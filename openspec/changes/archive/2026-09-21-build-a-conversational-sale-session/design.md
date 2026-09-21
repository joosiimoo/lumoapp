## Context

`build-a-conversational-sale-foundation` is archived. The backend can interpret one catalog line (`900gr zanahoria`), persist a `SaleItem` on one open `SaleSession` scoped to `(business_id, actor_id, conversation_id)`, and render `sale_item_added@1`. Session status is `open` only (`ck_sale_sessions_status` and unique index `WHERE status = 'open'`). Seeded catalog is Carrota + Zanahoria `25.00` MXN/kg. Papa is intentionally absent. `sale.commit@1` is unregistered. Flutter already receives `session_item_count` and `session_total` but does not display them.

This change evolves that foundation into a usable conversational sale session: multiple items, a representative catalog, explicit totalize, and `ready_to_charge` — still without payment.

Authority: Build A PRD/SRS/Architecture/Design System v1.0. PRD v0.11 is vision only. ADRs 001–013 remain accepted; ADR-012 stays prepared (outcomes still unregistered).

Inspection notes that constrain design:

- `sale.add_item@1` output already includes `session_item_count` and `session_total` derived from persisted items. Do not add a duplicated mutable total column.
- Scripted parser treats `2 galletas A` as quantity + product with missing unit. Kilogram missing-unit clarification MUST stay. Count-product completion MUST happen after catalog resolve in the application workflow, not in the interpreter.
- `SalesRepository.get_open_session` filters `status=open`. After totalize, add-item MUST look up the active session (`open` or `ready_to_charge`) so it rejects instead of creating a second open session.
- `sales.sale_sessions.conversation_id` is `VARCHAR(128) NULL` (not UUID). Migration `0002_catalog_sales` created `uq_sale_sessions_open_context` on `(business_id, actor_id, COALESCE(conversation_id, '')) WHERE status = 'open'`. `0003` MUST keep that expression and only widen the predicate to `status IN ('open', 'ready_to_charge')`.

## Goals / Non-Goals

**Goals:**

- Prove Lumo owns a sale workflow across turns: accumulate items, know the total, totalize to ready-to-charge.
- Keep conversation as the control plane; Flutter only renders server values.
- Stay compatible with a future `LLMProvider` (scripted interpreter remains local/test).

**Non-Goals:**

- Payment, `sale.commit@1`, confirmed Sale, operational day, close, cash, history, export, overrides, discounts, unknown products, multi-product utterances, catalog CRUD UI, inventory, item edit/remove, cancel, reopen, voice, camera, vendor LLM, outcomes.

## Conflicts with the current active baseline

| Baseline | Conflict | Resolution |
|---|---|---|
| `sales-session-foundation`: status `open` only | Need `ready_to_charge` | Delta: allow `open` \| `ready_to_charge`. Do not introduce PRD `confirmed` |
| `sales-session-foundation`: unique open session | Ready session would allow a second open row | Keep `0002` index expression `COALESCE(conversation_id, '')`; widen `WHERE` to `status IN ('open', 'ready_to_charge')` |
| `ai-native-contracts`: three product tools | Totalize needs a tool | Register `sale.totalize@1`. Keep `sale.commit@1` unregistered |
| PRD §8.1 `draft → pending_information → confirmed` | Requested `ready_to_charge` | `open` remains draft-equivalent. `ready_to_charge` is a pre-payment gate owned by this slice. `confirmed` waits for payment/`sale.commit` |
| Architecture §10.1 `sale.commit` includes payment | Totalize is not payment | New tool `sale.totalize@1`; commit stays later |
| PRD §10.5 `sale_draft_card` / `sale_confirmed_card` | Need a totalized summary without payment UI | New contract `sale_summary@1`. Map to Design System sale-prepared **structure** (status chip, product rows, total) **without** payment chips, Registrar, or Corregir |
| `sale-item-added-ui` version 1 | Need accumulated state | Keep version 1; Flutter starts displaying existing `session_item_count` / `session_total` |
| `conversational-sale-runtime`: missing unit never resolves first | `2 galletas A` must complete | Application resolve-first for missing unit; infer `unit`/`package` only after unique match. Never infer kilogram |
| Architecture §23 full sales module | Combined thin slice | Intentional: session workflow, not payment or close |

