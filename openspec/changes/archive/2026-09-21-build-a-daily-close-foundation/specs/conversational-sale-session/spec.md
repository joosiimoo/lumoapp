## MODIFIED Requirements

### Requirement: Payment intent confirms a ready_to_charge sale
An explicit payment intent against a `ready_to_charge` session MUST lock that session, persist one `Payment` whose amount equals the current Decimal sale total, transition `ready_to_charge` → `confirmed`, and commit audit, outbox, and message-level idempotency in one application-owned write transaction. Success and `sale_confirmed@1` MUST be produced only after commit. Approved phrases (trim, case-insensitive) MUST be:

- cash: `efectivo`, `pagar en efectivo`, `en efectivo`
- card: `tarjeta`, `pagar con tarjeta`, `con tarjeta`
- transfer: `transferencia`, `pagar por transferencia`, `pagar con transferencia`, `por transferencia`

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

#### Scenario: Commit attaches the operational day
- **WHEN** the first sale of the business date is confirmed
- **THEN** exactly one open `operations.operational_days` row MUST exist for that business and date and the confirmed session's `operational_day_id` MUST reference it

#### Scenario: Commit does not count cash or close
- **WHEN** a sale is confirmed with `efectivo`
- **THEN** `operations.cash_counts` MUST NOT gain a row, no `WorkItem` or invoice MUST be created, no Daily Close MUST be performed, and the day's `status` MUST remain `open`
