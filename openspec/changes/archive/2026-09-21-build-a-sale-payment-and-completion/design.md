## Context

`build-a-conversational-sale-session` is archived. The backend can accumulate catalog lines on one `SaleSession` scoped to `(business_id, actor_id, conversation_id)`, totalize with `sale.totalize@1` to `ready_to_charge`, and render `sale_summary@1`. Status CHECK and unique index `uq_sale_sessions_active_context` cover `open` and `ready_to_charge` only. `sale.commit@1` is unregistered. Flutter Inicio holds one stable client UUID as `conversation_id`. Adding items after `ready_to_charge` is rejected for that conversation.

This change completes the operational sale: record one payment method, confirm the sale, and allow the next customer sale in the same conversation.

Authority: Build A PRD/SRS/Architecture/Design System v1.0. PRD v0.11 is vision only. ADRs 001–014 remain accepted; ADR-012 stays prepared (outcomes still unregistered). ADR-014 reserved `sale.commit@1` for payment and financial confirmation and stated that `ready_to_charge` is not PRD `confirmed`.

Inspection notes that constrain design:

- `get_active_session` already filters `open` | `ready_to_charge`. Confirmed sessions will drop out of that lookup without a query rewrite if the CHECK is widened and the unique index predicate is left unchanged.
- `conversation_id` is `VARCHAR(128) NULL`. Do not change the column type. Keep `COALESCE(conversation_id, '')` on the unique index.
- Architecture §11.2 lists `sales`, `sale_lines`, `payments`. The live model is `sale_sessions` / `sale_items` (foundation mapping: `SaleSession` = Sale in draft). Do not invent a second sale table in this slice.
- PRD §8.1 canonical sale state is `confirmed`. PRD §8.2 payment state is `recorded`.
- Architecture `sale.commit` writes sale + payment in one transaction. That is this slice. It also updates jornada — deferred (Daily Close is a non-goal).
- Design System §4.12 is the compact registered-sale card. §4.11 payment chips stay on the prepared card, which this slice does not reintroduce.
- Alembic head is `0003_ready_to_charge`. Next revision is `0004`.

## Goals / Non-Goals

**Goals:**

- Prove Lumo can finish an operational sale: ready to charge → payment recorded → confirmed, then start the next sale naturally.
- Keep conversation as the control plane; Flutter only renders server values.
- Stay compatible with a future `LLMProvider` (scripted interpreter remains local/test).

**Non-Goals:**

- Daily Close, OperationalDay, CashCount, expected cash, WorkItems, NextBestAction, outcomes.
- Mixed/split/partial payments, change due, over/under payment, tips, fees, discounts, pending payment without a method.
- Acquirer/terminal/bank APIs, cash drawer, refunds, reversals, void, reopen, item edit/remove.
- Catalog price re-read at commit, catalog CRUD, unknown products, inventory, invoicing, CFDI, receipts, history, export.
- Combined item+payment utterances, explicit "nueva venta", Conversation aggregate, vendor LLM, Redis/Kafka/vector DB.

## Conflicts with the current active baseline

| Baseline | Conflict | Resolution |
|---|---|---|
| `sales-session-foundation`: status `open` \| `ready_to_charge` | Need a completed state | Delta: add `confirmed` (PRD §8.1). Do not use `completed` or `paid` |
| Unique index `WHERE status IN ('open', 'ready_to_charge')` | Confirmed would block the next sale if added to the predicate | Keep the `0003` index as-is so `confirmed` is inactive |
| `ai-native-contracts`: `sale.commit@1` unregistered | Architecture reserved commit for payment | Register `sale.commit@1` now |
| `ai-native-contracts` / `sale-summary-ui`: no confirmed-sale card | Need a post-payment UI | New `sale_confirmed@1`. Do not reuse `sale_summary@1` |
| Conversational-sale-session: add-item after ready is forever blocked | Next sale must start naturally | After `confirmed` only: same `conversation_id` may create a new `open` session |
| ADR-014: new `conversation_id` is the way to start another sale | Inicio holds one stable UUID | Backend inactivity of `confirmed` is the lever; Flutter MUST NOT rotate |
| SRS §8.6 / Architecture `sales` + `sale_lines` | Live tables are `sale_sessions` + `sale_items` | Confirmed `SaleSession` is the durable Sale. Separate `Payment` table. No `sales.sales` yet |
| Architecture §10.2 step 3 price revalidation (RF-A-037) | Items are immutable after totalize; catalog CRUD is out | Defer re-read; snapshots remain truth |
| Architecture §10.2 step 7 update jornada | Daily Close is a non-goal | Do not create `operations` schema |
| PRD §7.6 pending payment + WorkItem | This slice requires an explicit method | Subset: exactly one recorded payment. Pending is later |
| PRD §10.5 `sale_confirmed_card` | Event-like UI names | `sale_confirmed@1`, not the PRD card name |
| SALE-002 add-item only while `open` | After confirmed, lookup finds no active session | Message path creates a new open session. Tool-level add against a confirmed `sale_session_id` still denies |