## Assumptions

1. Interaction context remains `(business_id, actor_id, conversation_id)` when present. Inicio continues to send a stable client UUID.
2. Local/test use the scripted interpreter; no vendor LLM SDK.
3. Seed prices are exact Decimal fixtures: Zanahoria `25.00`/kg, Tomate `20.00`/kg, Galleta A `12.00`/unit. Golden lines: `900gr zanahoria` → `22.50`; `500gr tomate` → `10.00`; `2 galletas A` → `24.00`. Two-item total `32.50`; three-item `56.50`.
4. Galleta A alias `galletas a` is required because normalization is exact match (`galletas a` ≠ `galleta a`). No stemming in this change.
5. Papa remains unseeded as the unknown-product case.
6. Permission for totalize is `sale.create` (same as add-item).
7. `POST /api/v1/lumo/messages` remains the only public conversational entry.
8. Clarifications stay HTTP 200 agent text, not `409`, because conversation is the surface.
9. Session currency remains the business currency (MXN for Carrota).
10. Orchestrator still does not open ORM sessions. Application workflows own write transactions.
11. One product line per utterance.
12. Totalize synonyms are only `totalizar`, `total`, and `el total` (trim, case-insensitive). Do not treat `cobrar` or `pagar` as totalize.
13. Item edit/remove is not required for the state transition and is deferred.
14. `subtotal` equals `total` because discounts are out of scope.

## Exact entities and state transitions

### Product (`catalog.products`)

Unchanged shape. Seed adds Tomate and Galleta A. Alias row only for Galleta A.

### SaleSession (`sales.sale_sessions`)

Fields unchanged: `id`, `business_id`, `actor_id`, `conversation_id`, `status`, `currency`, timestamps. No `total` column.

| From | Event | To | Notes |
|---|---|---|---|
| (none) | message add-item creates session + item, commit | `open` | existing one-tx rule |
| `open` | add-item success | `open` | item appended |
| `open` | `sale.totalize@1` with ≥1 item, commit | `ready_to_charge` | lock row; one tx with audit/outbox/idempotency |
| `open` | totalize with 0 items | `open` | deny; no mutation |
| (none) | totalize with no session | (none) | deny; do not create a session |
| `ready_to_charge` | totalize same original idempotency key | `ready_to_charge` | replay original persisted response |
| `ready_to_charge` | totalize different idempotency key | `ready_to_charge` | non-mutating read-back; current `sale_summary@1`; no second outbox, transition audit, or idempotency row |
| `ready_to_charge` | add-item | `ready_to_charge` | deny; no new item; no new session |
| `ready_to_charge` (conv A) | add-item on conv B | new `open` for B | isolated by conversation_id |

Out of scope: `pending_information` as a persisted session status, `confirmed`, `voided`, `paid`.

Pending missing-unit remains process-local application state (existing D11), not `SaleSession.status`.

### SaleItem (`sales.sale_items`)

Still append-only. Created only for `open` sessions. Survives the totalize transition. No edit/delete in this change.

## Exact tool contracts

Shared: JSON snake_case; money `{ "amount": "<decimal-string>", "currency": "MXN" }`; tenant from session.

Existing tools keep their contracts. Deltas:

### `sale.start@1`

Output `status` MAY be `open` or `ready_to_charge` when reporting an existing active session. Start MUST NOT create a second session for a `ready_to_charge` context.

### `sale.add_item@1`

MUST lock the existing `SaleSession` row (`SELECT ... FOR UPDATE`) before checking status, then reject if status is not `open` (`SALE-002`). Output already includes `session_item_count` and `session_total`.

