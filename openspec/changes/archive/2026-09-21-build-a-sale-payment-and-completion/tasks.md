## 1. Domain session and payment

- [x] 1.1 Extend `SaleSessionStatus` with `confirmed`. Add `PaymentMethod` (`cash` | `card` | `transfer`) and frozen `Payment` (id, business_id, sale_session_id, actor_id, method, amount, currency, status=`recorded`, source=`manual_capture`). Domain MUST NOT import SQLAlchemy. Unit-test enum membership.
- [x] 1.2 Add domain rules: commit transition is allowed only from `ready_to_charge`; confirmed commit is a read-back; add-item targeting `confirmed` is illegal; payment amount MUST equal the Decimal session total. Unit-test legal/illegal transitions and `22.50+10.00+24.00 → 56.50` with no float.

## 2. Persistence

- [x] 2.1 Alembic `0004_sale_session_confirmed_payment` revising `0003_ready_to_charge`: replace `ck_sale_sessions_status` with `('open', 'ready_to_charge', 'confirmed')`. Do **not** alter `uq_sale_sessions_active_context`. Do not add a session total or payment_method column. Do not create `sales.sales`, `sale_lines`, `operations`, `workflow`, or `memory`.
- [x] 2.2 In the same migration create `sales.payments` (`id`, `business_id`, `sale_session_id` FK to `sale_sessions.id` only, `actor_id`, `method` CHECK cash/card/transfer, `amount numeric(12,2)`, `currency`, `status` CHECK recorded, `source` CHECK manual_capture, timestamps), UNIQUE (`sale_session_id`), ENABLE+FORCE RLS, `tenant_isolation` policy, grants to `lumo_app`. Do not add a composite `(business_id, sale_session_id)` foreign key.
- [x] 2.3 Update SQLAlchemy models and `SalesPort`/`SalesRepository`: `SaleSessionRow` check includes `confirmed`; `PaymentRow`; `add_payment`; `get_latest_confirmed_session` for the interaction context; `get_active_session` remains `open` | `ready_to_charge` with `FOR UPDATE`. `sale.start@1` output `status` stays `open` | `ready_to_charge` and MUST NOT return `confirmed`. Commit MUST lock the active row under `TenantContext` before `add_payment`. `add_payment` MUST copy `business_id` from `tenant.business_id`, reject a mismatch with the locked session, and MUST NOT take `business_id` from client/tool input. Cross-tenant payment queries MUST return nothing.

## 3. Policies, errors, and AgentDecision

- [x] 3.1 Register `SALE-004` (commit transition only from `ready_to_charge`; `confirmed` is allowed read-back) and `PAY-001` (closed-enum method required; do not infer cash) on `FoundationPolicyEngine`. Add `sale.commit@1` to the registered tool set used by SEC-002 tests.
- [x] 3.2 Add error types/envelope codes `SALE_NOT_READY_TO_CHARGE`, `SALE_NOT_FOUND`, and `PAYMENT_METHOD_UNKNOWN`. Conversational denials remain HTTP 200 agent text.
- [x] 3.3 Allow `AgentDecision.intent=commit_sale`, optional `payment_method` (`cash` | `card` | `transfer`), and `candidate_tool=sale.commit@1`. Invalid payloads still discard with no mutation.

## 4. Interpreter

- [x] 4.1 Teach the scripted interpreter the closed phrases (trim, case-insensitive): cash `efectivo` / `pagar en efectivo` / `en efectivo`; card `tarjeta` / `pagar con tarjeta` / `con tarjeta`; transfer `transferencia` / `pagar por transferencia` / `pagar con transferencia` / `por transferencia` → `commit_sale` / `sale.commit@1` / matching `payment_method`. No repository access.
- [x] 4.2 `pagar`, `cobrar`, mixed-method phrases, and unrecognized text MUST NOT commit. `pagar` alone MUST clarify methods. Combined item+payment utterances remain unsupported. Keep existing add-item and totalize paths.

## 5. Commit workflow

- [x] 5.1 Register `sale.commit@1` with the spec input/output schema, permission `sale.create`, side_effect write. Idempotency required for the `ready_to_charge` → `confirmed` transition. Amount MUST NOT be in the input schema.
- [x] 5.2 Implement `CommitSaleSession` in `backend/app/application/workflows/commit_sale_session.py`. If the original `lumo.message.commit_sale` key is completed, replay that body. Otherwise lock the active session (`FOR UPDATE`) and re-read status. Deny `open` (`SALE_NOT_READY_TO_CHARGE`) and missing sale (`SALE_NOT_FOUND`) with no Payment. If latest session is `confirmed` and no active session exists, return current `sale_confirmed@1` without a second Payment, outbox, transition audit, or new idempotency row.
- [x] 5.3 Transition path: while the session is locked under the tenant, Decimal-sum items, insert one `Payment` (`business_id` from that tenant/session, amount = total, status recorded, source manual_capture), set `confirmed`, write `sale.commit@1` audit, enqueue `sale.confirmed` and `payment.recorded`, complete `lumo.message.commit_sale` in one application-owned write transaction. Success only after commit. Orchestrator MUST NOT open the transaction. Forced failure MUST roll back status, Payment, audit, outbox, and idempotency.