## Assumptions

1. Interaction context remains `(business_id, actor_id, conversation_id)` when present. Inicio continues to send one stable client UUID through payment and the next product utterance.
2. Local/test use the scripted interpreter; no vendor LLM SDK.
3. Golden path stays Zanahoria `22.50` + Tomate `10.00` + Galleta A `24.00` = `56.50` MXN, then cash/card/transfer.
4. Permission for commit is `sale.create` (same as add-item and totalize).
5. `POST /api/v1/lumo/messages` remains the only public conversational entry.
6. Clarifications stay HTTP 200 agent text, not `409`.
7. Session currency remains the business currency (MXN for Carrota).
8. Orchestrator still does not open ORM sessions. Application workflows own write transactions.
9. One product line per utterance. Payment is its own turn after `ready_to_charge`.
10. Payment amount always equals the locked session total. The user never types an amount in this slice.
11. `subtotal` remains unused on the confirmed card; `total` is the sale total.
12. `pagar` and `cobrar` are not commit synonyms. `cobrar` is still not totalize (ADR-014).
13. Catalog prices are not edited in this slice, so RF-A-037 would not change the golden totals even if implemented.

## Exact entities and state transitions

### SaleSession (`sales.sale_sessions`)

Fields unchanged: `id`, `business_id`, `actor_id`, `conversation_id`, `status`, `currency`, timestamps. No `total` column. No `payment_method` column.

Active = `open` | `ready_to_charge`. Inactive durable = `confirmed`.

```text
(none) --add-item--> open --add-item--> open --totalize--> ready_to_charge --commit--> confirmed
                                              ^                         |
                                              |                         +-- different-key totalize: read-back
                                              |                         +-- add-item: deny
                                              |
                         after confirmed, same conversation_id, product utterance
                                              |
                                              v
                                            open (new session)
```

| From | Event | To | Notes |
|---|---|---|---|
| `ready_to_charge` | `sale.commit@1` with closed-enum method, commit | `confirmed` | lock row; one tx with Payment + audit + outbox + idempotency |
| `ready_to_charge` | add-item | `ready_to_charge` | deny; no new item; no new session |
| `ready_to_charge` | totalize | `ready_to_charge` | existing read-back |
| `open` | commit / payment intent | `open` | deny/clarify; no Payment |
| (none) | payment intent | (none) | deny/clarify; do not create a session |
| `confirmed` | same original commit idempotency key | `confirmed` | replay original body |
| `confirmed`, no newer active session | payment intent, different key | `confirmed` | non-mutating read-back of `sale_confirmed@1` |
| `confirmed` | message-path add-item, same conversation | new `open` | previous sale immutable |
| `confirmed` | tool `sale.add_item@1` targeting that session id | `confirmed` | deny; do not append |
| `confirmed` | totalize | (none active) | existing empty/missing totalize clarification; no mutation |

Out of scope: `pending_information` as a persisted status, `voided`, `paid`, `completed`.

### Payment (`sales.payments`) — new

| Field | Type | Notes |
|---|---|---|
| `id` | UUIDv7 | |
| `business_id` | UUID | tenant |
| `sale_session_id` | UUID FK | unique; one payment per sale |
| `actor_id` | UUID | confirming actor |
| `method` | enum | `cash` \| `card` \| `transfer` |
| `amount` | numeric(12,2) | equals sale total |
| `currency` | char(3) | session currency |
| `status` | enum | `recorded` only in this slice |
| `source` | enum | `manual_capture` |
| timestamps | timestamptz | |

