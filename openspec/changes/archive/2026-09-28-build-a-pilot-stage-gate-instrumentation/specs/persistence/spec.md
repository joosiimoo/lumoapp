## ADDED Requirements

### Requirement: Pilot enrollment is persisted per business
Migration `0014_pilot_stage_gate_instrumentation` MUST create `operations.pilot_program_enrollments` with `id` (UUIDv7), `business_id`, `cohort_code`, `pilot_started_on` (date), nullable `pilot_ended_on`, and `created_at`. A business MUST NOT have two overlapping active enrollments for the same `cohort_code`. Foreign key MUST bind `business_id` to the tenant business row. Table MUST `ENABLE` and `FORCE` RLS with `tenant_isolation` on `business_id`.

#### Scenario: Second overlapping enrollment is rejected
- **WHEN** an active enrollment exists and a second insert overlaps dates for the same business and cohort
- **THEN** the database MUST reject the insert

### Requirement: Perception and assessment tables follow operations RLS
`operations.pilot_perception_responses` and `operations.stage_gate_assessments` MUST use the same RLS pattern as other `operations` tables for rows with non-null `business_id`. Cohort-scoped assessments with null `business_id` MUST NOT be readable by `lumo_app` merchant sessions; only trusted internal roles defined in the migration MAY read or insert them.

#### Scenario: Perception row is tenant isolated
- **WHEN** business A stores a perception response and session is scoped to business B
- **THEN** the row MUST NOT be visible

### Requirement: Assessment immutability is enforced
`operations.stage_gate_assessments` MUST reject `UPDATE` and `DELETE` after `finalized_at` is set. `criterion_results` and `included_outcome_run_refs` MUST be JSONB with structured schema validated in domain layer before insert.

#### Scenario: Finalized assessment cannot change
- **WHEN** an assessment row has non-null `finalized_at`
- **THEN** an `UPDATE` to `overall_status` MUST fail at the database

### Requirement: Migration head follows work absorption
Revision `0014_pilot_stage_gate_instrumentation` MUST revise `0013_work_absorption_outcome_cost`. Downgrade MUST be blocked while perception or assessment rows exist, consistent with other operations migrations.

#### Scenario: Upgrade from 0013
- **WHEN** database is at `0013_work_absorption_outcome_cost` and upgrade runs
- **THEN** revision MUST become `0014_pilot_stage_gate_instrumentation`
