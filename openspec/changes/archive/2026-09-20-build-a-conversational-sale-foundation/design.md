## Context

`build-a-core-foundation` is archived. The backend has empty `ToolRegistry` / `GenerativeUIRegistry`, policies `SEC-001`–`SEC-003` only, PostgreSQL schemas `identity`/`audit`/`platform`, and a fake LLM that never mutates. Flutter Inicio is a placeholder; `GenerativeUIRenderer.known` is empty. This change is the first AI-native product slice: interpret `"900gr zanahoria"`, resolve catalog, normalize grams, price and persist in PostgreSQL, audit, and render `sale_item_added@1` on Inicio.

Authority: Build A PRD/SRS/Architecture/Design System v1.0. PRD v0.11 is vision only. ADRs 001–011 remain accepted; ADR-012 stays prepared (outcomes still unregistered).

## Goals / Non-Goals

**Goals:**

- Prove one vertical conversational add-item path end to end.
- Introduce `catalog` + `sales` persistence, three versioned tools, minimum policies, and one Generative UI contract.
- Keep conversation as the control plane; Flutter only renders server values.

**Non-Goals:**

- Payment, sale completion, operational day, close, cash, history, export, overrides, discounts, unknown products, multi-product messages, catalog CRUD UI, inventory, voice, camera, vendor LLM, outcomes.

## Conflicts with the current active baseline