No authorization code, reference, change due, or acquirer fields.

### Sale / SaleLine

Not created. Confirmed `SaleSession` + `SaleItem`s are the durable completed sale. Mapping recorded in D1.

## Exact tool contracts

Shared: JSON snake_case; money `{ "amount": "<decimal-string>", "currency": "MXN" }`; tenant from session.

Existing tools keep their contracts. `sale.start@1` output `status` remains `open` | `ready_to_charge` only. A confirmed session is historical/inactive and MUST NOT be returned as the started or reused session. After confirmed, start creates a **new** `open` session (`created=true`, `status=open`).

### `sale.commit@1` (new)

- permission: `sale.create` · side_effect: `write` · idempotency: true for the **transition**; read-back on `confirmed` is non-mutating · policies: `SALE-004`, `PAY-001`, `INT-001`

Input: `{ "conversation_id": string | null, "payment_method": "cash" | "card" | "transfer" }`

Output: `{ "sale_session_id", "payment_id", "status": "confirmed", "currency", "item_count", "total", "payment": { "method", "amount", "status": "recorded" }, "items": [ { "sale_item_id", "product_name", "quantity_normalized", "unit_normalized", "unit_price", "line_total" } ] }`

**SALE-004:** `ready_to_charge` → `confirmed` **transition** requires `status=ready_to_charge`. `confirmed` is allowed only as a stable read-back/no-op. `open` or missing sale is blocked.

**PAY-001:** method MUST be the closed enum. Do not infer `cash`. Unknown / missing method is clarify, no mutation.

**Transition path:** lock the active session row under `TenantContext`; re-read status and items while locked; Decimal total; insert `Payment` whose `business_id` is copied from that tenant/session (never from client or tool input); set `confirmed`; `sale.commit@1` audit; outbox `sale.confirmed` and `payment.recorded`; complete `lumo.message.commit_sale`; compose `sale_confirmed@1` only after commit. `add_payment` MUST reject a `business_id` that does not match the locked session.

**Same original idempotency key:** replay the original persisted response.

**Different key after confirmed (no newer active session):** non-mutating read-back. Do not write a new idempotency record, transition audit, Payment, or outbox event. The HTTP route still requires `Idempotency-Key`.

`AgentDecision` gains `intent=commit_sale` and optional `payment_method`.

## Exact Generative UI contracts

### `sale_summary@1`

Unchanged for `ready_to_charge`. MUST NOT be emitted after commit.

### `sale_confirmed@1` (new)

See `specs/sale-confirmed-ui/spec.md`. Visual: Design System §4.12 registered card (status, total · method, item count). Payload includes `items` for evidence; Flutter may render the compact registered form without summing lines. No payment chips, Registrar, Corregir, Deshacer, receipt, or invoice.

## Transaction, lock, idempotency, events

```text
CommitSaleSession (application UoW)
  1. peek lumo.message.commit_sale → replay if completed
  2. SELECT active session FOR UPDATE under TenantContext (open | ready_to_charge)
  3. if none: load latest confirmed for context → read-back or SALE_NOT_FOUND
  4. if open → SALE_NOT_READY_TO_CHARGE, no writes
  5. if ready_to_charge:
       begin idempotency
       sum items (Decimal)
       insert Payment.business_id = tenant.business_id (= locked session.business_id)
       status = confirmed
       audit sale.commit@1
       outbox sale.confirmed + payment.recorded
       complete idempotency
  6. success only after commit
```

Row lock is the same pattern as add-item/totalize (`with_for_update()`). Unique `payments.sale_session_id` is a second barrier. Two racing commits serialize on the session row; the second either replays (same key) or read-backs (different key).

Add-item vs commit is decided by which write transaction first commits its locked view of the active session. Add-item performs **one** `get_active_session(for_update=True)` in its write transaction and MUST NOT re-query after a `ready_to_charge` deny.

```text
CASE A — add-item obtains FOR UPDATE on ready_to_charge first
  add-item sees ready_to_charge → SALE-002 deny → no SaleItem, no new session
  commit waits, then confirms Sale A

CASE B — commit confirms and commits first
  Sale A is confirmed and immutable
  add-item's later active-session lookup finds none
  the same add-item request MAY create Sale B (new open session)
  the new item belongs only to Sale B
```

