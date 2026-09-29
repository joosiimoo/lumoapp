## Context

PRD v0.11 is the product authority for this slice (RF-001, RF-002, RF-003, RF-005). Build A v1.0 docs are implementation evidence only where they do not expand this slice.

Current persistence (`0001_foundation`, `BusinessRow`):

- `identity.businesses`: `name VARCHAR(200)`, `currency VARCHAR(3) NOT NULL`, `timezone VARCHAR(64) NOT NULL`, `locale` default `es-MX`, `status` default `active`.
- `identity.users.business_id` is required. `identity.memberships` already has unique `(business_id, user_id)` and `role` default `owner`.
- RLS on `identity.businesses` is `id = current_setting('app.current_business_id')`. Inserts as `lumo_app` succeed only after that GUC is set to the new id. There is no `WITH CHECK` bypass.
- No enabled-payment-method column. `PaymentMethod` is `cash`, `card`, `transfer` (`backend/app/domain/sales/session.py`). Sale commit already accepts only those three.
- `Money` accepts a 3-letter alphabetic code and uppercases it. It does not check a full ISO catalog.
- `business_date_for` resolves IANA names with `zoneinfo`. The API image has `tzdata`. Labels such as `Mexico` or `CST` fail.
- Businesses are inserted by `ensure_carrota_seed`, isolation fixtures, and tests. There is no merchant create-business command.
- Dev JWT (`issue_dev_token`) always embeds `sub` and `business_id`. `GET /api/v1/session` requires that tenant.
- Flutter `OnboardingPage` shows placeholder copy. `LumoHome` always loads Business Stream when a tenant token exists. The app has no device IANA timezone API.
- `OutcomeRun` is the Daily Close outcome. Onboarding does not use it.
- Alembic head is `0014_pilot_stage_gate_instrumentation`.

Directory layout stays the modular monolith: domain under `backend/app/domain/identity/` (or `onboarding/`), workflow under `backend/app/application/workflows/`, Flutter under `mobile/lib/features/onboarding/`. No new service, broker, or schema outside `identity`.

## Goals / Non-Goals

**Goals:**

- One authenticated creator can create one business, set currency, timezone, and at least one enabled payment method, review a summary, and complete only with explicit `start_using_lumo`, with zero catalog rows.
- State and next missing field are deterministic functions of persisted columns.
- Partial progress survives process restart.
- Corrections before completion update the same row.
- Existing operational tenants, including Carrota, start in the current shell. Migration does not rewrite their accepted data.
- Bootstrap uses a transaction-local GUC. Merchant RLS policies stay tenant-scoped.

**Non-Goals:**

See proposal. Post-completion settings editing, RF-009 pending payment, confirmation policy, and roles are out of this slice.

## Decisions

### 1. Conversational control plane, deterministic state

Onboarding is its own workflow, not an `OutcomeRun` and not a multi-step wizard. The merchant talks to Lumo. The server may emit a registered choice card when a closed set is easier than free text (currency, timezone, payment methods). Conversation remains the control plane: the card explains why Lumo is asking.

Persisted status is only `in_progress` or `completed`. There is no row for `not_started`. `ready_to_complete` is derived, not a stored status.

Next field is the first gap in this fixed order:

1. no business row for the actor → `business_name`
2. `currency` null → `currency`
3. `timezone` null → `timezone`
4. `enabled_payment_methods` is null or empty → `payment_methods`
5. name, currency, timezone, and a non-empty method set are stored, and status is still `in_progress` → `ready_to_complete`
6. the merchant sends an explicit `start_using_lumo` confirmation → status becomes `completed`

The system MUST NOT set `completed` merely because every field is present. No LLM ranking and no LLM inference decides confirmation. No generic NBA framework.

### 2. Business creation contract

`onboarding.apply@1` is the only writer. Input is a validated object with optional `name`, `currency`, `timezone`, and `payment_methods` (a set). The workflow:

- Rejects empty or whitespace-only names. Trims ends. Collapses internal whitespace. Keeps the merchant's casing. Maximum length 200, matching `identity.businesses.name`.
- Allows the same display name on different businesses. No global unique index on name.
- Creates the business, the user row, and one `memberships.role = 'owner'` row in one transaction the first time the actor submits a valid name. This reuses the existing membership primitive. It does not add roles, invites, or a second member (RF-007 is Build B).
- Build A bootstraps at most one business per actor because `actor_id` is the primary key of the link table. `business_id` on that table is not unique, so a later multi-user business is not structurally blocked. Authorization after bootstrap stays on membership and `TenantContext`.
- A repeated create for that actor returns the existing business. It does not insert another business, user, or membership.
- `business_id` is a server-generated UUIDv7. The client request MUST NOT contain or choose it. The authenticated `actor_id` comes from the principal.
- `locale` stays `es-MX`. `status` stays `active`. No other business columns.

Currency and timezone stay null until a valid value is applied. They become authoritative for `OperationalDay.business_date`, Daily Close, and stage-gate windows only after they are stored. Operational tools refuse the business until onboarding is `completed`.

### 3. Currency

