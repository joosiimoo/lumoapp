## 1. Domain session state

- [x] 1.1 Extend `SaleSessionStatus` with `ready_to_charge`. Add a domain rule that new items are allowed only while `open`. The **transition** `open` → `ready_to_charge` is allowed only from `open` with at least one item; `ready_to_charge` totalize is a stable read-back, not a second transition. Unit-test legal and illegal transitions with no SQLAlchemy imports.
- [x] 1.2 Add a domain helper that sums persisted `SaleItem.line_total` values with `Money` / Decimal (no float) and returns `session_total`. Unit-test `22.50 + 10.00 = 32.50` and `32.50 + 24.00 = 56.50`.

## 2. Persistence

- [x] 2.1 Alembic `0003_sale_session_ready_to_charge`: change `ck_sale_sessions_status` to `('open', 'ready_to_charge')`; `DROP INDEX` `sales.uq_sale_sessions_open_context` from `0002_catalog_sales`; recreate uniqueness with the **same** expression `(business_id, actor_id, COALESCE(conversation_id, ''))` because `conversation_id` is `VARCHAR(128) NULL`, not UUID, `WHERE status IN ('open', 'ready_to_charge')`. Do not change the column type. Do not add a session total column. Do not create `operations`, `workflow`, or `memory`.
- [x] 2.2 Update SQLAlchemy `SaleSessionRow` check constraint and repositories: add `get_active_session` for `open` or `ready_to_charge` that loads with `SELECT ... FOR UPDATE` (`with_for_update()`) before status checks; keep add-item inserting only against `open` after that lock; add `update_session_status` used only by totalize inside the same Unit of Work.

## 3. Catalog seed

- [x] 3.1 Extend `ensure_carrota_seed` to idempotently insert Tomate (`kilogram`, `per_kilogram`, `20.00` MXN) and Galleta A (`unit`, `per_unit`, `12.00` MXN) plus alias `galletas a`. Do not seed Papa. Keep Zanahoria unchanged.
- [x] 3.2 Unit/integration tests: resolve `tomate`, `galleta a`, and `galletas a` uniquely; resolve `papa` as none; cross-tenant resolve still empty.

## 4. Policies, errors, and AgentDecision

- [x] 4.1 Register policies `SALE-002` (add-item only while session is `open`) and `SALE-003` (`open` + ≥1 item required for the **transition**; `ready_to_charge` totalize is an allowed stable read-back/no-op) on `FoundationPolicyEngine`.
- [x] 4.2 Add error types/envelope codes `SALE_NOT_OPEN` and `SALE_EMPTY`. Conversational denials remain HTTP 200 agent text.
- [x] 4.3 Allow `AgentDecision.intent=totalize_sale` with `candidate_tool=sale.totalize@1`. Invalid payloads still discard with no mutation.

## 5. Interpreter

- [x] 5.1 Teach the scripted interpreter the closed synonyms `totalizar`, `total`, and `el total` (trim, case-insensitive) → `totalize_sale` / `sale.totalize@1`. Do not map `cobrar` or `pagar`. No repository access.
- [x] 5.2 Keep quantity+product-without-unit as `add_sale_item` with `missing_fields=["unit"]` so the application can resolve-first. Do not infer kilogram or prices in the interpreter.

## 6. Add-item workflow

- [x] 6.1 In `AddCatalogSaleItem`, lock the active session for the conversation (`FOR UPDATE`) then re-read status. If `ready_to_charge`, return a resolution-oriented denial, write no item, and create no second session. Insert a `SaleItem` only if the locked session is still `open`.
- [x] 6.2 When quantity and product are present but unit is missing: resolve as a read first. If unique and `sale_unit` is `unit` or `package`, complete add-item with that unit. If unique and `sale_unit` is `kilogram`, keep pending missing-unit clarification and write nothing. If none/ambiguous, clarify without writing.
- [x] 6.3 Preserve the existing one write transaction for start/reuse + add-item + audit + `sale.item.added` + `lumo.message.add_sale_item`. Compose `sale_item_added@1` only after commit, including `session_item_count` and `session_total`.

## 7. Totalize tool and workflow