| Baseline | Conflict | Resolution |
|---|---|---|
| `persistence`: product schemas MUST NOT exist | This slice needs `catalog` and `sales` | Delta: create those two schemas only; keep `operations`/`workflow`/`memory` absent |
| `ai-native-contracts`: empty tool catalog | Product tools required | Register exactly `catalog.resolve_product@1`, `sale.start@1`, `sale.add_item@1`; `sale.commit@1` stays unregistered |
| `ai-native-contracts`: policies SEC-001–003 only | Add-item needs catalog/quantity/integrity rules | Add `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, `SALE-001` |
| `ai-native-contracts`: empty UI registry | Need a card for the slice | Register only `sale_item_added@1` |
| `mobile-shell`: Inicio MAY be a placeholder | Composer must send | Inicio becomes a live stream; other tabs stay placeholders |
| Architecture §10.1 tools `catalog.search`, `sale.prepare`, `sale.commit` | Requested tools differ | Slice tools are the draft-stage subset. `catalog.resolve_product` is a precise read; `sale.start`/`sale.add_item` are the draft of later `sale.prepare`/`sale.commit`. Do not register commit yet |
| SRS §8.6 `Sale` / `SaleLine`; PRD §8.1 `draft→confirmed` | Requested `SaleSession` / `SaleItem` | Map `SaleSession` = Sale in `open` (draft-equivalent). Confirmation is a later change |
| PRD §10.5 `sale_draft_card` / `sale_confirmed_card` | Requested `sale_item_added@1` | New contract maps to Design System §4.14 product row + soft card, **without** payment chips or Registrar |
| `openspec/config.yaml` foundation-only artifact rules | Stale “no catalog/sales logic” rules | **Resolved before apply:** config context and artifact rules now allow product logic owned by an approved change; architectural constraints are unchanged |
| Architecture §23 sequenced catalog, then sales, then agent, then experience | Combined thin slice | Intentional: one path, not three full modules |

## Assumptions

1. Interaction context is `(business_id, actor_id, conversation_id)` when `conversation_id` is present. Inicio MUST send a client-generated UUID on every `POST /api/v1/lumo/messages` and reuse that same id across turns in the current conversational sale context (including `"900 zanahoria"` then `"gr"`). A new context (for this slice: a new Inicio widget / app process) MAY generate a new UUID. This is not a Conversation aggregate and MUST NOT create schema `memory`. Independent `sale.start@1` MAY still receive `conversation_id=null`; that NULL bucket MUST NOT be used by Inicio.
2. Local/test use a scripted interpreter; no vendor LLM SDK in this change.
3. Seed price is **25.00 MXN / kg** so `0.900 × 25.00 = 22.50` is an exact Decimal result.
4. `current_price` lives on `Product`; `ProductPrice` history and `UnitConversion` tables wait. Gram→kg is a domain rule (`/ 1000`).
5. Alias table exists but Zanahoria needs no alias.
6. Permission for all three tools is `sale.create` (SRS §11). No catalog CRUD permission is exercised.
7. `POST /api/v1/lumo/messages` is the only public entry (SRS §8.2). Tools are not public HTTP resources.
8. Clarifications return HTTP 200 agent responses with no UI card, not `AMBIGUOUS_PRODUCT` 409, because conversation is the surface. Missing-unit clarification MUST retain parsed product and quantity for the next user turn in the same interaction context.
9. Camera/mic composer icons stay decorative. Enter and the send button share one submit path.
10. Session currency is the business currency (MXN for Carrota).
11. Orchestrator selects intent and registered tools; it does not open ORM sessions or transactions. The application workflow owns sequencing and the write transaction.
12. `SaleSession.status=open` is the only status in this change (PRD `draft` equivalent).
13. The public logical mutation is one user message, not two committed tool calls. `catalog.resolve_product@1` is read-only and runs before the write transaction.
14. Local Compose publishes PostgreSQL to the host as `5432:5432`. Container-internal Postgres remains `5432`. Host `5433` is not canonical.
15. FORCE RLS means `SELECT * FROM catalog.products` (and sales tables) returns zero rows unless `app.current_business_id` is set, even when seed rows exist. `lumo_admin` does not bypass RLS.
16. Flutter display labels (`kg`, `g`, `unidad`, `paquete`) MUST NOT change persisted `unit_normalized` (`kilogram`, etc.).

## Exact entities and state transitions

### Product (`catalog.products`)

Fields: `id`, `business_id`, `name`, `normalized_name`, `sale_unit` (`unit`\|`package`\|`kilogram`), `pricing_type` (`per_unit`\|`per_package`\|`per_kilogram`), `current_price numeric`, `status` (`active`\|`inactive`), timestamps.

Optional `catalog.product_aliases`.

No status machine beyond active/inactive. Inactive MUST NOT resolve for new items.

### SaleSession (`sales.sale_sessions`)

Fields: `id`, `business_id`, `actor_id`, `conversation_id` (nullable only for independent start; Inicio message path persists the client UUID), `status`, `currency`, timestamps. When `conversation_id` is present, open-session uniqueness/reuse is `(business_id, actor_id, conversation_id)`. New Inicio runs MUST NOT silently reuse an unrelated historical open session that has a different or NULL `conversation_id`.

| From | Event | To | Notes |
|---|---|---|---|
| (none) | standalone `sale.start@1` commits | `open` | empty session is valid only when start is the public operation |
| (none) | message workflow creates session + item, commit | `open` | one transaction; session and item appear together |
| `open` | standalone or composed start (reuse) | `open` | same id, `created=false` |
| `open` | composed add-item success | `open` | item appended in the same write transaction as start/reuse |
| (none) | message workflow creates session, add-item fails | (none) | rollback; **no orphan session** |
| `open` | reused session, add-item fails | `open` | pre-request session unchanged; no new item |

Out of scope: `pending_information`, `confirmed`, `voided`.

### SaleItem (`sales.sale_items`)

Append-only in this change. Created only after unique product resolve, compatible unit, positive quantity, policy `allow`, and commit.

## Exact tool contracts

Shared: JSON snake_case; money `{ "amount": "<decimal-string>", "currency": "MXN" }`; tenant from session.

### `catalog.resolve_product@1`

- permission: `sale.create` · side_effect: `read` · idempotency: false · policy: `CAT-001`

Input: `{ "query": string }`

Output: `{ "match": "unique"|"ambiguous"|"none", "product": { "product_id", "name", "normalized_name", "sale_unit", "pricing_type", "current_price", "product_status" } | null, "candidates": [{ "product_id", "name" }] }`

### `sale.start@1`

- permission: `sale.create` · side_effect: `write` · idempotency: true · policy: `INT-001`

Input: `{ "conversation_id": string | null }`

Output: `{ "sale_session_id": uuid, "status": "open", "created": boolean, "item_count": integer }`

### `sale.add_item@1`

- permission: `sale.create` · side_effect: `write` · idempotency: true · policies: `SALE-001`, `CAT-001`, `CAT-002`, `INT-003`, `SEC-003`

Input: `{ "sale_session_id": uuid, "product_id": uuid, "quantity": "<decimal-string>", "unit": "gram"|"kilogram"|"unit"|"package" }`

Output: `{ "sale_session_id", "sale_item_id", "product_id", "product_name", "quantity_input", "unit_input", "quantity_normalized", "unit_normalized", "unit_price", "line_total", "session_item_count", "session_total" }`

Golden I/O: quantity `900` + unit `gram` + Zanahoria → `quantity_normalized=0.900`, `unit_normalized=kilogram`, `unit_price.amount=25.00`, `line_total.amount=22.50`.

Message path (not two commits): read resolve → application write transaction (start/reuse + add-item + audit/outbox/idempotency) → compose UI only after that commit. See D10.

`AgentDecision` optional fields: `product_query`, `quantity`, `unit`. Existing `intent`, `entities`, `candidate_tool`, `missing_fields`, `clarification_question` remain.

## Exact Generative UI contract

`sale_item_added@1` — see `specs/sale-item-added-ui/spec.md`. Actions `[]`. Flutter maps to Lumo mark + `LumoCard` product row (Design System §4.14 / §5 `sale item`) with **user-facing** quantity/unit/price labels (`0.900 kg · $25.00/kg`). Canonical payload fields stay `quantity_normalized=0.900`, `unit_normalized=kilogram`, `unit_price.amount=25.00`. No payment section, no Registrar. User turn: right-aligned `#267B4C` bubble. Lumo: mark + unbubbled text/card. Inicio eyebrow is `LUMO · {session business name}` in uppercase. Greeting is Design System display greeting with Lumo gradient: `Buenos días`.