Persist the uppercase code on `identity.businesses.currency`. Build A @1 supported set is exactly `{MXN}`. Reject any other code, including `USD`, and stay on `currency`. No FX and no multi-currency balances. Adding another currency requires a future product decision. It is not open for this slice.

Suggestion copy may mention pesos. The server must not write MXN until the merchant confirms it through the tool.

### 4. Timezone

Persist a ZoneInfo-resolvable IANA id. Reject `Mexico`, `CST`, empty strings, and unknown ids before write.

The Flutter app does not expose a safe IANA source. The client must ask. It must not persist a device abbreviation. A choice card may offer only this closed pilot list, all valid IANA ids:

- `America/Mexico_City`
- `America/Cancun`
- `America/Tijuana`
- `America/Hermosillo`
- `America/Mazatlan`
- `America/Chihuahua`
- `America/Merida`
- `America/Monterrey`
- `America/Bahia_Banderas`

The server accepts any id on that list. It rejects other ids in this slice, including other valid IANA zones. The merchant must confirm the zone. The client must not infer one from the device. Adding another zone requires a future product decision. It is not open for this slice.

### 5. Payment methods

Enabled methods are a set stored on the business, not on the chat transcript. Allowed values are exactly `PaymentMethod`: `cash`, `card`, `transfer`. Unknown methods are rejected.

`enabled_payment_methods IS NULL` means a legacy business with no explicit onboarding configuration. A non-null array is an explicit configuration and MUST contain at least one method. An empty array is invalid. It is not a wildcard.

A new onboarding may enter `ready_to_complete` only when the array is non-null and has cardinality at least 1. `completed` still waits for `start_using_lumo`.

Before confirmation, a later apply replaces the set with the validated set in the tool input (idempotent write of the same canonical sorted set). Example: cash, then "también aceptamos transferencia", yields `{cash, transfer}` with one configuration row state, not a second row.

`sale.commit@1` for a new completed business rejects a method outside that non-null set. A legacy `completed` business with `enabled_payment_methods IS NULL` keeps today's commit behavior for `cash`, `card`, and `transfer`. Carrota is that case. Do not backfill invented methods.

### 5b. Explicit confirmation

When `next_required_field` is `ready_to_complete`, the server emits a compact summary card with business name, currency, timezone, and enabled payment methods. The only completion action is an explicit `start_using_lumo` control. The LLM MUST NOT treat a free-form utterance as confirmation. Fields stay editable until that action. After `completed`, configuration edits stay out of this slice.

### 6. No catalog

Completion does not read or write `catalog.products`. After `completed`, the existing noncatalog sale path remains available.

### 7. Resume and correction

Progress is the business row. On the next authenticated open, `next_required_field` is recomputed from columns, not from chat history. If every required field is stored and status is still `in_progress`, the next field is `ready_to_complete` and the summary card is shown again. Before `start_using_lumo`, name, currency, timezone, and the payment-method set may be replaced with a new valid value, which returns the flow to the first missing field or back to `ready_to_complete`. After `completed`, this slice rejects configuration changes. There is no settings center. Post-completion editing is separate future work.

### 8. Owner bootstrap and tokens

Current dev tokens always carry `business_id`, and `users.business_id` is NOT NULL, so a principal cannot exist as a tenant before the business row.

Trusted bootstrap, in one transaction:

1. Accept a pre-tenant dev token whose `sub` is the actor UUID and whose `business_id` claim is absent. Only onboarding routes accept that token. Sale, close, memory, and session-as-tenant routes reject it.
2. Read `identity.actor_business_links` with RLS `actor_id = current_setting('app.current_actor_id')`. This is actor-scoped, not a global business read.
3. Resolve the authenticated actor from the principal. If an `actor_business_links` row already exists, return that business and do not insert another.
4. The server generates a new UUIDv7 `business_id`. The client MUST NOT send one.
5. Begin a transaction. `SET LOCAL app.current_business_id` to that generated id. Insert the business, insert the user (`id = actor`) or reuse only if the current model already has that user inside this transaction, insert the owner membership, insert `actor_business_links`, and persist the onboarding field writes that belong to this request.
6. Commit. Any failure rolls back the transaction. No partial business, user, membership, or link remains.
7. Return the normal tenant dev token (`sub`, `business_id`) from the existing issuer. Later requests use `TenantContext` as today (ADR-010).

No password signup. No change to Carrota's token.

### 8b. Concurrent first bootstrap

Two concurrent first-business attempts for the same actor MUST result in at most one associated business. The `actor_id` primary key is the database guard. The transaction inserts the link before commit, in the same transaction as the business, user, and membership. The loser hits the primary-key conflict and rolls back its entire transaction, so it MUST NOT leave an orphan business, user, or membership. No distributed lock. The winner's business is the one later requests resolve.

### 9. Existing businesses

Migration `0015` (not created in this step):