- [x] 7.1 Register `sale.totalize@1` with the spec input/output schema, permission `sale.create`, side_effect write. Idempotency is required for the `open` → `ready_to_charge` transition. Keep `sale.commit@1` unregistered.
- [x] 7.2 Implement `TotalizeSaleSession` in `backend/app/application/workflows/`: if the original `lumo.message.totalize_sale` key is completed, replay that body. Otherwise lock the active session (`FOR UPDATE`) and re-read status. Deny empty/missing. If already `ready_to_charge`, return current `sale_summary@1` without a second outbox, transition audit, or new idempotency row. If `open` with items, read items while locked, Decimal-sum, then one write transaction (status, `sale.totalize@1` audit, `sale.ready_to_charge` outbox, `lumo.message.totalize_sale` idempotency). Success only after commit. Orchestrator MUST NOT open the transaction.
- [x] 7.3 Wire the orchestrator to route `totalize_sale` to `TotalizeSaleSession` and `add_sale_item` to the existing workflow. Check `ready_to_charge` before storing pending missing-unit state.

## 8. Generative UI backend

- [x] 8.1 Register `sale_summary@1`. Compose it after a committed totalize **transition**, and also as the current-state payload for a `ready_to_charge` read-back, using server item rows, `item_count`, `subtotal=total`, status `ready_to_charge`, and fallback_text. `actions=[]`. Refuse `sale_confirmed_card` and `sale_ready_to_charge@1`.

## 9. Flutter renderer and Inicio

- [x] 9.1 Display `session_item_count` and `session_total` on `sale_item_added@1` without bumping the version and without client math.
- [x] 9.2 Map `sale_summary@1` in `GenerativeUIRenderer` to Lumo mark + compact `LumoCard` (status chip, product rows, total row). Format server strings only; unknown version shows `fallback_text`. No payment chips, Registrar, Corregir, or table layout. Do not redesign Inicio.
- [x] 9.3 Keep Inicio posting `conversation_id` on every turn including `totalizar`. Flutter tests for accumulated add-item values, summary render, and no local summing.

## 10. Integrity helpers and config

- [x] 10.1 Extend `sale_cleanup` to delete `sale.totalize@1` audit, `sale.ready_to_charge` outbox, and `lumo.message.totalize_sale` idempotency together with sales rows.
- [x] 10.2 Update `openspec/config.yaml` context: registered tools include `sale.totalize@1`; registered UI includes `sale_summary@1`; session statuses are `open` and `ready_to_charge`; this change is the active product slice.
- [x] 10.3 Write ADR-014 (`open` → `ready_to_charge` via `sale.totalize@1`; `sale.commit@1` remains payment). Do not implement payment, commit, operational day, export, catalog CRUD, or item edit/remove.

## 11. Acceptance tests

- [x] 11.1 Scenario 1–2: same conversation adds Zanahoria then Tomate (`32.50`); then `2 galletas A` (`24.00` line, session `56.50`). One session while `open`.
- [x] 11.2 Scenario 3: open sale, `500 tomate` clarifies unit with no write, `gr` adds Tomate `10.00` to the existing session.
- [x] 11.3 Scenario 4–5: `totalizar` transitions `open` → `ready_to_charge`, returns `sale_summary@1` whose total equals the sum of persisted items; replay same idempotency key returns the original persisted body with no second outbox.
- [x] 11.4 Scenario 6–8 and different-key no-op: empty totalize does not mutate; add-item after ready is rejected with no new item; a new `conversation_id` creates a new `open` session and does not reuse the ready one; a different idempotency key on `ready_to_charge` returns current `sale_summary@1` with no second outbox, transition audit, or new `lumo.message.totalize_sale` row.
- [x] 11.5 Scenario 9–11: `900gr papa` does not persist and does not damage the sale; forced totalize/add-item failure rolls back domain + audit + outbox + idempotency; cross-business reads/writes are denied.
- [x] 11.6 Scenario 12: Flutter tests assert add-item accumulated values and summary totals come from payload fields and that the widget tree does not multiply or sum money.
- [x] 11.7 Concurrent add-item vs totalize against the same open session: operations serialize on the row lock; final state is deterministic (item included then totalized, or totalize first and add rejected); no `SaleItem` persists after `ready_to_charge`; summary total equals items committed before the transition.