### `sale.totalize@1` (new)

- permission: `sale.create` · side_effect: `write` · idempotency: true for the **transition**; read-back on `ready_to_charge` is non-mutating · policies: `SALE-003`, `INT-001`

Input: `{ "conversation_id": string | null }`

Output: `{ "sale_session_id", "status": "ready_to_charge", "currency", "item_count", "subtotal", "total", "items": [ { "sale_item_id", "product_name", "quantity_normalized", "unit_normalized", "unit_price", "line_total" } ] }`

**SALE-003:** an `open` → `ready_to_charge` **transition** requires `status=open` and ≥1 `SaleItem`. `ready_to_charge` is allowed only as a stable read-back/no-op, not as a second transition.

**Transition path** (`open` + ≥1 item): lock the session row; re-read status and items while locked; Decimal total; one application write transaction (status + `sale.totalize@1` audit + `sale.ready_to_charge` outbox + `lumo.message.totalize_sale` idempotency); compose `sale_summary@1` only after commit.

**Same original idempotency key:** replay the original persisted response. No second transition or outbox.

**Different idempotency key on `ready_to_charge`:** non-mutating read-back of current state (D19). Return current `sale_summary@1`. Do not write a new idempotency record, transition audit, or outbox event. The HTTP route still requires `Idempotency-Key`; persistence of that key is not required because there is no mutation.

`sale.commit@1` stays unregistered.

`AgentDecision` gains intent `totalize_sale`. Existing add-item fields remain.

## Exact Generative UI contracts

### `sale_item_added@1`

Unchanged JSON. Flutter MUST display `session_item_count` and `session_total` (footer on the existing product row card). No version bump.

### `sale_summary@1` (new)

See `specs/sale-summary-ui/spec.md`. Visual: Design System §4.11 structure minus payment section and actions; §4.14 product rows; §4.21 status chip. Chip copy is server `fallback_text` / status `ready_to_charge` rendered as "Lista para cobrar". No payment chips.

## Acceptance tests

1. **Multi-item same conversation.** `900gr zanahoria` then `500gr tomate` → one open session, two items, total `32.50`.
2. **Unit-priced product.** `2 galletas A` on that session → third item `24.00`, session total `56.50`.
3. **Clarification inside active sale.** After Zanahoria, `500 tomate` asks unit; `gr` adds Tomate to the same session; no write on the first turn.
4. **Totalize.** `totalizar` → `ready_to_charge`, `sale_summary@1`, summary total equals sum of persisted items.
5. **Idempotent totalize.** Replay same `Idempotency-Key` → original persisted body, one transition, one outbox.
6. **Totalize empty.** No session/items → clarification, no mutation.
7. **Item after ready_to_charge.** `900gr zanahoria` → rejection, no new item, status unchanged.
8. **Different conversation.** New `conversation_id` after ready → new open session; does not reuse the ready session.
9. **Unknown product.** `900gr papa` during an open sale → no persist, sale undamaged.
10. **Integrity rollback.** Forced failure during totalize or add-item rolls back domain + audit + outbox + idempotency.
11. **RLS.** Business B cannot read/write Carrota sessions or items.
12. **Flutter.** Renders accumulated add-item totals and `sale_summary@1` from payload fields; does not add line totals.
13. **Different-key no-op totalize.** After ready, a new `Idempotency-Key` returns current `sale_summary@1` without a second outbox, transition audit, or new `lumo.message.totalize_sale` row.
14. **Concurrent add-item vs totalize.** Both target the same open session; they serialize on the row lock; final state is either (item included then totalized) or (totalize first, add rejected). No item may persist after `ready_to_charge`. Summary total equals items committed before the transition.

Also retain existing golden Zanahoria, missing-unit, and two-conversation isolation tests.

## Decisions

### D1. `ready_to_charge` is not `confirmed`