CASE B is intentional Build A behavior (next sale in the same conversation), not an accidental side effect. Do not add conversation epochs, Redis, distributed locks, "nueva venta", or `conversation_id` rotation.

`Payment.business_id` is an application/repository invariant matching `sale_items`: copy from `TenantContext` / locked session; FK remains `sale_session_id` only. Do not add a composite `(business_id, sale_session_id)` foreign key; `sale_sessions` is keyed by `id` and `0002` already used that pattern. FORCE RLS is defense-in-depth.

Audit action: `sale.commit@1` (matches `sale.totalize@1` / `sale.add_item@1`).

Outbox: `sale.confirmed` (destination-state naming, like `sale.ready_to_charge`) and `payment.recorded` (PRD payment state).

Error codes for structured tool invocation: `SALE_NOT_READY_TO_CHARGE`, `SALE_NOT_FOUND`, `PAYMENT_METHOD_UNKNOWN`. Conversational path remains HTTP 200 text.

Cleanup: extend `sale_cleanup` with payment deletes (before sessions), plus the new audit/outbox/idempotency names.

## Flutter next-sale behavior

Inicio keeps one `conversation_id`. After `sale_confirmed@1`, the next `900gr zanahoria` uses that same id. Backend `get_active_session` returns none, so add-item creates a new `open` session. Flutter MUST NOT rotate the UUID and MUST NOT compute payment totals. `sale.start@1` in that situation returns `status=open`, never `confirmed`.

## Decisions

### D1. Confirmed SaleSession is the durable Sale; Payment is a separate table

PRD/SRS/Architecture name `Sale` + `SaleLine` + `Payment`. The live model already mapped `SaleSession` = Sale in draft. Copying items into new `sales` / `sale_lines` tables would duplicate snapshots without a consumer. Alternative: introduce `sales.sales` now — rejected as premature. Alternative: store method on `sale_sessions` — rejected; Payment is its own entity (PRD §8.2, Architecture §11.2).

### D2. Canonical completed state is `confirmed`, not `completed` or `paid`

PRD §8.1. `completed` collides with OutcomeRun/Daily Close. `paid` overstates acquirer settlement. `ready_to_charge` stays the pre-payment gate (ADR-014).

### D3. Register `sale.commit@1` now

Architecture §10.2 and ADR-014 reserved this name for payment/confirmation. Alternative: `sale.complete@1` — rejected; it would fragment the closed catalog.

### D4. `sale_confirmed@1`, not `sale_completed@1` or `sale_summary@1`

Semantic state changed; `sale_summary` stays ready-to-charge. Event-like naming matches `sale_item_added`. PRD `sale_confirmed_card` stays unregistered.

### D5. conversation_id does not rotate; confirmed leaves the unique index

Preferred product: next product utterance starts the next sale. The `0003` unique index already excludes non-active statuses. Flutter rotation would fight Inicio's stable UUID and is unnecessary. Alternative: explicit "nueva venta" — rejected as extra UX. Alternative: treat completed sessions as still active — rejected; that would block the next customer.

### D6. Different-key repeat after confirmed is a read-back

Same as totalize D19. Alternative: reject as already confirmed — worse UX when the merchant repeats `efectivo`. Alternative: treat as no-sale — wrong while the just-confirmed sale is the latest session. If a **new open** session already exists, payment intent applies to that new sale (and is denied until totalize).

### D7. Payment amount is server total only

No user-entered amount. Change due is PRD-adjacent but not required for this pilot replacement; defer explicitly.

### D8. Do not re-read catalog prices at commit

RF-A-037 waits for a slice that can change prices between totalize and pay. Ready-to-charge items are immutable. Changing the total at payment would surprise the merchant.

### D9. Closed phrase set; interpreter still has no DB access

Exact trimmed case-insensitive phrases listed in the spec. Do not parse `900gr zanahoria tarjeta` as combined sale+pay. Do not map `pagar` alone.

### D10. Application workflow `CommitSaleSession`

Lives at `backend/app/application/workflows/commit_sale_session.py`. Orchestrator gains a `commit` collaborator and routes `commit_sale` before add-item. Do not merge into `TotalizeSaleSession`.

### D11. Policies SALE-004 and PAY-001

