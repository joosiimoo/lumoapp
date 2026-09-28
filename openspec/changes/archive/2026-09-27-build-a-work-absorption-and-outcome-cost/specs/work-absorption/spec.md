## ADDED Requirements

### Requirement: Execution mode is a closed PRD enum
The system MUST persist execution mode using exactly these values from PRD v0.11 §9.12. RF-083 Spanish labels map 1:1 as follows: manual → `manual_by_business`; asistida → `assisted_by_lumo`; preparada → `prepared_by_lumo`; ejecutada con confirmación → `executed_with_confirmation`; reversible → `executed_and_reversible`; bajo política → `executed_under_policy`; revisión interna → `reviewed_by_lumo_operator`; automatizada → `fully_automated`. Execution mode MUST describe how a task was executed. It MUST NOT be WorkItem status, OutcomeRun status, actor, risk level, or completion percentage. The database MUST reject any other value.

#### Scenario: Daily Close uses only Build A modes
- **WHEN** a `WorkAbsorptionRecord` is stored for `daily_close_ready@1`
- **THEN** `current_execution_mode` MUST be one of `fully_automated`, `prepared_by_lumo`, or `executed_with_confirmation`

#### Scenario: Illegal mode is rejected
- **WHEN** an insert uses `current_execution_mode=open`
- **THEN** the database MUST reject the row

### Requirement: Daily Close task taxonomy is six administrative jobs
For `daily_close_ready@1` only, `task_type` MUST be one of `organize_registered_sales`, `calculate_expected_cash`, `record_cash_count`, `reconcile_cash`, `prepare_close`, and `confirm_close`. Each type MUST represent one meaningful administrative job in the implemented Build A flow, not one API call, message, UI action, or sale row. `organize_registered_sales` MUST mean attaching confirmed sales to the OperationalDay and summarizing registered sales. `calculate_expected_cash` MUST mean the server sum of recorded cash payments for the day. `record_cash_count` MUST mean the merchant recording a current CashCount. `reconcile_cash` MUST mean deriving counted versus expected cash and cash status, including short, over, and balanced. `prepare_close` MUST mean the prepared close package that `closing.prepare@1` would return. `confirm_close` MUST mean merchant confirmation via `closing.confirm@1`. The database MUST reject any other `task_type`.

#### Scenario: Balanced close still reconciles
- **WHEN** `closing.confirm@1` completes with `cash_status=balanced`
- **THEN** a `reconcile_cash` record MUST exist for that OutcomeRun

#### Scenario: One sale does not create two organize records
- **WHEN** three confirmed sales commit on the same open day
- **THEN** exactly one `organize_registered_sales` row MUST exist for that OutcomeRun

### Requirement: Baseline is versioned and deterministic
`human_steps_before`, `human_steps_after`, and `estimated_minutes_saved` MUST come from the versioned constant `daily_close_ready@1/work_absorption_baseline@1`, not from an LLM at runtime. For baseline `@1`, `previous_execution_mode` MUST be `manual_by_business` on every task. The baseline MUST copy onto each `WorkAbsorptionRecord` at write time, including `baseline_version` `daily_close_ready@1/work_absorption_baseline@1`. `estimated_minutes_saved` MUST equal `(human_steps_before − human_steps_after) × 2` integer minutes for baseline `@1`. **Approved product rule:** two estimated minutes per eliminated human step. This is a provisional pilot estimate, not measured elapsed time, not a merchant-facing ROI claim. Zero minutes saved is allowed on tasks that still require a human step. If a later baseline version recalibrates constants, existing rows MUST keep the values copied at insert time.

#### Scenario: E26 mapping matches six tasks
- **WHEN** a normal Daily Close completes and six absorption rows exist
- **THEN** exactly two MUST have `current_execution_mode=fully_automated`, exactly two `prepared_by_lumo`, and exactly two `executed_with_confirmation`, and summed `estimated_minutes_saved` MUST be `8` for baseline `@1`

#### Scenario: Baseline version is stored
- **WHEN** any absorption row is inserted
- **THEN** `baseline_version` MUST be `daily_close_ready@1/work_absorption_baseline@1`