PRD confirmation includes payment and `sale.commit`. This slice needs an explicit "ready to charge" gate so Lumo owns workflow state without recording money movement. Alternative: jump to `confirmed` — rejected; that would falsify financial confirmation.

### D2. New tool `sale.totalize@1`, not `sale.commit@1`

Architecture `sale.commit` writes sale + payment + operational day. Reusing that name would overload the later contract. Alternative: register `sale.commit@1` with payment omitted — rejected.

### D3. `sale_summary@1`, not `sale_ready_to_charge@1`

Status belongs in `data.status`. The card is a structured summary. Naming it after the state would force a new component if a later slice shows the same summary in another status. Alternative: `sale_draft_card` — rejected; previous slice already chose event-like names (`sale_item_added`) over PRD card names.

### D4. Keep `sale_item_added@1` at version 1

The contract already has accumulated fields. A v2 bump would break Inicio for no schema reason. Flutter display is the missing piece.

### D5. No duplicated session total column

Line totals are already snapshotted on each `SaleItem`. Session total is a pure sum. Alternative: persist `total` at totalize time — unnecessary; items cannot change in this slice after ready, and summing is deterministic.

### D6. Reject add-item after ready; do not reopen

Simplest safe default. Silent reopen would hide that the merchant already totalized. New `conversation_id` is the way to start another sale. Edit/remove/reopen are a later change.

### D7. Count-product unit is completed after unique resolve

The interpreter MUST NOT know catalog `sale_unit`. Application workflow resolves first when quantity + product are present and unit is missing. Infer `unit`/`package` only. Never infer `kilogram`. Alternative: require `2 unidades galleta A` — rejected; the product example is `2 galletas A`.

### D8. Galleta A alias instead of stemming

Exact normalized match stays the catalog rule. Alias `galletas a` is the minimum to make the golden utterance unique. General pluralization is deferred.

### D9. Seed prices

Tomate `20.00` MXN/kg and Galleta A `12.00` MXN/unit keep every golden line on two-decimal money without repeating Zanahoria's `25.00`. Papa stays unseeded.

### D10. Application workflows

Keep `AddCatalogSaleItem` and add `TotalizeSaleSession` under `backend/app/application/workflows/`. Orchestrator routes on intent. Do not merge into one god-workflow. Directory layout from ADR-013 / previous D4 stays.

### D11. Lookup active session, not only open

`SalesPort` MUST expose getting and **locking** the active session for the interaction context (`open` or `ready_to_charge`) with PostgreSQL `SELECT ... FOR UPDATE` (SQLAlchemy `with_for_update()`). `get_open_session` without a lock is insufficient after this change. The lock MUST be taken before validating mutable workflow status.

### D12. Idempotency operation types

Add-item remains `lumo.message.add_sale_item`. Totalize uses `lumo.message.totalize_sale`. Mixing them would replay the wrong body.

### D13. Policies SALE-002 and SALE-003

Workflow gates in the existing SALE-* family. Do not add schema `workflow`.

- `SALE-002`: add-item only while `open` (evaluated after the session row is locked).
- `SALE-003`: an `open` → `ready_to_charge` **transition** requires `open` and ≥1 item. A `ready_to_charge` totalize is not a transition; it is an allowed stable read-back. Empty/missing sale remains blocked.

### D14. ADR this change establishes

- ADR-014 (prepare/accept): `SaleSession` `open` → `ready_to_charge` via `sale.totalize@1`; `sale.commit@1` remains payment/confirmation.
- ADR-013 remains: conversational tools; message path owns the UoW.
- ADR-007/006/009 remain: server math, LLM non-mutation, closed Generative UI.
- ADR-012 still prepared.

### D15. Error / clarify codes

Add `SALE_NOT_OPEN` and `SALE_EMPTY` for structured tool invocation. Conversational path still returns HTTP 200 agent text.

### D16. Visual mapping

Reuse `LumoCard`, product row, and status chip. Do not implement Design System payment chips or Registrar. Do not redesign Inicio.

