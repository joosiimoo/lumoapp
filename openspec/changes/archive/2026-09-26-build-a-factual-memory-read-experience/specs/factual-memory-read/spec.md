## ADDED Requirements

### Requirement: Factual memory queries use a closed taxonomy
The system MUST answer factual memory only through the query types `day_summary`, `day_events`, `sales_summary`, `cash_summary`, `close_summary`, `latest_close`, and `recent_cash_differences`. A day-scoped query MUST accept only a resolved business-local date. `today` and `yesterday` MUST be resolved with the business IANA timezone before the query runs. Yesterday MUST be the previous calendar date of that business-local today. `latest` MUST be valid only for `latest_close`. `recent_days` MUST be an integer from 1 to 30 and MUST be valid only for `recent_cash_differences`. The system MUST NOT accept free text, SQL, a semantic query, an arbitrary event-type filter, a date range longer than 30 business days, or a natural-language period such as last quarter or this year. A date after business-local today MUST NOT create an `OperationalDay`.

#### Scenario: Yesterday follows the business calendar
- **WHEN** business-local today is 2026-09-25 and the query is `day_summary` for yesterday
- **THEN** the queried business date MUST be 2026-09-24

#### Scenario: A future date creates no day
- **WHEN** `day_summary` is asked for a business date after business-local today
- **THEN** no `OperationalDay` MUST be inserted and `empty_reason` MUST be `no_operational_day`

#### Scenario: Recent days above 30 are rejected
- **WHEN** `recent_cash_differences` is asked with `recent_days` 31
- **THEN** the query MUST be rejected and no business row MUST be written

### Requirement: FactualMemoryResult is a typed read model
`FactualMemoryResult` MUST contain `query_type`, `business_id`, `business_date`, `period_start`, `period_end`, `facts`, `events`, `source_coverage`, `limitation_code`, and `empty_reason`. It MUST NOT be persisted. It MUST NOT contain model prose, a generated narrative, a completeness score, a confidence, or an embedding. `business_id` MUST be the trusted tenant. Money values MUST be decimal strings with two fraction digits. `limitation_code` MUST be `only_lumo_registered_operations` on every result, including an empty result. `events` MUST contain only business-event read DTOs. `facts` MUST be null when `empty_reason` is set, except where a requirement below explicitly returns partial day-summary facts with a null empty reason.

#### Scenario: The result echoes the tenant and the limitation
- **WHEN** a factual query succeeds for the authenticated business
- **THEN** `business_id` MUST be that tenant and `limitation_code` MUST be `only_lumo_registered_operations`

#### Scenario: The result stores no narrative
- **WHEN** a factual query returns
- **THEN** the result MUST NOT contain a summary, title, narrative, or confidence field

### Requirement: An empty result means nothing matching is recorded in Lumo
The only empty reasons MUST be `no_operational_day`, `no_confirmed_sales`, `no_cash_count`, `no_completed_close`, and `no_matching_facts`. `no_matching_facts` MUST mean that no matching factual result exists. It MUST NOT name the storage table. The system MUST NOT use `nothing_happened`, `no_sales_occurred`, `fully_empty_day`, or `no_matching_events`. `sales_summary` for an existing day with `sale_count` 0 MUST use `no_confirmed_sales`. `cash_summary` for an open day with no current `CashCount` MUST use `no_cash_count`. `close_summary` without a `ClosingSnapshot`, and `latest_close` when the tenant has no snapshot, MUST use `no_completed_close`. `day_events` for an existing day with no events, and `recent_cash_differences` with no qualifying snapshot, MUST use `no_matching_facts`. A day-scoped query with no `OperationalDay` MUST use `no_operational_day`. `day_summary` for an existing day MUST leave `empty_reason` null and MUST return partial facts even when `sale_count` is 0.

#### Scenario: No registered sales is not a claim that nothing was sold
- **WHEN** `sales_summary` runs for a business date that has an `OperationalDay` and no confirmed sale
- **THEN** `empty_reason` MUST be `no_confirmed_sales` and the result MUST NOT state that no sale occurred outside Lumo

#### Scenario: An open day with no sales still returns day facts
- **WHEN** `day_summary` runs for an open day with no confirmed sale and no cash count
- **THEN** `empty_reason` MUST be null, `day_status` MUST be `open`, `close_status` MUST be `not_completed`, and `sale_count` MUST be 0