### Requirement: WorkAbsorptionRecord is persisted in operations
The system MUST persist `WorkAbsorptionRecord` only in `operations.work_absorption_records`. A row MUST store `id` (UUIDv7), `business_id`, `outcome_run_id`, `work_item_id` (nullable), `task_type`, `previous_execution_mode`, `current_execution_mode`, `human_steps_before`, `human_steps_after`, `estimated_minutes_saved`, `business_intervention_seconds`, `internal_intervention_seconds`, `automation_level`, `evidence_ids`, `baseline_version`, `created_at`, and `updated_at`. `business_id` MUST match the owning OutcomeRun. `outcome_run_id` MUST reference `operations.outcome_runs (id, business_id)` through `(outcome_run_id, business_id)`. Optional `work_item_id` MUST reference `operations.work_items (id, business_id)` when non-null. `human_steps_before`, `human_steps_after`, and `estimated_minutes_saved` MUST be integers `>= 0`. `business_intervention_seconds` and `internal_intervention_seconds` MUST be nullable integers. When non-null, they MUST be `>= 0`. `evidence_ids` MUST be a JSONB array of objects, each with `kind` and `id` only, with no duplicated entity payloads. Allowed `kind` MUST be `outcome_run`, `work_item`, `cash_count`, `closing_snapshot`, `business_event`, and `source_coverage`. Every row MUST include `{kind: outcome_run, id: <outcome_run_id>}`. `automation_level` MUST be one of `manual`, `assisted`, and `automated`. It MUST be derived deterministically from `current_execution_mode` only: `manual_by_business` → `manual`; `assisted_by_lumo`, `prepared_by_lumo`, `executed_with_confirmation`, and `reviewed_by_lumo_operator` → `assisted`; `fully_automated`, `executed_under_policy`, and `executed_and_reversible` → `automated`. It MUST NOT equal `current_execution_mode`, MUST NOT be a percentage, and MUST NOT use runtime LLM classification. Domain `WorkAbsorptionRecord` MUST NOT be a SQLAlchemy model.

#### Scenario: Automation rollup for prepared task
- **WHEN** `reconcile_cash` is stored with `current_execution_mode=prepared_by_lumo`
- **THEN** `automation_level` MUST be `assisted`

#### Scenario: Automation rollup for automated task
- **WHEN** `organize_registered_sales` is stored with `current_execution_mode=fully_automated`
- **THEN** `automation_level` MUST be `automated`

#### Scenario: Work item link is optional
- **WHEN** `organize_registered_sales` is stored
- **THEN** `work_item_id` MAY be null

#### Scenario: Evidence is references only
- **WHEN** a row is inserted
- **THEN** `evidence_ids` MUST NOT contain sale lines, snapshot totals, or model prose

### Requirement: Intervention seconds use nullable measured semantics
`business_intervention_seconds` MUST mean active merchant effort for that task. `internal_intervention_seconds` MUST mean active Lumo internal-operator effort for that task. Backend execution time, GET latency, Flutter redraws, and WorkItem elapsed open-to-resolve time MUST NOT be counted. Persisted semantics MUST be: **NULL** = unknown or not measured; **0** = measured zero active seconds; **>0** = measured duration in seconds. Build A Daily Close instrumentation MUST persist **NULL** for both fields because there is no reliable active-time measurement. The system MUST NOT convert `estimated_minutes_saved` into intervention seconds and MUST NOT fabricate `0` or positive values without a measurement source. NULL MUST NOT mean proof that no intervention occurred.

#### Scenario: Normal close stores unknown intervention
- **WHEN** `confirm_close` is stored after a successful Daily Close in Build A
- **THEN** `business_intervention_seconds` and `internal_intervention_seconds` MUST be NULL and the task MUST still be `executed_with_confirmation`

#### Scenario: Measured zero is distinct from unknown
- **WHEN** a future measurement source records zero active merchant seconds for a task
- **THEN** the row MAY store `business_intervention_seconds=0` and MUST NOT use NULL for that measured case

