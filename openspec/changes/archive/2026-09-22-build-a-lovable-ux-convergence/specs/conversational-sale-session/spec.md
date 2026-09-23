## MODIFIED Requirements

### Requirement: Payment intent confirms a ready_to_charge sale
An explicit payment intent against a `ready_to_charge` session MUST lock that session, persist one `Payment` whose amount equals the current Decimal sale total, transition `ready_to_charge` → `confirmed`, and commit audit, outbox, and message-level idempotency in one application-owned write transaction. Success and `sale_confirmed@1` MUST be produced only after commit. Approved phrases (trim, case-insensitive) MUST be:

- cash: `efectivo`, `pagar en efectivo`, `en efectivo`
- card: `tarjeta`, `pagar con tarjeta`, `con tarjeta`
- transfer: `transferencia`, `pagar por transferencia`, `pagar con transferencia`, `por transferencia`

The actions `sale.pay.cash@1`, `sale.pay.card@1`, and `sale.pay.transfer@1` MUST be the same commit, with the method taken from the action id, and only for the `sale_session_id` inside that action's signed token. They MUST NOT be a second payment implementation. A typed phrase MUST NOT require that token.

`pagar`, `cobrar`, mixed-method phrases, and item+payment utterances MUST NOT commit.

Commit MUST ensure and attach the `OperationalDay` for the confirmation's business date exactly as `operational-day-foundation` requires: the same transaction MUST resolve or lazily create the one open day for that date and MUST set the confirmed session's `operational_day_id`. This supersedes the earlier statement that commit MUST NOT create an `OperationalDay`, which contradicted the implemented baseline.

Commit MUST NOT create a `CashCount`, a `WorkItem`, or an invoice, MUST NOT perform a final Daily Close, MUST NOT change `OperationalDay.status`, and MUST NOT compute or persist expected cash, counted cash, or a cash difference. Cash counting is owned by `cash-count-foundation` and requires a separate explicit write.

#### Scenario: Cash completion
- **WHEN** a conversation has added Zanahoria `22.50`, Tomate `10.00`, and Galleta A `24.00`, posted `totalizar`, then posted `efectivo`
- **THEN** the session MUST be `confirmed`, exactly one `Payment` MUST exist with `method=cash` and `amount=56.50`, and the response `ui` MUST include `sale_confirmed@1`

#### Scenario: Card completion
- **WHEN** a `ready_to_charge` session exists and the actor posts `tarjeta`
- **THEN** the session MUST be `confirmed` and the `Payment.method` MUST be `card`

#### Scenario: Transfer completion
- **WHEN** a `ready_to_charge` session exists and the actor posts `transferencia`
- **THEN** the session MUST be `confirmed` and the `Payment.method` MUST be `transfer`

#### Scenario: Cash tap completion
- **WHEN** a `ready_to_charge` session exists and the actor submits `sale.pay.cash@1` whose token `sale_session_id` is that session
- **THEN** that session MUST be `confirmed`, exactly one `Payment` MUST exist with `method=cash`, and the response `ui` MUST include `sale_confirmed@1` with empty `actions`

#### Scenario: Commit attaches the operational day
- **WHEN** the first sale of the business date is confirmed
- **THEN** exactly one open `operations.operational_days` row MUST exist for that business and date and the confirmed session's `operational_day_id` MUST reference it

#### Scenario: Commit does not count cash or close
- **WHEN** a sale is confirmed with `efectivo` or with `sale.pay.cash@1`
- **THEN** `operations.cash_counts` MUST NOT gain a row, no `WorkItem` or invoice MUST be created, no Daily Close MUST be performed, and the day's `status` MUST remain `open`

### Requirement: Repeat commit on confirmed is a stable read-back
When the latest session for the interaction context is `confirmed` and no newer active session exists, another semantic payment intent, including a payment action, MUST return the current `sale_confirmed@1` and MUST NOT create a second `Payment`, MUST NOT emit another `sale.confirmed` or `payment.recorded` outbox event, and MUST NOT create another transition audit. Replaying the original `Idempotency-Key` and payload hash MUST return the original persisted response. A different `Idempotency-Key` MUST be treated as a non-mutating read-back and MUST NOT insert a new `lumo.message.commit_sale` idempotency record.

#### Scenario: Same-key replay after commit
- **WHEN** the actor resubmits `efectivo` with the same `Idempotency-Key` and payload hash after a successful transition
- **THEN** the original body MUST be returned, status MUST remain `confirmed`, and a second `Payment` or `sale.confirmed` outbox row MUST NOT exist

#### Scenario: Different-key payment after confirmed
- **WHEN** the session is `confirmed`, no newer active session exists, and the actor posts `efectivo` with a new `Idempotency-Key`
- **THEN** the response MUST include current `sale_confirmed@1`, one `Payment` MUST remain, no second outbox or transition audit MUST be written, and no new `lumo.message.commit_sale` idempotency row MUST be created for that key

#### Scenario: Stale payment action does not double-charge
- **WHEN** the token-bound session is already `confirmed`, no newer active session exists, and `sale.pay.card@1` is submitted with a new idempotency key
- **THEN** one `Payment` MUST remain and the response MUST be that session's `sale_confirmed@1`

## ADDED Requirements

### Requirement: A payment action cannot move to a later sale
A payment action MUST confirm only the session named by its token. A completed same key and hash MUST return the stored body before any newer-session comparison. When that session is already `confirmed` and no newer `open` or `ready_to_charge` session exists, a fresh key MUST return that session's `sale_confirmed@1` without a new payment, audit, outbox, or idempotency row. When a newer `open` or `ready_to_charge` session exists, a fresh key MUST return reason `ui_action_stale`, text `Esta acción ya no aplica a la venta en curso.`, and empty `ui`, and MUST NOT compose the bound session's `sale_confirmed@1` or confirm the newer session. Flutter disabled controls MUST NOT be required for this outcome.

#### Scenario: Unused Sale A button is stale while Sale B is active
- **WHEN** session A was confirmed by typing `efectivo`, session B is `ready_to_charge` in the same conversation, and the unused payment token bound to A is submitted
- **THEN** the response MUST be `ui_action_stale` with empty `ui`, session A MUST keep exactly one `Payment`, session B MUST remain `ready_to_charge` with no `Payment`, and no audit, outbox, or idempotency row MUST be written

#### Scenario: Same-key replay stays on Sale A
- **WHEN** a completed `sale.pay.cash@1` key for session A is repeated after session B is `ready_to_charge`
- **THEN** the stored session A response MUST be returned and session B MUST gain no `Payment`

#### Scenario: Confirmed read-back when the conversation has no newer sale
- **WHEN** the token-bound session is `confirmed`, the conversation has no newer `open` or `ready_to_charge` session, and a fresh payment action key is submitted
- **THEN** the response MUST include that session's `sale_confirmed@1` and MUST NOT create a second `Payment`