## 6. Orchestrator and add-item after confirmed

- [x] 6.1 Wire `FoundationOrchestrator` and the message route to inject `CommitSaleSession`. Route `commit_sale` / `sale.commit@1` to that workflow before add-item or totalize.
- [x] 6.2 Keep add-item to a **single** `get_active_session(for_update=True)` in its write transaction. CASE A: lookup returns `ready_to_charge` → deny under `SALE-002`, persist no item, do not re-query to start a new sale in that request. CASE B: lookup returns none because commit already confirmed → MAY create a new `open` session (Sale B); Sale A stays immutable. Tool-level `sale.add_item@1` against a confirmed `sale_session_id` MUST deny. Preserve the existing one write transaction for start/reuse + add-item.

## 7. Generative UI backend

- [x] 7.1 Register `sale_confirmed@1`. Compose it after a committed commit **transition**, and as the current-state payload for a `confirmed` read-back, using server items, `item_count`, `total`, `payment` (method, amount, recorded), status `confirmed`, and `fallback_text`. `actions=[]`. Do not emit `sale_summary@1` after commit. Refuse `sale_confirmed_card@1` and `sale_completed@1`.

## 8. Flutter renderer and Inicio

- [x] 8.1 Map `sale_confirmed@1` in `GenerativeUIRenderer` to Lumo mark + compact `LumoCard` (registered status, item count, total, method label Efectivo/Tarjeta/Transferencia, payment amount). Format server strings only; unknown version shows `fallback_text`. No payment chips, Registrar, Corregir, Deshacer, or client math.
- [x] 8.2 Keep Inicio posting the same `conversation_id` on payment phrases and the next product utterance after `sale_confirmed@1`. Do not rotate the UUID. Flutter tests for confirmed render, same conversation_id across payment + next item, and no local summing.

## 9. Integrity helpers, config, and ADR

- [x] 9.1 Extend `sale_cleanup` to delete `sales.payments` with `sale_items`/`sale_sessions`, plus `sale.commit@1` audit, `sale.confirmed` / `payment.recorded` outbox, and `lumo.message.commit_sale` idempotency, in one transaction. Orphan helper MUST also check `payment_id`.
- [x] 9.2 Update `openspec/config.yaml` context: registered tools include `sale.commit@1`; registered UI includes `sale_confirmed@1`; session statuses are `open`, `ready_to_charge`, and `confirmed`; Payment exists in `sales.payments`.
- [x] 9.3 Write ADR-015 (`ready_to_charge` → `confirmed` via `sale.commit@1` with one `Payment`; confirmed `SaleSession` is the durable sale; `conversation_id` does not rotate). Do not implement Daily Close, OperationalDay, change due, refunds, catalog CRUD, or item edit/remove.

## 10. Acceptance tests

- [x] 10.1 Scenarios 1–3: build the three-item sale, `totalizar`, then `efectivo` / `tarjeta` / `transferencia`. Each MUST persist one Payment with the matching method, amount `56.50`, status `confirmed`, and `sale_confirmed@1`.
- [x] 10.2 Scenarios 4–6: `efectivo` on an open sale clarifies with no Payment; payment with no sale clarifies with no mutation; `cheque` or `pagar` clarifies methods with no mutation.
- [x] 10.3 Scenarios 7–8: same `Idempotency-Key` replay returns the original body with one Payment and one `sale.confirmed` outbox; a different key after confirmed returns current `sale_confirmed@1` with no second Payment, outbox, transition audit, or new `lumo.message.commit_sale` row.
- [x] 10.4 Scenarios 9–10: tool add-item against the confirmed session id does not append; message-path `900gr zanahoria` on the same `conversation_id` after confirmed creates a new `open` session; the previous confirmed sale and Payment remain immutable.
- [x] 10.5 Scenario 11: two concurrent `efectivo` requests serialize to one Payment and one confirmation. Add-item vs commit: CASE A (add-item locks `ready_to_charge` first) rejects with no item and no new session; CASE B (commit confirms first) leaves Sale A immutable and MAY attach the racing item only to a new open Sale B. Use the existing thread-pool pattern from `test_concurrent_add_item_vs_totalize` for both orderings when practical.
- [x] 10.6 Scenarios 12–13: business B cannot read/write Carrota payments; `add_payment` with a mismatched `business_id` or foreign session MUST fail before commit with no Payment row; forced failure during commit rolls back confirmed status, Payment, audit, outbox, and idempotency.
- [x] 10.7 Scenario 14: Flutter tests assert confirmed total, method, and payment amount come from payload fields and that the widget tree does not add line totals or compute change.