## Acceptance tests for `"900gr zanahoria"`

1. **E2E golden path.** Seeded Carrota actor posts the message with a client `conversation_id`. After commit: unique Zanahoria resolve; one open `SaleSession` whose `conversation_id` equals the request; one `SaleItem` with `0.900` kg, unit price `25.00`, line total `22.50` MXN; audit, outbox, and message idempotency rows in the same transaction that reference live session/item ids; response `ui[0]` is `sale_item_added@1` with those server values.
2. **Flutter render.** Inicio shows user bubble `"900gr zanahoria"` and the card; client does not multiply `0.900 * 25`.
3. **Idempotent replay.** Same `Idempotency-Key` + hash → same item id, one row.
4. **LLM cannot mutate.** Provider has no repository; a hinted total `99.00` is ignored.
5. **Ambiguous / missing unit / unknown product.** Clarification, zero `SaleItem` writes, and no new `SaleSession`. After missing-unit clarification, a unit-only reply (`gr` / `g` / `gramos` / `kg` / `kilogramo` / `kilogramos`) MUST complete add-item using the preserved product and quantity.
6. **Two-turn missing unit.** `"900 zanahoria"` then `"gr"` with the same `conversation_id` → one open session (that persisted id) and one item only after the second turn.
7. **Tenant isolation.** Business B cannot resolve or add Carrota Zanahoria (`TENANT_SCOPE_VIOLATION` / empty resolve).
8. **Unregistered tool.** `sale.commit@1` denied; `sale_confirmed_card` cannot be composed.
9. **Rollback — new session.** No prior open session; force failure after session+item writes, before commit → zero `SaleSession` and zero `SaleItem` remain; no audit/outbox success rows; idempotency remains failed or absent so retry can execute.
10. **Rollback — reused session.** Open session already exists; force add-item failure before commit → that session is unchanged; no new `SaleItem`; no partial audit/outbox/idempotency for the failed message.
11. **Same conversation reuses session.** Two successful add-item messages with the same `conversation_id` → one `SaleSession`, two `SaleItem`s, persisted `conversation_id`.
12. **Different conversations isolate sessions.** Two successful add-item messages with different `conversation_id`s → two open `SaleSession`s. A later run MUST NOT attach to a historical open session from another conversation (including a leftover NULL-`conversation_id` session).
13. **Cleanup/reset integrity.** Test or reset utilities that remove a committed sale mutation MUST delete `sale_items`, `sale_sessions`, and the related `audit_events` / `outbox_events` / `idempotency_records` in the same transaction, or roll the original transaction back. Piecemeal DELETE of sales (and/or idempotency) that leaves audit/outbox pointing at missing session/item ids is forbidden. Production message UoW already commits or rolls back those rows together.

## Decisions

### D1. Slice tools, not Architecture’s full catalog

Register the three requested tools instead of `catalog.search` / `sale.commit`. Alternative: implement `sale.commit` now — rejected; payment and confirmation are out of scope.

### D2. SaleSession is draft Sale

Avoid a parallel `Sale` table. Later `sale.commit` can promote or relabel the same session. Alternative: create `sales` + `sale_lines` in confirmed shape now — rejected; that implies financial confirmation.

### D3. Application workflow owns sequencing and the write transaction

`backend/app/application/workflows` implements `AddCatalogSaleItem`. Registered tools are facades over domain services (schemas, policy metadata, independent invocation). The orchestrator MUST NOT open ORM sessions or transactions. Alternative: LLM emits a tool-call list that each auto-commits — rejected; see D10.

### D4. Directory layout

