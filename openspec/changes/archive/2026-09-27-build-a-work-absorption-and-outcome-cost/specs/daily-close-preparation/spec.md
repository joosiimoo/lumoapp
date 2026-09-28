## MODIFIED Requirements

### Requirement: Tool closing.prepare@1 is a read
`ToolRegistry` MUST register `closing.prepare@1` as a read tool. Input MUST be an empty object and MUST NOT accept an amount, a difference, a status, an `operational_day_id`, or a business date. Permission MUST be `closing.submit_cash_count`. Policy MUST be `CLOSE-002`. Side effect MUST be `read`. Idempotency MUST NOT be required, and the message path MUST NOT insert an idempotency record for it. Despite the Architecture §10.1 name, this tool MUST NOT insert or update `operations.operational_days`, `operations.cash_counts`, `operations.closing_snapshots`, `operations.work_absorption_records`, `operations.outcome_costs`, `sales.sale_sessions`, `sales.sale_items`, `sales.payments`, `audit.audit_events`, `platform.outbox_events`, or `platform.idempotency_records`. It MUST NOT change `OperationalDay.status`, evaluate outcome gates, create a `ClosingSnapshot`, create WorkItems, mark a day ready to close, confirm a close, or write work-absorption or outcome-cost instrumentation. It MUST NOT issue a confirmation token. When the day is `open` or absent, output MUST be the live close-preparation payload with `confirmation_token` null. When the day is `closed`, output MUST be the persisted `ClosingSnapshot` and the composer MUST emit `daily_close_confirmed@1` instead of `daily_close_preparation@1`. That closed read MUST NOT recompute totals from current sales. A `closed` day with no snapshot MUST fail the read and MUST NOT fall back to a live aggregate. `closing.reopen@1` MUST remain unregistered.

#### Scenario: Preparation read writes nothing
- **WHEN** `closing.prepare@1` runs for a tenant that has a confirmed cash sale and a recorded count on an open day
- **THEN** it MUST return the live preparation payload and MUST NOT insert or update any operational day, cash count, snapshot, sale, payment, absorption row, cost row, audit, outbox, or idempotency row

#### Scenario: Repeat read is stable
- **WHEN** the actor requests close preparation twice with no cash sale and no count in between
- **THEN** both responses MUST carry the same `expected_cash`, `counted_cash`, `cash_difference`, and `cash_status`, and the second request MUST write nothing

#### Scenario: Closed day returns the snapshot
- **WHEN** `closing.prepare@1` runs for a day whose `status` is `closed`
- **THEN** the response MUST carry the snapshot's `sale_count`, `gross_sales_total`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, and `closed_at`, MUST emit `daily_close_confirmed@1`, and MUST write nothing

#### Scenario: Reopen stays unavailable
- **WHEN** a decision names `closing.reopen@1`
- **THEN** the registry MUST report the tool as unregistered, policy MUST `deny` under `SEC-002`, and no day MUST be reopened