### Requirement: Day summary facts follow the open or closed source
`day_summary` facts MUST include `day_status`, `sale_count`, `gross_sales_total`, `cash_sales_total`, `card_sales_total`, `transfer_sales_total`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, `close_status`, `pending_work_count`, and `currency`. For an open day, sale totals MUST come from the existing deterministic day summary of confirmed sales, cash fields MUST come from the current `CashCount` when one exists, and those cash fields MUST be null when it does not. `pending_work_count` MUST be the count of open WorkItems for that day. For a closed day, sale totals and cash fields MUST be copied from that day's `ClosingSnapshot` and MUST NOT be recomputed from current payments or from business events. `close_status` MUST be `completed` only when that snapshot exists and MUST be `not_completed` otherwise. The result MUST also include that day's business events ordered by `occurred_at` ascending, then `id` ascending. The facts MUST NOT include completeness, estimated missing sales, a prediction, a trend, or a recommendation.

#### Scenario: An open day uses the live summary and a null cash count
- **WHEN** `day_summary` runs for an open day with one confirmed card sale and no `CashCount`
- **THEN** `sale_count` MUST be 1, the card total MUST equal that payment, `expected_cash`, `counted_cash`, `cash_difference`, and `cash_status` MUST be null, and `close_status` MUST be `not_completed`

#### Scenario: A closed day uses the snapshot
- **WHEN** `day_summary` runs for a closed day whose snapshot gross total differs from a later change to a payment row
- **THEN** `gross_sales_total`, the tender totals, and the cash fields MUST equal the `ClosingSnapshot`, and `close_status` MUST be `completed`

### Requirement: Sales summary reports registered sales only
`sales_summary` facts MUST include `sale_count`, `gross_sales_total`, `cash_sales_total`, `card_sales_total`, `transfer_sales_total`, and `currency`. An open day MUST use the existing confirmed-sales summary. A closed day MUST use the `ClosingSnapshot` totals. The facts MAY include `sale_event_refs` of `event_id` and `sale_session_id` for that day's `sale_confirmed` events. `events` MUST be empty. The system MUST NOT add product ranking, a top seller, a trend, or an average ticket. A missing historical event MUST NOT change `sale_count`.

#### Scenario: Confirmed sales return typed totals
- **WHEN** `sales_summary` runs for an open day with one confirmed cash sale of `120.00`
- **THEN** `sale_count` MUST be 1, `gross_sales_total` and `cash_sales_total` MUST be `120.00`, and `empty_reason` MUST be null

#### Scenario: Snapshot totals survive missing events
- **WHEN** a closed day has snapshot `sale_count` 2 and no `sale_confirmed` row because events were not backfilled
- **THEN** `sale_count` MUST be 2 and `sale_event_refs` MUST be empty