```text
backend/app/domain/catalog/
backend/app/domain/sales/
backend/app/application/commands/  # start session, add item, resolve product
backend/app/application/workflows/ # conversational add-item sequence
backend/app/agent/tools/           # registrations + adapters
mobile/lib/features/inicio/         # stream + composer wiring
mobile/lib/lumo/generative_ui/      # sale_item_added renderer
```

Foundation already placed `GenerativeUIRenderer` under `lumo/` (archived D3). Keep that. Do not add `lib/generative_ui/` from Architecture §5.

### D5. Scripted interpreter

Replace foundation `FakeLLMProvider` interpret-always-unsupported with a scripted parser for this slice (regex/rules for quantity+unit+product, Spanish abbreviations `gr`/`g`/`gramos`/`kg`/`kilogramo`/`kilogramos`). A unit-only follow-up MUST complete a pending missing-unit clarification. Alternative: vendor SDK — rejected for tests.

### D6. Money and conversion

Reuse `Money`; add `Quantity`/`normalize_mass` in domain. Round MXN to 2 decimals only in the money helper. Alternative: `unit_conversions` table — deferred.

### D7. Seed

Deterministic, idempotent fixture: business Carrota, owner membership, product Zanahoria `25.00` MXN/kg, `status=active`, no alias required. `create_app` MUST call `ensure_carrota_seed` only when `APP_ENV=local` and MUST commit it. Pytest MUST call the same helper explicitly (`APP_ENV=test` does not auto-seed at boot, so tests stay isolated). Staging and production MUST NOT insert this seed. `docker compose down -v` wipes the volume; the next local API boot re-seeds Carrota/Zanahoria but not prior `SaleSession`/`SaleItem` rows.

Manual SQL as `lumo_app` or `lumo_admin` MUST set `app.current_business_id` to the Carrota id before `SELECT` on FORCE-RLS tables, or the result is empty even when seed succeeded.

### D8. ADRs this change establishes

- ADR-013 (prepare/accept): conversational sale tools `resolve`/`start`/`add_item` as the first registered catalog.
- ADR-007 remains: all totals server-side.
- ADR-006/009 remain: LLM non-mutation; closed Generative UI.
- ADR-012 still prepared.

### D9. Error codes

Add `AMBIGUOUS_PRODUCT`, `PRODUCT_NOT_FOUND`, `UNIT_NOT_SUPPORTED` to the domain/error envelope. Conversational clarify uses agent text; structured validation still uses the envelope when the tool is invoked with bad args.

### D10. One logical write transaction for the user message

The public operation is one message (`POST /api/v1/lumo/messages` with `"900gr zanahoria"`). That message is one logical mutation.

**Required semantics:**

1. `catalog.resolve_product@1` is read-only and MUST run **before** the write transaction so an ambiguous/none/missing-unit outcome never creates a session.
2. The application workflow opens **one** write transaction that (a) creates or loads the open `SaleSession` (`sale.start@1` semantics), (b) inserts the `SaleItem` (`sale.add_item@1` semantics), (c) writes audit, outbox, and the **message-level** idempotency record, then (d) commits once. Success and `sale_item_added@1` are post-commit only.
3. If this message **creates** a session and add-item fails before commit: rollback MUST leave **neither** the new session **nor** the item, and MUST NOT commit audit/outbox/idempotency success for that mutation. Idempotency MUST remain failed or absent so a retry can execute.
4. If this message **reuses** an existing open session and add-item fails: rollback MUST leave that session unchanged (no new item, no mutation of session fields) and MUST NOT partially commit integrity rows for the failed message.
5. Message `Idempotency-Key` scopes the whole workflow (`operation_type` such as `lumo.message.add_sale_item`), not two nested committed tool operations.

**Why tools cannot each commit on the message path:** if `sale.start@1` committed an empty session and `sale.add_item@1` then failed, the user would be left with an orphan `open` session from a failed utterance. That is a partial logical effect and is forbidden for `POST /lumo/messages`.

**Independent tool invocation** (tests or a later structured API): `sale.start@1` MAY commit an empty open session when start is the public operation; `sale.add_item@1` MAY run in its own transaction against an already-committed session id. Composition on the message path MUST still use the workflow Unit of Work, not those independent commits.

**Fallback if a Unit of Work cannot wrap both facades:** do not silently commit start first. Instead, the message workflow MUST call a single application command that performs start-or-reuse **and** add-item inside one transaction, while still recording both tool ids in audit. `sale.start@1` remains registered for explicit/test starts. This fallback is allowed; two-commit composition on the message path is not.

### D11. Minimal pending clarification (missing unit only)