- Add `onboarding_status VARCHAR(32) NOT NULL DEFAULT 'completed'`. That default exists only so pre-0015 rows become `completed` without a data rewrite. The bootstrap workflow MUST insert `onboarding_status = 'in_progress'` explicitly and MUST NOT rely on the default. `enabled_payment_methods` starts NULL on that new row.
- Add `enabled_payment_methods TEXT[] NULL` with no default array. Existing rows, including Carrota, stay `NULL`.
- Drop NOT NULL on `currency` and `timezone` so in-progress rows can exist. Existing rows are not updated to null.
- Check constraints: status in `in_progress`, `completed`; a non-null array has cardinality at least 1 and each element is `cash`, `card`, or `transfer`. NULL stays valid for legacy completed rows. An empty array is rejected by the check.
- Create `identity.actor_business_links(actor_id UUID PRIMARY KEY, business_id UUID NOT NULL, created_at)`. Do not add `UNIQUE(business_id)`.
- RLS on the link table as in decision 8. Existing business RLS policies are unchanged.
- Data backfill: `UPDATE` is not required for status if the default is `completed`. Do not update Carrota name, currency (`MXN`), timezone (`America/Mexico_City`), products, sales, or memberships. Leave `enabled_payment_methods` NULL. Do not insert payment methods for existing rows.

### 10. Audit and idempotency

Reuse `audit.audit_events` and ADR-011. Actions: `business.created`, `business.currency_configured`, `business.timezone_configured`, `business.payment_methods_configured`, `business.onboarding_completed`. Same transaction as the write.

`onboarding.apply@1` requires an idempotency key. Reuse ADR-011. Do not add a second idempotency system.

Before a business exists, the identity is `actor_id + operation_type + idempotency_key`. After a business exists, the identity is `business_id + operation_type + idempotency_key`.

In both phases, the same identity and the same payload replay the original result. The same identity with a different payload is `IDEMPOTENCY_CONFLICT`. The `actor_id` primary key is the concurrency guard. It does not replace this request identity. A replay must not insert a second business, user, membership, or link. Two concurrent first bootstraps with different keys for the same actor still leave at most one association, and the loser rolls back with no orphan rows.

### 11. UI and routing

`OnboardingPage` becomes the conversational surface (existing `LumoScaffold` without the tab bar, composer, Lumo messages, choice cards, and one compact confirmation card). The confirmation card shows name, currency, timezone, and enabled methods, and exposes `start_using_lumo`. It stays inside the conversation. No wizard, settings page, POS setup, or dashboard.

Startup:

- Pre-tenant or `in_progress` → onboarding.
- `completed` → existing `LumoHome` / Inicio.
- Carrota's session is `completed` → unchanged Inicio.

`GET /api/v1/session` gains `onboarding_status`, `currency`, `timezone`, `enabled_payment_methods`, and `next_required_field` for tenant tokens. A pre-tenant status route returns `not_started` and `next_required_field=business_name` without a business body.

### 12. ADR

This change prepares **ADR-030** (Proposed): trusted pre-tenant creation, deterministic onboarding state, initial configuration fields, and legacy-tenant compatibility. It does not mark the ADR Accepted.

## Build A @1 decisions

These seven items are closed for this slice. None of them blocks implementation.

1. **Currency.** Supported set is exactly `MXN`. No `USD` and no FX. An unsupported code is rejected and the next field stays `currency`.
2. **Timezone.** The nine Mexico IANA ids above. Merchant confirmation is required. No device inference and no ambiguous labels.
3. **Payment methods.** Exactly `cash`, `card`, and `transfer`. No other methods, no mixed payments, and no RF-009 payment-pending behavior.
4. **Owner and bootstrap.** One Build A creator with membership role `owner`. `actor_business_links` resolves bootstrap only: `actor_id` primary key, `business_id` not unique. A pre-tenant token has no `business_id` and is valid only on onboarding routes. The actor id comes from the principal. After creation the normal tenant token applies. No signup redesign and no RBAC expansion.
5. **Post-completion edits.** After `onboarding_status = completed`, this slice rejects configuration changes. No settings center. Later settings work is separate.
6. **Persistence.** Columns on `identity.businesses` plus `identity.actor_business_links`. No onboarding JSON document and no separate onboarding state store.
7. **Legacy payment methods.** `enabled_payment_methods IS NULL` means a legacy business with no explicit configuration. An empty array is invalid. Carrota stays `completed` with NULL methods and keeps current `sale.commit@1` behavior.

## Risks / Trade-offs

- Nullable currency and timezone weaken the old NOT NULL guarantee. Operational tools must keep refusing incomplete businesses so Daily Close cannot run without a zone.
- A pre-tenant token is a new claim shape. Limiting it to onboarding routes is part of the security contract. Forgetting that check would expose tenant APIs with no tenant.
- Actor-scoped RLS on the link table is a second policy shape. It must not be copied onto sales or catalog tables.
- NULL payment methods mean "legacy, not configured here." A non-null set is explicit. New completions cannot use NULL or an empty array.

## Migration Plan

Design only. At implementation time, add Alembic revision `0015` after `0014`, as specified above. Do not create that file in this OpenSpec step. Downgrade drops the link table and new columns and restores NOT NULL only if no null currency or timezone rows exist.

No product decision inside RF-001, RF-002, RF-003, and RF-005 remains open for this slice. Adding a currency, a timezone, or a settings editor later requires a future product decision.
