## ADDED Requirements

### Requirement: Expected cash is recorded cash payments of the day
`expected_cash` MUST be computed in the backend as the `Decimal` sum of `sales.payments.amount` where `status=recorded` and `method=cash`, for the `SaleSession`s of that `OperationalDay` whose status is `confirmed`. It MUST be quantized to two decimal places, MUST be `0.00` when there are no cash sales, and MUST use the business currency. Card and transfer payments MUST NOT change it. `open` and `ready_to_charge` sessions MUST be excluded. `expected_cash` MUST be produced by the same repository aggregation that computes `cash_total` for `operational_day.summary@1`, and the two values MUST be equal for the same day. Build A MUST NOT include an opening float, cash expenses, withdrawals, deposits, refunds, voids, tips, or rounding adjustments in the formula, because no authoritative Build A requirement defines them. The client, the interpreter, and the model MUST NOT supply or recompute `expected_cash`.

#### Scenario: Only cash sales count
- **WHEN** today's confirmed sales are one cash sale of `22.50`, one card sale of `10.00`, and one transfer sale of `24.00`
- **THEN** `expected_cash` MUST be `22.50` in the business currency and MUST equal that day's `cash_total` from `operational_day.summary@1`

#### Scenario: No cash sales
- **WHEN** today's OperationalDay has confirmed sales but none paid with cash
- **THEN** `expected_cash` MUST be `0.00` and MUST NOT be null

#### Scenario: Drafts are excluded
- **WHEN** an `open` or `ready_to_charge` session exists for the same business date
- **THEN** it MUST NOT change `expected_cash`

### Requirement: Cash difference is signed and derived
`cash_difference` MUST equal `counted_cash − expected_cash`, computed with `Decimal` in the backend and quantized to two decimal places. A positive value MUST mean an overage, zero MUST mean balanced, and a negative value MUST mean a shortage. It MUST be serialized as a signed decimal string with the business currency. `cash_difference` MUST NOT be persisted in `operations.cash_counts` or `operations.operational_days`. No tolerance, threshold, rounding band, automatic adjustment, or silent correction MUST be applied. The client MUST NOT compute or re-derive it.

#### Scenario: Shortage
- **WHEN** `expected_cash` is `22.50` and the current count is `20.00`
- **THEN** `cash_difference` MUST be `-2.50` and `cash_status` MUST be `short`

#### Scenario: Overage
- **WHEN** `expected_cash` is `22.50` and the current count is `25.00`
- **THEN** `cash_difference` MUST be `2.50` and `cash_status` MUST be `over`

#### Scenario: Balanced
- **WHEN** `expected_cash` is `22.50` and the current count is `22.50`
- **THEN** `cash_difference` MUST be `0.00` and `cash_status` MUST be `balanced`

#### Scenario: Difference is not adjusted
- **WHEN** a non-zero difference exists
- **THEN** the system MUST report it and MUST NOT alter the count, the payments, or the sales to remove it

### Requirement: Cash status enum exposed to the client
`cash_status` MUST be exactly one of `not_counted`, `balanced`, `over`, or `short`. `not_counted` MUST be used when no current `CashCount` exists for the day, and in that case `counted_cash`, `cash_difference`, `counted_at`, and `cash_count_id` MUST be null. A fabricated `0.00` difference MUST NOT be returned for an uncounted day. Statuses implying a close decision, approval, or exception MUST NOT be exposed.

#### Scenario: Not counted
- **WHEN** today's OperationalDay has cash sales of `22.50` and no `CashCount`
- **THEN** `expected_cash` MUST be `22.50`, `counted_cash` MUST be null, `cash_difference` MUST be null, and `cash_status` MUST be `not_counted`

#### Scenario: Status values are closed
- **WHEN** the preparation payload is validated
- **THEN** `cash_status` MUST be one of the four allowed values and MUST NOT be `ready_to_close`, `closed`, `accepted`, or `blocked`

### Requirement: Tool closing.prepare@1 is a read
`ToolRegistry` MUST register `closing.prepare@1` as a read tool. Input MUST be an empty object and MUST NOT accept an amount, a difference, a status, an `operational_day_id`, or a business date. Output MUST be the close-preparation payload. Permission MUST be `closing.submit_cash_count`. Policy MUST be `CLOSE-002`. Side effect MUST be `read`. Idempotency MUST NOT be required, and the message path MUST NOT insert an idempotency record for it. Despite the Architecture §10.1 name, this tool MUST NOT insert or update `operations.operational_days`, `operations.cash_counts`, `sales.sale_sessions`, `sales.sale_items`, `sales.payments`, `audit.audit_events`, `platform.outbox_events`, or `platform.idempotency_records`. It MUST NOT change `OperationalDay.status`, evaluate outcome gates, create a `ClosingSnapshot`, create WorkItems, mark a day ready to close, or confirm a close. `closing.confirm@1` and `closing.reopen@1` MUST remain unregistered.

