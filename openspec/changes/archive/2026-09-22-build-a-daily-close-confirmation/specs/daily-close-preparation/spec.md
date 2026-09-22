## MODIFIED Requirements

### Requirement: Tool closing.prepare@1 is a read
`ToolRegistry` MUST register `closing.prepare@1` as a read tool. Input MUST be an empty object and MUST NOT accept an amount, a difference, a status, an `operational_day_id`, or a business date. Permission MUST be `closing.submit_cash_count`. Policy MUST be `CLOSE-002`. Side effect MUST be `read`. Idempotency MUST NOT be required, and the message path MUST NOT insert an idempotency record for it. Despite the Architecture §10.1 name, this tool MUST NOT insert or update `operations.operational_days`, `operations.cash_counts`, `operations.closing_snapshots`, `sales.sale_sessions`, `sales.sale_items`, `sales.payments`, `audit.audit_events`, `platform.outbox_events`, or `platform.idempotency_records`. It MUST NOT change `OperationalDay.status`, evaluate outcome gates, create a `ClosingSnapshot`, create WorkItems, mark a day ready to close, or confirm a close. It MUST NOT issue a confirmation token. When the day is `open` or absent, output MUST be the live close-preparation payload with `confirmation_token` null. When the day is `closed`, output MUST be the persisted `ClosingSnapshot` and the composer MUST emit `daily_close_confirmed@1` instead of `daily_close_preparation@1`. That closed read MUST NOT recompute totals from current sales. A `closed` day with no snapshot MUST fail the read and MUST NOT fall back to a live aggregate. `closing.reopen@1` MUST remain unregistered.

#### Scenario: Preparation read writes nothing
- **WHEN** `closing.prepare@1` runs for a tenant that has a confirmed cash sale and a recorded count on an open day
- **THEN** it MUST return the live preparation payload and MUST NOT insert or update any operational day, cash count, snapshot, sale, payment, audit, outbox, or idempotency row

#### Scenario: Repeat read is stable
- **WHEN** the actor requests close preparation twice with no cash sale and no count in between
- **THEN** both responses MUST carry the same `expected_cash`, `counted_cash`, `cash_difference`, and `cash_status`, and the second request MUST write nothing

#### Scenario: Closed day returns the snapshot
- **WHEN** `closing.prepare@1` runs for a day whose `status` is `closed`
- **THEN** the response MUST carry the snapshot's `sale_count`, `gross_sales_total`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, and `closed_at`, MUST emit `daily_close_confirmed@1`, and MUST write nothing

#### Scenario: Reopen stays unavailable
- **WHEN** a decision names `closing.reopen@1`
- **THEN** the registry MUST report the tool as unregistered, policy MUST `deny` under `SEC-002`, and no day MUST be reopened

### Requirement: Close-preparation payload
For an open day or no day, the payload MUST contain `operational_day_id`, `business_date`, `day_status`, `currency`, `sale_count`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, `counted_at`, `cash_count_id`, and `confirmation_token`. Money MUST be decimal strings plus the business currency. `business_date` MUST be an ISO calendar date computed from one application clock reading in `identity.businesses.timezone`, never from a client date or the device timezone. `day_status` MUST be `open` when an open day exists and null when it does not. `sale_count` MUST be the number of confirmed sales of that day. `confirmation_token` MUST be null on this tool. The payload MUST NOT include `gross_sales_total`, `card_total`, `transfer_total`, a close action, an approval, an exception list, a product breakdown, a chart series, or history; the daily split remains owned by `operational_day.summary@1`. A closed day MUST NOT use this payload; it uses `daily_close_confirmed@1`.

#### Scenario: Counted day payload
- **WHEN** today's open OperationalDay has three confirmed sales, `expected_cash` `22.50`, and a current count of `20.00`
- **THEN** the payload MUST carry that `operational_day_id`, `day_status=open`, `sale_count=3`, `expected_cash` `22.50`, `counted_cash` `20.00`, `cash_difference` `-2.50`, `cash_status=short`, a non-null `counted_at`, that `cash_count_id`, and `confirmation_token` null

#### Scenario: Payload omits the daily split
- **WHEN** the open-day preparation payload is inspected
- **THEN** it MUST NOT contain `gross_sales_total`, `card_total`, `transfer_total`, or a close-confirmation action

### Requirement: Preparation does not close the day
Calling `closing.prepare@1` or recording a cash count MUST NOT transition `OperationalDay.status`, MUST NOT persist a close timestamp on the day, and MUST NOT create a `ClosingSnapshot`, a close outbox event, WorkItems, NextBestAction rows, or OutcomeRuns. `status=closed` is owned only by `closing.confirm@1`. Preparation state for an open day MUST stay derived from the current `CashCount`.

#### Scenario: Day stays open after counting
- **WHEN** a balanced count is recorded for today's open OperationalDay and the actor does not confirm
- **THEN** that day's `status` MUST still be `open`, no close event MUST be emitted, and no `ClosingSnapshot` MUST exist

#### Scenario: No close-side effects from preparation
- **WHEN** the capture and preparation flow has run and the actor has not confirmed
- **THEN** no `ClosingSnapshot`, WorkItem, OutcomeRun, or close-approval row MUST exist
