## MODIFIED Requirements

### Requirement: closing.confirm@1 confirms today's open day
`ToolRegistry` MUST register `closing.confirm@1` as a write tool. Input MUST include required `confirmation_token` string and MAY include optional `close_note` string. It MUST NOT accept totals, expected cash, counted cash, a difference, `cash_status`, an operational day id, a snapshot id, a business date, a currency, an actor id, a cash count id, or `closed_at`. Permission MUST be `closing.confirm`. Policy MUST be `CLOSE-003`. Side effect MUST be `write`. Idempotency MUST be required. `closing.reopen@1` MUST remain unregistered. The tool MUST NOT create an `OperationalDay`, a `WorkItem`, or a `NextBestAction`, and MUST NOT register `daily_close_ready.execute@1`. A successful confirm MUST complete the day's `daily_close_ready@1` OutcomeRun as `daily-close-outcome` requires. A business date with no `OperationalDay` MUST clarify with reason `operational_day_not_started` and MUST NOT insert a day, a snapshot, an OutcomeRun, an audit row, an outbox row, or an idempotency row. When `close_note` is present and non-empty after trim, the new ClosingSnapshot MUST store it; otherwise `close_note` MUST be null. The note MUST NOT change fingerprint verification.

#### Scenario: No day does not close
- **WHEN** the actor confirms a close and no OperationalDay exists for today's business date
- **THEN** the response MUST clarify with `operational_day_not_started`, and `operations.operational_days`, `operations.closing_snapshots`, and `operations.outcome_runs` MUST gain no row

#### Scenario: Reopen stays unregistered
- **WHEN** a decision names `closing.reopen@1`
- **THEN** the registry MUST report the tool as unregistered, policy MUST `deny` under `SEC-002`, and no day MUST change status

#### Scenario: Optional note does not bypass guards
- **WHEN** confirm is attempted with a valid-looking note but a stale confirmation token
- **THEN** the day MUST stay open and no snapshot MUST be written