### D17. `openspec/config.yaml`

Update project context so later artifacts know `sale.totalize@1` and `sale_summary@1` are the active closed catalog additions, and that `ready_to_charge` is an allowed session status.

### D18. Serialize add-item and totalize with a row lock

`AddCatalogSaleItem` and `TotalizeSaleSession` MUST serialize mutations on an **existing** `SaleSession` using PostgreSQL `SELECT ... FOR UPDATE` (SQLAlchemy `with_for_update()`) on that row, inside the application write transaction, **before** validating mutable status.

Add-item: lock → re-read status → insert only if still `open`, else reject.

Totalize: lock → re-read status → if `open` with items, read those items while locked, Decimal-sum, transition, commit status+audit+outbox+idempotency atomically; if already `ready_to_charge`, read-back without mutating.

Two concurrent first-creates of a session remain serialized by the unique index. Do not introduce Redis, advisory-lock-only session mutexes, or other infrastructure. (Idempotency already uses `pg_advisory_xact_lock` for key uniqueness; that does not serialize two different keys against one session.)

### D19. Different-key totalize on ready_to_charge is a non-mutating read-back

The public route still requires `Idempotency-Key`. Persistence of that key is required only when the request is a mutation.

- Same original key + hash: replay the completed `lumo.message.totalize_sale` body (existing integrity-foundation contract).
- Different key after `ready_to_charge`: return current `sale_summary@1` from persisted items. Do **not** insert a new idempotency row, transition audit, or `sale.ready_to_charge` outbox row. There is no mutation, so the message idempotency contract does not require a new record.
- Alternative considered: complete a new idempotency row with the current summary — rejected; it writes platform state for a read and is not needed for replay of the original transition.

## Risks / Trade-offs

- [Ready_to_charge vs later confirmed] → Document mapping in D1/ADR-014; do not create a Sale table.
- [Merchant wants to add an item after totalize] → Clear rejection copy; reopen/edit deferred.
- [Interpreter overfits totalize synonyms] → Closed list of three phrases; anything else clarifies.
- [Plural matching only via alias] → Document; `2 galleta A` still matches the product name if used.
- [Widening unique index] → `0003` drops `uq_sale_sessions_open_context` and recreates the same expression with a wider `WHERE`. `conversation_id` stays `VARCHAR(128)`; `COALESCE(..., '')` remains valid. Do not change the column type.
- [Missing-unit path now resolves first] → Kilogram products still clarify; must not persist on that read.
- [Concurrent add vs totalize without a lock] → D18: `FOR UPDATE` on the session row before status checks.
- [Different-key totalize writing a second idempotency row] → D19: read-back only; original key still replays.

## Migration Plan

Alembic `0003_sale_session_ready_to_charge`:

1. Replace `ck_sale_sessions_status` so status IN (`open`, `ready_to_charge`).
2. `DROP INDEX` `sales.uq_sale_sessions_open_context`.
3. Recreate uniqueness with the **same** `0002` expression, only widening the predicate:

```sql
CREATE UNIQUE INDEX uq_sale_sessions_active_context
ON sales.sale_sessions (business_id, actor_id, COALESCE(conversation_id, ''))
WHERE status IN ('open', 'ready_to_charge');
```

Do not change `conversation_id VARCHAR(128) NULL`. Do not add a session total column. No new schemas. Seed helper becomes idempotent for Tomate and Galleta A. Rollback: downgrade 0003; Inicio can ignore unknown `sale_summary` via fallback_text. No production tenant.

## Open Questions

1. Whether later payment mutates the same `ready_to_charge` session into `confirmed` or inserts a `Sale` / `Payment` — deferred, mapping recorded in D1.
2. Whether a future slice allows reopen/edit of `ready_to_charge` — deferred; this change rejects add-item.
3. Production LLM provider — still deferred.
4. Whether `conversation_id` becomes a Conversation aggregate — still not in this change.