- `SALE-004`: transition requires `ready_to_charge`; confirmed is read-back.
- `PAY-001`: Architecture id reused — method must be explicit; do not infer cash.

### D12. ADR this change establishes

- ADR-015 (prepare/accept): `ready_to_charge` → `confirmed` via `sale.commit@1` with one `Payment`; confirmed `SaleSession` is the durable sale; `conversation_id` does not rotate.
- ADR-014 remains: totalize is not payment.
- ADR-013 remains: message path owns the UoW.
- ADR-007/006/009 remain: server math, LLM non-mutation, closed Generative UI.
- ADR-012 still prepared.

### D13. Visual mapping

Reuse `LumoCard` and status treatment. Map to Design System §4.12. Do not implement payment chips or Deshacer. Do not redesign Inicio.

### D14. `openspec/config.yaml`

Update project context so later artifacts know `sale.commit@1` and `sale_confirmed@1` are registered, statuses include `confirmed`, and Payment exists.

### D15. Directory layout

No new top-level packages. Domain payment types in `backend/app/domain/sales/`. No `operations` / `workflow` / `memory` schemas.

### D16. Payment tenant ownership is application/repository, matching sale_items

`sale_items` FKs `sale_session_id` only and copies `business_id` from `TenantContext`. Payments MUST do the same. `CommitSaleSession` locks the session under the tenant before `add_payment`. `add_payment` MUST assign `business_id` from `tenant.business_id` and reject a mismatch with the locked session. Client, interpreter, and tool input MUST NOT supply `business_id`. FORCE RLS remains the second barrier. Alternative: composite FK `(business_id, sale_session_id)` — rejected; `sale_sessions` has no unique `(id, business_id)` constraint today and this repo does not use composite FKs on sales tables.

### D17. Commit vs add-item CASE A / CASE B is intentional

The transaction that first commits its locked view of the active session decides ownership. CASE A (add-item locks `ready_to_charge` first) is a hard deny for that request. CASE B (commit commits first) allows the same add-item request to become the first item of Sale B. Alternative: after CASE B, still reject add-item until a later turn — rejected; it would block the next customer in the same conversation. Alternative: rotate `conversation_id` or introduce epochs — rejected.

## Risks / Trade-offs

- [No separate Sale table vs later reporting/close] → D1 mapping; Daily Close can project confirmed sessions later.
- [Merchant repeats efectivo after starting a new open sale] → payment hits the new open session and clarifies to totalize first; does not mutate the previous Payment.
- [Add-item racing commit] → D17: CASE A deny; CASE B new Sale B. Never append to confirmed. Tests cover both orderings.
- [Payment with forged business_id] → D16: repository rejects mismatch before commit; RLS still applies.
- [Interpreter overfits payment phrases] → closed list; `pagar` alone clarifies.
- [RF-A-037 skipped] → documented deferral; items frozen at totalize.
- [Cash change not shown] → explicit non-goal; registered card has no change line.

## Migration Plan

Alembic `0004_sale_session_confirmed_payment`, revises `0003_ready_to_charge`:

1. Replace `ck_sale_sessions_status` so status IN (`open`, `ready_to_charge`, `confirmed`).
2. Do **not** drop or recreate `uq_sale_sessions_active_context`.
3. Create `sales.payments` as specified: FK on `sale_session_id` only (same as `sale_items`), UNIQUE (`sale_session_id`), FORCE RLS, `tenant_isolation` policy, grants to `lumo_app`. Do **not** add a composite `(business_id, sale_session_id)` foreign key.
4. Do not create `sales.sales` / `sale_lines`. Do not add a session total or payment_method column.

Rollback: downgrade 0004. Inicio can ignore unknown `sale_confirmed` via `fallback_text`. No production tenant.

## Open Questions

1. Whether a later close/reporting slice should project confirmed sessions into a dedicated `sales.sales` table — deferred; mapping is D1.
2. Whether RF-A-037 price revalidation at commit is required before catalog CRUD exists — deferred; D8.
3. Whether cash change-due is required for the Carrota pilot — deferred; D7. Confirm only if product later insists despite this slice's non-goals.
4. Whether pending payment + WorkItem (PRD §7.6) should be allowed without a method — out of this change.
5. Production LLM provider — still deferred.
6. Whether `conversation_id` becomes a Conversation aggregate — still not in this change.
