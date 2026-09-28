# outcome-cost Specification

## Purpose

Internal outcome cost instrumentation per OutcomeRun (PRD RF-084/085): one `operations.outcome_costs` row in USD with measured, estimated, and unavailable components, partial completeness in Build A, nullable intervention seconds, and completion freeze. Cost fields MUST NOT live on `operations.outcome_runs`. No merchant-facing cost API in Build A.
## Requirements
### Requirement: Outcome cost is one row per OutcomeRun
The system MUST persist outcome cost only in `operations.outcome_costs`, not on `operations.outcome_runs`. Exactly one row MUST exist per `(business_id, outcome_run_id)`. `outcome_run_id` MUST reference `operations.outcome_runs (id, business_id)` through `(outcome_run_id, business_id)`. The row MUST store `id` (UUIDv7), `business_id`, `outcome_run_id`, `currency`, component status fields, optional monetary amounts, `retry_count`, `business_intervention_seconds`, `internal_intervention_seconds`, `estimated_total_cost_amount` (nullable), `cost_completeness`, `created_at`, and `updated_at`. Domain `OutcomeCost` MUST NOT be a SQLAlchemy model. Merchant-facing APIs MUST NOT expose this row in Build A.

#### Scenario: OutcomeRun has no cost_summary column
- **WHEN** `operations.outcome_runs` is inspected after migration `0013`
- **THEN** it MUST NOT contain `cost_summary` or other cost columns

#### Scenario: Second cost row is rejected
- **WHEN** an OutcomeCost already exists for a business and OutcomeRun and another insert uses the same pair
- **THEN** the database MUST reject the second insert

### Requirement: Cost components distinguish measured estimated and unavailable
Each cost component MUST declare a status of `measured`, `estimated`, or `unavailable`. Unavailable monetary components MUST store NULL amount, not `0.00`. Build A Daily Close MUST set `model_call_count_status`, `model_token_status`, `model_cost_status`, and `infrastructure_cost_status` to `unavailable` with NULL counts and NULL amounts because the LLM provider port exposes no usage metadata and outcome-delivery writes do not call a model. The system MUST NOT fabricate token counts or model costs and MUST NOT force an LLM call to produce telemetry. `retry_count` MUST be `measured` with a non-null integer `>= 0`. `retry_count=0` MUST mean no recorded server-side retry for outcome delivery, not unavailable. `business_intervention_seconds` and `internal_intervention_seconds` MUST be nullable integers. **NULL** = unknown or not measured; **0** = measured zero active seconds; **>0** = measured duration. Build A Daily Close MUST persist **NULL** for both because there is no reliable active-time measurement. They MUST NOT be derived from `estimated_minutes_saved`, WorkItem elapsed time, or fabricated defaults. They MUST NOT be converted to money in Build A.

#### Scenario: Outcome-level intervention is unknown in Build A
- **WHEN** an OutcomeCost row is finalized for a completed Daily Close in Build A
- **THEN** `business_intervention_seconds` and `internal_intervention_seconds` MUST be NULL

#### Scenario: Model cost is unavailable not zero
- **WHEN** an OutcomeCost row is inserted for a completed Daily Close
- **THEN** `model_cost_status` MUST be `unavailable`, `model_cost_amount` MUST be NULL, and `model_cost_amount` MUST NOT be `0.00`

#### Scenario: Zero model calls without fabrication
- **WHEN** outcome delivery completed without a model call in the write transaction
- **THEN** `model_call_count` MUST be NULL and `model_call_count_status` MUST be `unavailable`

### Requirement: Platform cost currency is USD
Monetary cost fields MUST use `numeric(12,2)` amounts and a three-letter ISO currency code. Binary float MUST NOT be used. JSON representations MUST use decimal strings plus currency. Build A internal platform cost currency MUST be `USD`, separate from merchant operational MXN amounts on sales and close snapshots. The `operations.outcome_costs.currency` column MUST be `USD` even when all monetary amounts are NULL.

#### Scenario: Money type rejection
- **WHEN** application code attempts to persist cost with a float amount
- **THEN** the typed money helper MUST reject the value