When the interpreter has an unequivocal product query and quantity but no unit, the runtime MUST store those fields keyed by `(business_id, actor_id, conversation_id)` and ask only for the unit. Inicio's client UUID is the `conversation_id`. It MUST NOT open a write transaction or create `SaleSession`/`SaleItem`. A later unit-only message in that same context MUST merge with the pending fields and run the normal add-item workflow. A new complete add-item utterance replaces pending state. This is not general-purpose memory and MUST NOT create schema `memory`. Process-local application state is allowed for this slice.

### D12. Local PostgreSQL host port

Canonical host mapping is `5432:5432`. Internal container port stays `5432`. README, pytest defaults, and local scripts MUST use `localhost:5432`. If host 5432 is already occupied, stop and report the conflict; do not kill the other process.

### D13. Display labels vs canonical units

Flutter formats server strings only. Map `kilogram`→`kg`, `gram`→`g`, `unit`→`unidad`, `package`→`paquete`. Golden visible row: `0.900 kg · $25.00/kg`. Do not recompute `0.900 × 25`.

### D14. Composer Enter

`LumoComposer` Enter (and the send button) MUST call the same `onSend`. Whitespace-only text MUST NOT send. Retry/idempotency behavior is unchanged.

### D15. Inicio header and greeting

Eyebrow is `LUMO · {business.name}` in uppercase from `GET /api/v1/session` (Carrota when seeded). Do not hardcode `NEGOCIO`. `Buenos días` uses Design System display greeting (Instrument Serif italic) with the Lumo text gradient. Do not redesign the screen.

### D16. Dev/debug is local/test only

`GET /api/v1/dev/carrota-token` MUST be unavailable in staging/production (`FORBIDDEN`). `X-Debug-Fail-After-Write` MUST be ignored unless `APP_ENV` is `local` or `test`.

### D17. Client-generated conversation_id on Inicio

Inicio MUST hold one UUID for the current conversational sale context and send it on every `POST /api/v1/lumo/messages`. Flutter generates the UUID; the backend persists it on `SaleSession`. Same id → reuse one open session. Different id → different open session. Do not introduce a Conversation aggregate. Alternative: server-issued conversation resource — rejected for this slice.

**Local inspection finding:** a live Carrota `SaleSession` had `conversation_id=NULL`, so later Inicio messages reused `live-golden-900gr`. Missing client id was the cause.

### D18. Sale-mutation cleanup is all-or-nothing

The message UoW already writes session, item, audit, outbox, and message idempotency in one transaction (D10). The `live-clarify-2` orphan (audit + `sale.item.added` outbox whose session/item ids no longer exist, idempotency already gone) was caused by the test helper `_clear_sales` originally deleting only sales rows (then sales + idempotency) against the shared local database — not by production rollback. Test/reset utilities MUST delete related integrity rows in the same transaction as the sales rows, or use rollback. Do not "fix" orphans by one-off DELETE of production-shaped rows without changing that path.

## Risks / Trade-offs

- [SaleSession vs later Sale] → Document mapping; do not create a second confirmed-sale table in this change.
- [Scripted interpreter overfits one utterance] → Cover `900gr`, `900 gr`, `900 g`, `900 gramos`; anything else clarifies.
- [Empty-registry tests from foundation will fail] → Update those tests to the new closed catalog.
- [Sticky composer vs keyboard] → Reuse `LumoScaffold.footer`; Enter and send share `onSend`; no layout redesign.
- [Empty catalog SELECT] → FORCE RLS + no `app.current_business_id`; not a missing-seed by itself. Document SET + local-only startup seed.
- [Partial unique index for one open session] → Unique `(business_id, actor_id, coalesced conversation_id)` WHERE `status=open`. Inicio always supplies a UUID so it never shares the NULL coalesced bucket with leftover live tests.
- [Tool-per-commit leaves orphan sessions] → D10: message path is one Unit of Work; tests must fail if a new session survives a failed add-item.
- [Test helper leaves orphan audit/outbox] → D18: reset sales and related integrity together; regression test forbids audit/outbox that reference missing sale mutations.

## Migration Plan

Alembic upgrade creates `catalog` and `sales` + RLS. Seed runs automatically only when the API boots with `APP_ENV=local`; tests seed explicitly; staging/production never seed. Rollback: downgrade those migrations; Inicio composer can be feature-flagged off if needed. No production tenant.

## Open Questions

1. Whether later `sale.commit` mutates the same `SaleSession` row or inserts a confirmed `Sale` — deferred, mapping recorded in D2.
2. Production LLM provider — still deferred.
3. Whether `conversation_id` becomes a persisted Conversation aggregate — not in this change. This slice uses a client-generated UUID only (D17).