#### Scenario: Preparation read writes nothing
- **WHEN** `closing.prepare@1` runs for a tenant that has a confirmed cash sale and a recorded count
- **THEN** it MUST return the preparation payload and MUST NOT insert or update any operational day, cash count, sale, payment, audit, outbox, or idempotency row

#### Scenario: Repeat read is stable
- **WHEN** the actor requests close preparation twice with no cash sale and no count in between
- **THEN** both responses MUST carry the same `expected_cash`, `counted_cash`, `cash_difference`, and `cash_status`, and the second request MUST write nothing

#### Scenario: Close confirmation stays unavailable
- **WHEN** a decision names `closing.confirm@1` or `closing.reopen@1`
- **THEN** the registry MUST report the tool as unregistered, policy MUST `deny` under `SEC-002`, and no day MUST be closed

### Requirement: Close-preparation payload
The payload MUST contain `operational_day_id`, `business_date`, `day_status`, `currency`, `sale_count`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, `counted_at`, and `cash_count_id`. Money MUST be decimal strings plus the business currency. `business_date` MUST be an ISO calendar date computed from one application clock reading in `identity.businesses.timezone`, never from a client date or the device timezone. `day_status` MUST be `open` when a day exists and null when it does not. `sale_count` MUST be the number of confirmed sales of that day. The payload MUST NOT include `gross_sales_total`, `card_total`, `transfer_total`, a close action, an approval, an exception list, a product breakdown, a chart series, or history; the daily split remains owned by `operational_day.summary@1`.

#### Scenario: Counted day payload
- **WHEN** today's OperationalDay has three confirmed sales, `expected_cash` `22.50`, and a current count of `20.00`
- **THEN** the payload MUST carry that `operational_day_id`, `day_status=open`, `sale_count=3`, `expected_cash` `22.50`, `counted_cash` `20.00`, `cash_difference` `-2.50`, `cash_status=short`, a non-null `counted_at`, and that `cash_count_id`

#### Scenario: Payload omits the daily split
- **WHEN** the preparation payload is inspected
- **THEN** it MUST NOT contain `gross_sales_total`, `card_total`, `transfer_total`, or a close-confirmation action

### Requirement: Zero sales and no day are deterministic
When no `OperationalDay` exists for today's business date, the preparation read MUST return `operational_day_id=null`, `day_status=null`, `sale_count=0`, `expected_cash=0.00`, `counted_cash=null`, `cash_difference=null`, `cash_status=not_counted`, `counted_at=null`, `cash_count_id=null`, and `business_date` equal to today in the business timezone. The read MUST NOT create an `OperationalDay` or a `CashCount`. Repeating the read MUST NOT create a row and MUST NOT write audit, outbox, or idempotency records.

#### Scenario: Preparation with no sales and no day
- **WHEN** the actor posts `preparar el cierre` and no confirmed sale exists for today's business date
- **THEN** the response MUST be that not-started payload, and `operations.operational_days` and `operations.cash_counts` MUST gain no rows

#### Scenario: Preparation after sales but before counting
- **WHEN** the day exists with cash sales of `22.50` and no count
- **THEN** `expected_cash` MUST be `22.50`, `cash_status` MUST be `not_counted`, and the read MUST write nothing

### Requirement: Preparation does not close the day
This capability MUST NOT introduce `OperationalDay.status` values other than `open`, MUST NOT persist a close timestamp, a closed-by actor, a `ClosingSnapshot`, or a close outbox event, and MUST NOT create WorkItems, NextBestAction rows, OutcomeRuns, or `daily_close_ready@1` gate evaluation. Preparation state MUST be derived from the presence and amount of the current `CashCount`, not from a new persisted workflow state.

#### Scenario: Day stays open after counting
- **WHEN** a balanced count is recorded for today's OperationalDay
- **THEN** that day's `status` MUST still be `open`, no close event MUST be emitted, and no `closed` or `ready_to_close` value MUST be persisted anywhere

#### Scenario: No close-side effects
- **WHEN** the full capture and preparation flow has run for a business date
- **THEN** no `ClosingSnapshot`, WorkItem, OutcomeRun, or close-approval row MUST exist
