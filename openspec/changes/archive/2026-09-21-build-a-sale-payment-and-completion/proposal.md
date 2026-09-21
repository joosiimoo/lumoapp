## Why

The archived conversational-sale session can totalize to `ready_to_charge`, but Lumo cannot finish the operational sale. PRD §7.6 and §8.1 plus Architecture §10.2 require an explicit payment method, a recorded `Payment`, and `sale.commit` that confirms the sale. This slice proves Lumo can charge, complete, and leave the conversation ready for the next customer — still without Daily Close.

## What Changes

- Register `sale.commit@1` and application workflow `CommitSaleSession`. Closed Spanish phrases `efectivo` / `pagar en efectivo` / `en efectivo`, `tarjeta` / `pagar con tarjeta` / `con tarjeta`, and `transferencia` / `pagar por transferencia` / `pagar con transferencia` / `por transferencia` commit a `ready_to_charge` session. Do not treat `pagar`, `cobrar`, or mixed-method phrases as commit.
- Persist a separate `Payment` (`sales.payments`) with method `cash` | `card` | `transfer`, amount equal to the current sale total, currency, status `recorded`, actor, and timestamps. One payment per sale in this change.
- Transition `SaleSession` `ready_to_charge` → `confirmed` (PRD §8.1). Do not introduce a separate `sales.sales` / `sale_lines` table yet: a confirmed `SaleSession` plus its `SaleItem`s is the durable completed sale for this slice (foundation mapping: `SaleSession` = Sale in draft).
- Register Generative UI `sale_confirmed@1`. Do not reuse `sale_summary@1`. Flutter renders server values and MUST NOT calculate payment or sale totals.
- After `confirmed`, the session is no longer active. The unique index stays `WHERE status IN ('open', 'ready_to_charge')`. The same Inicio `conversation_id` MAY start a new `open` session on the next product utterance. Do not rotate `conversation_id`.
- Payment on `open`, with no sale, or with an unrecognized method MUST clarify and MUST NOT mutate. Same-key replay returns the original body. Different-key repeat after `confirmed` is a stable read-back of `sale_confirmed@1` when no new active session exists.
- Preserve row-lock serialization, FORCE RLS, one application write transaction, audit, outbox, and message-level idempotency (`lumo.message.commit_sale`).

**BREAKING** relative to the active baseline: `SaleSession.status` allows `confirmed`; `ToolRegistry` and `GenerativeUIRegistry` gain `sale.commit@1` and `sale_confirmed@1`; add-item after `confirmed` on the same conversation starts a new sale instead of remaining blocked forever.

## Non-goals

- Daily Close, OperationalDay, CashCount, expected cash, WorkItems, NextBestAction, outcomes.
- Mixed, split, partial, over/under payment, change due, tips, fees, discounts, rounding adjustments.
- Pending payment without a method; `PaymentMethod` configuration table; acquirer, terminal, or bank APIs; cash drawer hardware.
- Refunds, reversals, void/cancel of a confirmed sale, reopen `ready_to_charge`, item edit/remove.
- Catalog price re-read at commit (RF-A-037), manual price override, unknown/free-concept products, catalog CRUD.
- Inventory, stock decrement, purchasing, receiving, suppliers, replenishment, forecasting.
- Invoicing, CFDI/SAT, receipt printing, history screen, CSV/XLSX export.
- Combined item+payment utterances, explicit "nueva venta", Conversation aggregate.
- Voice, camera, vendor LLM, advanced Memory, Redis, Kafka, vector DB, multi-agent, multi-branch.

## Capabilities

### New Capabilities

- `sale-payment`: Separate `Payment` record, closed method enum, amount defaults to sale total, exactly one recorded payment per confirmed session.
- `sale-confirmed-ui`: Versioned `sale_confirmed@1` contract, backend composition after committed `sale.commit@1`, Flutter rendering on Inicio.

### Modified Capabilities

- `sales-session-foundation`: Status machine `open` → `ready_to_charge` → `confirmed`; confirmed sessions leave the active unique index; items remain immutable; next open session allowed for the same conversation after confirm.
- `conversational-sale-session`: Explicit payment intent after ready-to-charge; next natural product utterance starts a new sale; confirmed sales stay immutable.
- `conversational-sale-runtime`: Register and execute `sale.commit@1`; scripted payment-method phrases; `CommitSaleSession` owns the write transaction.
- `ai-native-contracts`: Register `sale.commit@1` and `sale_confirmed@1`; add `SALE-004` and `PAY-001`.
- `persistence`: Alembic `0004` allows `confirmed`, creates `sales.payments` with FORCE RLS; extend sale cleanup to commit/payment integrity rows.
- `mobile-shell`: Inicio keeps a stable `conversation_id` through payment and the next sale; renderer maps `sale_confirmed@1`.
- `sale-summary-ui`: `sale_summary@1` remains `ready_to_charge` only; confirmed sales use `sale_confirmed@1`.

## Impact

- Backend: `SaleSessionStatus.confirmed`, `Payment` domain, Alembic 0004, `sale.commit@1`, `CommitSaleSession`, scripted payment phrases, `sale_confirmed@1`.
- Mobile: renderer maps `sale_confirmed@1`; Inicio does not rotate `conversation_id`.
- Integrity: one application-owned write transaction after locking the session row under `TenantContext` (status + Payment whose `business_id` is copied from that tenant/session + `sale.commit@1` audit + `sale.confirmed` / `payment.recorded` outbox + `lumo.message.commit_sale`). Concurrent commits serialize on that row. Add-item vs commit is CASE A (deny if add-item locks `ready_to_charge` first) or CASE B (new Sale B if commit commits first). Same-key replay; different-key after `confirmed` is a non-mutating read-back. `sale.start@1` output status stays `open` | `ready_to_charge`.
- Tests: cash/card/transfer completion, payment-before-totalize, no-sale, unknown method, replay, different-key read-back, stale add vs next sale, CASE A/CASE B commit-vs-add concurrency, tenant-mismatch Payment rejected, RLS, rollback, Flutter no local math.