### Requirement: Cash summary reports the recorded count
`cash_summary` facts MUST include `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, `currency`, and `counted_at`. On an open day the counted amount MUST be the current `CashCount.amount`, the expected amount MUST be that day's confirmed cash sales total, and the difference and status MUST be derived by the existing cash-difference functions. On a closed day those money fields and `cash_status` MUST be copied from the `ClosingSnapshot`. The result MUST NOT infer theft, error, fraud, or a missing transaction.

#### Scenario: A short open day returns the signed difference
- **WHEN** `cash_summary` runs for an open day whose confirmed cash sales are `820.00` and whose current count is `805.00`
- **THEN** `expected_cash` MUST be `820.00`, `counted_cash` MUST be `805.00`, `cash_difference` MUST be `-15.00`, and `cash_status` MUST be `short`

#### Scenario: No count is an empty cash summary
- **WHEN** `cash_summary` runs for an open day with no current `CashCount`
- **THEN** `empty_reason` MUST be `no_cash_count` and `facts` MUST be null

### Requirement: Close summary is frozen
`close_summary` facts MUST include `business_date`, `closed_at`, `sale_count`, `gross_sales_total`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, `outcome_status`, and `currency`. Money, counts, and `cash_status` MUST come from the `ClosingSnapshot`. `outcome_status` MUST be the status of that day's daily-close `OutcomeRun` and MUST be null when that run is absent. The system MUST NOT invent `completed`. A later read MUST return the same snapshot figures. The result MAY include the matching `daily_close_completed` event when that row exists. The result MUST NOT state that all sales were captured or that cash was reconciled outside Lumo.

#### Scenario: A closed short day returns the snapshot
- **WHEN** `close_summary` runs for a closed day whose snapshot difference is `-15.00` and whose OutcomeRun is `completed`
- **THEN** `cash_difference` MUST be `-15.00`, `cash_status` MUST be `short`, and `outcome_status` MUST be `completed`

#### Scenario: An open day has no close summary
- **WHEN** `close_summary` runs for an open day
- **THEN** `empty_reason` MUST be `no_completed_close`

#### Scenario: Repeating the read does not recompute the close
- **WHEN** `close_summary` is executed twice for the same closed day and no write occurs between the reads
- **THEN** both results MUST contain the same snapshot totals and the same `closed_at`

### Requirement: Latest close returns one completed snapshot
The system MUST provide a tenant-scoped read `get_latest_completed_close` that returns the single `ClosingSnapshot` ordered by `business_date` descending, `closed_at` descending, and `id` descending. The facts MUST use the close-summary shape for that snapshot. The associated `daily_close_completed` event MUST be included only when that row exists. When the tenant has no snapshot, `empty_reason` MUST be `no_completed_close`. The read MUST NOT write.

#### Scenario: The latest business date wins
- **WHEN** the tenant has closed snapshots for 2026-09-23 and 2026-09-24
- **THEN** `latest_close` MUST return the 2026-09-24 snapshot

#### Scenario: No close is empty
- **WHEN** the tenant has no `ClosingSnapshot`
- **THEN** `empty_reason` MUST be `no_completed_close`

### Requirement: Recent cash differences list closed short or over days
`recent_cash_differences` MUST include only `ClosingSnapshot` rows whose `business_date` falls in the inclusive business-local window from today minus `recent_days - 1` through today, and whose `cash_status` is `short` or `over`. Each fact MUST include `business_date`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, `closed_at`, and `currency`. Order MUST be `business_date` descending. The current open-day `CashCount` and superseded cash-count events MUST be excluded. The result MUST NOT classify a row as severe, suspicious, unusual, or recurring. `source_coverage` MUST be null. `limitation_code` MUST still be `only_lumo_registered_operations`.

#### Scenario: Balanced and open days are omitted
- **WHEN** the last 7 business dates contain one closed short day, one closed balanced day, and an open day with a short current count
- **THEN** the result MUST contain only the closed short day

#### Scenario: No qualifying close is an empty match
- **WHEN** every snapshot in the window is `balanced`
- **THEN** `empty_reason` MUST be `no_matching_facts` and `facts` MUST be null

### Requirement: Business event reads expose typed facts and the business date
A business-event read DTO MUST include `event_id`, `event_type`, `business_date`, `occurred_at`, `source_type`, `source_entity_type`, `source_entity_id`, and `facts`. `business_date` MUST be the linked `OperationalDay.business_date`. `occurred_at` MUST remain the stored timestamp. The DTO MUST NOT add a title, a generated description, a sentiment, a score, a confidence, or an embedding. Day-scoped event lists MUST be ordered by `occurred_at` ascending, then `id` ascending, and MUST NOT be paginated.

#### Scenario: A late local sale stays on its business date
- **WHEN** a sale is confirmed at 23:30 in the business timezone and that instant is the next UTC date
- **THEN** the event DTO `business_date` MUST equal that `OperationalDay.business_date`

#### Scenario: Day events keep chronology
- **WHEN** `day_events` returns a sale, a cash count, and a close for the same day
- **THEN** the events MUST be ordered by `occurred_at` ascending and then `id` ascending

### Requirement: Resolved days include recorded-operations coverage
When a query resolves one `OperationalDay`, `source_coverage` MUST be the recorded-operations declaration for that day, including empty domains and sources when no coverage row exists. The declaration MUST keep `merchant_source_declaration` null and MUST NOT contain a percentage or a complete flag. `recent_cash_differences` MUST leave `source_coverage` null.

#### Scenario: Observed domains are listed without a score
- **WHEN** `day_summary` runs for a day that has `sales` and `cash_count` coverage, both `observed`
- **THEN** `source_coverage.domains` MUST list `sales` and `cash_count`, `sources` MUST list `manual_capture`, and the declaration MUST NOT contain a percentage

### Requirement: Factual reads do not write
Executing any factual memory query MUST NOT insert or update a business event, a coverage row, an `OperationalDay`, a sale, a `CashCount`, a `ClosingSnapshot`, an OutcomeRun, a WorkItem, an audit row, an outbox row, or an idempotency row. A repeated read with unchanged stored facts MUST return the same factual result.

#### Scenario: A query leaves the database unchanged
- **WHEN** `day_summary`, `sales_summary`, `cash_summary`, `close_summary`, `latest_close`, `recent_cash_differences`, or `day_events` runs
- **THEN** the row counts of `business_events`, `source_coverage_records`, `audit.audit_events`, `platform.outbox_events`, and `platform.idempotency_records` MUST be unchanged

#### Scenario: Another tenant cannot read these facts
- **WHEN** tenant B runs any factual memory query while tenant A has events and a snapshot
- **THEN** tenant B MUST NOT receive tenant A's facts or events
