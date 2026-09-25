## MODIFIED Requirements

### Requirement: Payment intent confirms a ready_to_charge sale
An explicit payment intent against a `ready_to_charge` session MUST lock that session, persist one `Payment` whose amount equals the current Decimal sale total, transition `ready_to_charge` → `confirmed`, and commit audit, outbox, and message-level idempotency in one application-owned write transaction. Success and `sale_confirmed@1` MUST be produced only after commit. Approved phrases (trim, case-insensitive) MUST be:

- cash: `efectivo`, `pagar en efectivo`, `en efectivo`
- card: `tarjeta`, `pagar con tarjeta`, `con tarjeta`
- transfer: `transferencia`, `pagar por transferencia`, `pagar con transferencia`, `por transferencia`

The actions `sale.pay.cash@1`, `sale.pay.card@1`, and `sale.pay.transfer@1` MUST be the same commit, with the method taken from the action id, and only for the `sale_session_id` inside that action's signed token. They MUST NOT be a second payment implementation. A typed phrase MUST NOT require that token.

`pagar`, `cobrar`, mixed-method phrases, and item+payment utterances MUST NOT commit.

Commit MUST ensure and attach the `OperationalDay` for the confirmation's business date exactly as `operational-day-foundation` requires: the same transaction MUST resolve or lazily create the one open day for that date and MUST set the confirmed session's `operational_day_id`. This supersedes the earlier statement that commit MUST NOT create an `OperationalDay`, which contradicted the implemented baseline.

Commit MUST NOT create a `CashCount` or an invoice, MUST NOT perform a final Daily Close, MUST NOT change `OperationalDay.status`, and MUST NOT compute or persist counted cash or a cash difference. The same transaction MUST ensure the `daily_close_ready@1` OutcomeRun and then run Daily Close WorkItem sync after the day and payment exist, as `daily-close-outcome` and `work-item-foundation` require. When that day has no current `CashCount`, the OutcomeRun MUST be `in_progress` with `reason_code=awaiting_cash_count` and sync MUST leave one open `cash_count_required` row whose `outcome_run_id` is that run. Cash counting is owned by `cash-count-foundation` and requires a separate explicit write. Idempotent replay and a confirmed read-back MUST NOT run sync again and MUST NOT insert a second OutcomeRun.

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
- **WHEN** a sale is confirmed with `efectivo` or with `sale.pay.cash@1` and no `CashCount` exists
- **THEN** `operations.cash_counts` MUST NOT gain a row, no invoice MUST be created, no Daily Close MUST be performed, the day's `status` MUST remain `open`, exactly one OutcomeRun MUST be `in_progress` with `reason_code=awaiting_cash_count`, and exactly one open `cash_count_required` WorkItem MUST exist for that day

#### Scenario: First confirmed sale opens one outcome
- **WHEN** the first sale of the business date is confirmed and no CashCount exists
- **THEN** exactly one OutcomeRun MUST exist for that operational day and a second confirmed sale on that day MUST NOT insert another

### Requirement: Repeat commit on confirmed is a stable read-back
When the latest session for the interaction context is `confirmed` and no newer active session exists, another semantic payment intent, including a payment action, MUST return the current `sale_confirmed@1` and MUST NOT create a second `Payment`, MUST NOT emit another `sale.confirmed` or `payment.recorded` outbox event, MUST NOT create another transition audit, and MUST NOT insert or update an OutcomeRun. Replaying the original `Idempotency-Key` and payload hash MUST return the original persisted response. A different `Idempotency-Key` MUST be treated as a non-mutating read-back and MUST NOT insert a new `lumo.message.commit_sale` idempotency record.

#### Scenario: Same-key replay after commit
- **WHEN** the actor resubmits `efectivo` with the same `Idempotency-Key` and payload hash after a successful transition
- **THEN** the original body MUST be returned, status MUST remain `confirmed`, and a second `Payment`, `sale.confirmed` outbox row, or OutcomeRun MUST NOT exist

#### Scenario: Different-key payment after confirmed
- **WHEN** the session is `confirmed`, no newer active session exists, and the actor posts `efectivo` with a new `Idempotency-Key`
- **THEN** the response MUST include current `sale_confirmed@1`, one `Payment` MUST remain, no second outbox or transition audit MUST be written, no OutcomeRun MUST be inserted or updated, and no new `lumo.message.commit_sale` idempotency row MUST be created for that key

### Requirement: Post-close commit guard is unchanged
A free-concept line MAY be added on a new `open` session after the operational day is `closed`, because add-item does not consult the day. `sale.commit@1` MUST still refuse to confirm that session into the closed day and MUST NOT insert an OutcomeRun for that refusal.

#### Scenario: Commit after close refuses
- **WHEN** the day is `closed` and a `ready_to_charge` session contains a free-concept line
- **THEN** commit MUST NOT record a `Payment`, MUST NOT set the session to `confirmed`, and MUST NOT insert an OutcomeRun

### Requirement: Existing close and payment behavior stays in force
A confirming commit MUST still record exactly one `Payment` with `status=recorded`. It MUST NOT leave a confirmed sale without a payment. `ready_to_charge` MUST remain unattached to an OperationalDay and MUST NOT create an OutcomeRun. This requirement does not add `payment_required`.

#### Scenario: Ready to charge stays off the day
- **WHEN** a session is `ready_to_charge` and no confirmed sale exists for today
- **THEN** its `operational_day_id` MUST be NULL, no Daily Close WorkItem MUST reference that session, and no OutcomeRun MUST exist