### Requirement: Retry count counts outcome-delivery retries only
`retry_count` MUST count server-side re-attempts of `sale.commit@1`, a new current CashCount insert, or `closing.confirm@1` after a retryable failure, when recorded by the instrumentation hook as a new attempt. It MUST NOT count idempotent replay of the same key, equal-amount cash-count read-back, `closing.prepare@1`, Business Stream GET, Next Best Action GET, page reloads, or Flutter redraws. Merchant recounts MUST NOT increment `retry_count`.

#### Scenario: Idempotent close replay
- **WHEN** `closing.confirm@1` replays with the same idempotency key and payload hash
- **THEN** `retry_count` MUST remain unchanged

### Requirement: Estimated total cost admits partial completeness
`estimated_total_cost_amount` MUST be NULL when any monetary component required for an honest total is unavailable. **Approved for Build A:** model/token cost unavailable, infrastructure cost unavailable (no configured estimate), `estimated_total_cost_amount` NULL, `cost_completeness=partial`. Conversation-model attribution is deferred to a future slice. The system MUST NOT sum unavailable components as zero. When every monetary component is `measured` or `estimated` and a deterministic total rule exists, `cost_completeness` MAY be `complete` and `estimated_total_cost_amount` MAY be non-null. Build A MUST NOT claim `complete` while model or infrastructure cost is unavailable.

#### Scenario: Partial total is explicit
- **WHEN** an OutcomeCost row is finalized for a completed Daily Close in Build A
- **THEN** `cost_completeness` MUST be `partial` and `estimated_total_cost_amount` MUST be NULL

### Requirement: Outcome cost writes join OutcomeRun write transactions
An OutcomeCost row MUST be inserted when the OutcomeRun is first created for the day in `sale.commit@1` or repair paths, while the OutcomeRun is not `completed`. It MAY be updated while the OutcomeRun is `in_progress` or `ready`. It MUST be finalized in the same `closing.confirm@1` transaction before the OutcomeRun transitions to `completed`. Repair paths MUST NOT insert OutcomeCost after the OutcomeRun is already `completed`; they MUST insert or update cost while the run is `in_progress` or `ready`, then complete the run in that same transaction. Reads MUST NOT create or update OutcomeCost. Idempotent parent replay MUST NOT create a second row.

#### Scenario: Prepare does not write cost
- **WHEN** `closing.prepare@1` runs
- **THEN** `outcome_costs` MUST be unchanged by that read

#### Scenario: Rollback leaves no cost row
- **WHEN** the first `sale.commit@1` of the day fails before commit after preparing an OutcomeCost insert
- **THEN** that OutcomeCost row MUST NOT remain

### Requirement: Outcome cost freezes when the outcome completes
When the owning OutcomeRun `status` is `completed`, both `INSERT` and `UPDATE` on `operations.outcome_costs` MUST be rejected for every role. There MUST be no post-complete cost insert. Completed historical cost MUST NOT change silently. Build A MUST NOT provide in-place correction or a correction table; a later slice MAY add append-only correction semantics.

#### Scenario: Completed outcome blocks cost update
- **WHEN** an OutcomeRun is `completed` and an update attempts to change `retry_count`
- **THEN** the statement MUST fail

#### Scenario: Completed outcome blocks cost insert
- **WHEN** an OutcomeRun is `completed` and an insert attempts to add an OutcomeCost row
- **THEN** the statement MUST fail

### Requirement: Outcome cost is tenant scoped
`operations.outcome_costs` MUST `ENABLE` and `FORCE` ROW LEVEL SECURITY with policy `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`. `lumo_app` MUST be granted `SELECT`, `INSERT`, `UPDATE`, and `DELETE`. `business_id` MUST come from trusted tenant context or the owning OutcomeRun, never from an untrusted client parameter.

#### Scenario: Cross-tenant read returns nothing
- **WHEN** business A has an OutcomeCost row and the session is scoped to business B
- **THEN** a select of `operations.outcome_costs` MUST NOT return A's row

### Requirement: Outcome cost audit is create only on insert
Inserting an OutcomeCost MUST write one audit action `outcome_cost.created` in the same transaction. Updates MUST NOT write audit. Outcome cost MUST NOT enqueue an outbox event.

#### Scenario: Finalize without second audit
- **WHEN** `closing.confirm@1` updates an existing OutcomeCost before completion
- **THEN** no second `outcome_cost.created` audit MUST be written solely for that update

