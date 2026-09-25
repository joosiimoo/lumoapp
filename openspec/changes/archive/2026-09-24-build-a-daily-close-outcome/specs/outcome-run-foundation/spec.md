## ADDED Requirements

### Requirement: Daily Close outcome is one durable row
The system MUST persist `daily_close_ready` version `1` in `operations.outcome_runs`. A row MUST store `id`, `business_id`, `operational_day_id`, `outcome_type`, `outcome_version`, `status`, `owner_type`, `reason_code`, `evidence`, `created_at`, and `updated_at`. `ready_at`, `completed_at`, and `closing_snapshot_id` MUST be nullable. `outcome_type` MUST be `daily_close_ready`. `outcome_version` MUST be `1`. `owner_type` MUST be `business`. The row MUST NOT store `owner_id`, `failed_at`, a cost summary, a source-coverage id, sale lines, or model prose. Status MUST be only `in_progress`, `ready`, or `completed`. Reason codes MUST be only `awaiting_cash_count`, `ready_balanced`, `ready_cash_short`, `ready_cash_over`, and `closed_confirmed`. `blocked`, `failed`, `cancelled`, and `not_ready` MUST NOT be stored. `not_ready` is an `OutcomeEngine` evaluation verdict for an unknown definition id. It MUST NOT be an `OutcomeRun.status`, a reason code, or a value allowed by the `operations.outcome_runs` status check.

`in_progress` MUST have `reason_code=awaiting_cash_count`, null `ready_at`, null `completed_at`, null `closing_snapshot_id`, and evidence `cash_status=not_counted`. An insert with `status=ready` MUST set `ready_at` to the insertion instant. `ready` MUST have a non-null `ready_at`, null `completed_at`, null `closing_snapshot_id`, and `reason_code` `ready_balanced`, `ready_cash_short`, or `ready_cash_over` matching evidence `cash_status` `balanced`, `short`, or `over`. An insert with `status=completed` MUST set `ready_at` equal to `completed_at`. `completed` MUST have non-null `ready_at`, non-null `completed_at`, non-null `closing_snapshot_id`, `reason_code=closed_confirmed`, and evidence `cash_status` of `balanced`, `short`, or `over`.

#### Scenario: Stored states are the three Build A states
- **WHEN** a row is inserted for an open day that has confirmed sales and no current CashCount
- **THEN** `status` MUST be `in_progress`, `reason_code` MUST be `awaiting_cash_count`, `owner_type` MUST be `business`, and `outcome_type` MUST be `daily_close_ready` at version `1`

#### Scenario: Failed blocked and cancelled are absent
- **WHEN** the `outcome_runs` status check is inspected
- **THEN** it MUST NOT allow `blocked`, `failed`, `cancelled`, or `not_ready`

#### Scenario: A ready insert records ready_at
- **WHEN** a row is inserted with `status=ready`
- **THEN** `ready_at` MUST be the insertion instant and the status check MUST still allow only `in_progress`, `ready`, and `completed`

### Requirement: One outcome per day and version
The database MUST enforce one row for `(business_id, operational_day_id, outcome_type, outcome_version)` through `uq_outcome_runs_identity`. It MUST also enforce `UNIQUE (id, business_id)` and `UNIQUE (id, business_id, operational_day_id)`. A second row for the same business, day, type, and version MUST be rejected.

#### Scenario: A second insert for the same day is rejected
- **WHEN** an OutcomeRun already exists for a business, operational day, `daily_close_ready`, and version `1`, and another insert uses that same identity
- **THEN** the database MUST reject the second insert and the first row MUST remain

### Requirement: Evidence is a structured projection
`evidence` MUST be a JSON object. It MUST include `currency`, `sale_count`, `gross_sales_total`, `expected_cash`, and `cash_status`. When a current CashCount exists it MUST also include `counted_cash`, signed `cash_difference`, and `current_cash_count_id`. Amounts MUST be decimal strings. It MUST NOT include `operational_day_id`, `closing_snapshot_id`, sale lines, or prose. Evidence MUST NOT be the input used to compute expected cash, `cash_status`, or the ClosingSnapshot.

#### Scenario: Uncounted evidence omits count fields
- **WHEN** an `in_progress` row is stored and no current CashCount exists
- **THEN** evidence MUST contain `cash_status=not_counted` and MUST NOT contain `current_cash_count_id`

#### Scenario: Counted evidence names the current count
- **WHEN** a `ready` row is stored for a current count
- **THEN** evidence MUST contain that count's id, `counted_cash`, and the signed `cash_difference`

### Requirement: Outcome rows are tenant scoped
`operations.outcome_runs` MUST `ENABLE` and `FORCE` ROW LEVEL SECURITY with policy `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`. `lumo_app` MUST be granted `SELECT`, `INSERT`, `UPDATE`, and `DELETE`. This migration MUST NOT grant `BYPASSRLS`. `lumo_admin` MUST remain `NOBYPASSRLS`. The row MUST reference `operations.operational_days (id, business_id)` through `(operational_day_id, business_id)`. A non-null `closing_snapshot_id` MUST reference `operations.closing_snapshots (id, business_id, operational_day_id)` through `(closing_snapshot_id, business_id, operational_day_id)`.

#### Scenario: Another tenant cannot read the outcome
- **WHEN** business A has an OutcomeRun and the database session is scoped to business B
- **THEN** a select of `operations.outcome_runs` MUST NOT return A's row

### Requirement: Outcome audit is create and status or reason change only
Inserting an OutcomeRun MUST write one audit action `outcome_run.created` in the same transaction. Changing `status` or `reason_code` on an existing row MUST write one audit action `outcome_run.status_changed` and MUST include `previous_status`, `status`, `previous_reason_code`, and `reason_code`. A ready reason change that keeps `status=ready` MUST use `outcome_run.status_changed`. An evidence-only update MUST NOT write audit. An unchanged status, reason, and evidence MUST NOT write the row and MUST NOT change `updated_at`. Outcome lifecycle MUST NOT enqueue an outbox event. Audit payloads MUST NOT include model prose.

#### Scenario: Evidence-only refresh is quiet
- **WHEN** a later sale changes `sale_count` and `gross_sales_total` but leaves `status` and `reason_code` unchanged
- **THEN** evidence MUST be updated and no `outcome_run.status_changed` audit MUST be written

#### Scenario: No outcome event is enqueued
- **WHEN** an OutcomeRun is created or completed
- **THEN** no outbox row whose type names the OutcomeRun MUST exist