### Requirement: One absorption row per outcome and task
Unique constraint `uq_work_absorption_records_task` MUST enforce one row for `(business_id, outcome_run_id, task_type)`. Idempotent replay of the parent mutation MUST NOT insert a second row. A merchant recount MUST update the existing `record_cash_count` and `reconcile_cash` rows and MUST NOT insert a second row per recount generation. Reads MUST NOT insert or update absorption rows.

#### Scenario: Idempotent commit does not duplicate
- **WHEN** `sale.commit@1` replays with the same idempotency key and payload hash
- **THEN** exactly one `organize_registered_sales` row MUST exist for that OutcomeRun

#### Scenario: Business Stream is read-only
- **WHEN** `GET /api/v1/business-stream/today` runs twice for a day with an OutcomeRun
- **THEN** `work_absorption_records` row counts MUST be unchanged by those GETs

### Requirement: Absorption writes join OutcomeRun write transactions
Absorption upserts MUST run only inside successful `sale.commit@1`, a new current CashCount insert, successful `closing.confirm@1`, and the today-only initializer that already ensures an OutcomeRun. The first OutcomeRun insert for the day MUST upsert `organize_registered_sales` and `calculate_expected_cash`. A new current CashCount MUST upsert `record_cash_count` and `reconcile_cash`. `closing.confirm@1` MUST upsert all six task types with final evidence, including `prepare_close` and `confirm_close`, before the OutcomeRun becomes `completed`. `closing.prepare@1`, `operational_day.summary@1`, daily sales export, Next Best Action GET, `GET /api/v1/business-stream/today`, equal-amount cash-count read-back, and idempotent replay MUST NOT write absorption rows. A failure before commit MUST leave no new absorption row from that attempt.

#### Scenario: Prepare does not write absorption
- **WHEN** `closing.prepare@1` runs for an open counted day
- **THEN** `work_absorption_records` MUST be unchanged by that read

#### Scenario: Completion writes prepare and confirm tasks
- **WHEN** `closing.confirm@1` commits for a ready day
- **THEN** rows MUST exist for all six `task_type` values for that OutcomeRun

### Requirement: Absorption rows freeze when the outcome completes
When the owning OutcomeRun `status` is `completed`, both `INSERT` and `UPDATE` on `operations.work_absorption_records` MUST be rejected for every role. There MUST be no exception that inserts missing instrumentation after the run is already `completed`. Repair paths that end `completed` in one transaction MUST create or restore the OutcomeRun as `in_progress` or `ready`, insert or upsert all required absorption rows, then transition the OutcomeRun to `completed` in that same transaction. Completed historical absorption MUST NOT change silently on later reads or sales. Build A MUST NOT provide an in-place correction table.

#### Scenario: Completed outcome blocks update
- **WHEN** an OutcomeRun is `completed` and an update attempts to change `estimated_minutes_saved`
- **THEN** the statement MUST fail and the stored value MUST remain

#### Scenario: Completed outcome blocks insert
- **WHEN** an OutcomeRun is `completed` and an insert attempts to add a missing `task_type`
- **THEN** the statement MUST fail and no new row MUST remain

### Requirement: Absorption rows are tenant scoped
`operations.work_absorption_records` MUST `ENABLE` and `FORCE` ROW LEVEL SECURITY with policy `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`. `lumo_app` MUST be granted `SELECT`, `INSERT`, `UPDATE`, and `DELETE`. Instrumentation MUST NOT accept `business_id` from an untrusted request parameter. A session scoped to business B MUST NOT read business A absorption rows.

#### Scenario: Cross-tenant read returns nothing
- **WHEN** business A has absorption rows and the database session is scoped to business B
- **THEN** a select of `operations.work_absorption_records` MUST NOT return A's rows

### Requirement: Absorption audit is create only on insert
Inserting a `WorkAbsorptionRecord` MUST write one audit action `work_absorption.created` in the same transaction. An upsert that only updates an existing row MUST NOT write audit. Absorption lifecycle MUST NOT enqueue an outbox event and MUST NOT add a separate idempotency operation.

#### Scenario: Upsert refresh is quiet
- **WHEN** a second confirmed sale updates evidence on `organize_registered_sales` without inserting a row
- **THEN** no additional `work_absorption.created` audit MUST be written
