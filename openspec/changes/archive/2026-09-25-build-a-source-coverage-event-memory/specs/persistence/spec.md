## MODIFIED Requirements

### Requirement: Alembic 0011 creates the daily close outcome
Alembic revision id MUST be `0011_daily_close_outcome` and `down_revision` MUST be `0010_work_items`. It MUST create `operations.outcome_runs` with the columns, checks, and unique keys required by `outcome-run-foundation`. It MUST add `uq_closing_snapshots_id_business_day` on `(id, business_id, operational_day_id)` without dropping the existing closing-snapshot unique keys. It MUST add nullable `operations.work_items.outcome_run_id` and composite foreign key `fk_work_items_outcome_run` from `(outcome_run_id, business_id, operational_day_id)` to `operations.outcome_runs (id, business_id, operational_day_id)`. It MUST `ENABLE` and `FORCE` ROW LEVEL SECURITY, create policy `tenant_isolation`, and grant `lumo_app` `SELECT`, `INSERT`, `UPDATE`, and `DELETE` on `operations.outcome_runs`. It MUST NOT insert an OutcomeRun or a WorkItem. It MUST NOT create schema `workflow` or `memory`, and it MUST NOT create `outcome_definitions`, `completion_evidence`, `next_best_actions`, source-coverage, event-memory, cost, or generic workflow tables. Downgrade MUST abort when any `outcome_runs` row exists. Otherwise it MUST drop `outcome_run_id` and `operations.outcome_runs`, and MUST drop `uq_closing_snapshots_id_business_day`. Existing WorkItem rows MAY remain.

#### Scenario: Upgrade does not backfill
- **WHEN** Alembic upgrades to exactly `0011_daily_close_outcome` on a database that already has an open OperationalDay and WorkItems
- **THEN** that revision MUST be `0011_daily_close_outcome`, `operations.outcome_runs` MUST exist and MUST contain no row, and every existing `outcome_run_id` MUST be null

#### Scenario: Downgrade with an outcome aborts
- **WHEN** any `outcome_runs` row exists and downgrade from `0011_daily_close_outcome` is attempted
- **THEN** the downgrade MUST abort and the row MUST remain

#### Scenario: Forbidden tables stay absent
- **WHEN** the database revision is exactly `0011_daily_close_outcome`
- **THEN** schemas `workflow` and `memory` MUST NOT exist, and `outcome_definitions`, `completion_evidence`, `source_coverage_records`, `business_events`, and `work_absorption_records` MUST NOT exist

## ADDED Requirements

### Requirement: Alembic 0012 creates source coverage and business events
Alembic revision id MUST be `0012_source_coverage_event_memory` and `down_revision` MUST be `0011_daily_close_outcome`. It MUST create `operations.source_coverage_records` and `operations.business_events` with the columns, checks, and unique keys required by `source-coverage` and `factual-event-memory`. `operations.source_coverage_records` MUST NOT include `updated_at`. It MUST `ENABLE` and `FORCE` ROW LEVEL SECURITY on both tables, create policy `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`, and grant `lumo_app` `SELECT`, `INSERT`, and `DELETE` only. It MUST NOT grant `UPDATE` on either table. It MUST create trigger `business_events_immutable` that rejects `UPDATE` for every role. It MUST NOT insert a coverage row or a business event. It MUST NOT create schema `workflow` or `memory`, a vector extension, an embeddings table, a generic knowledge table, a key-value memory store, or a recommendation table. `lumo_app` and `lumo_admin` MUST remain `NOBYPASSRLS`. Downgrade MUST abort when any `source_coverage_records` row or any `business_events` row exists. Otherwise it MUST drop both tables and MUST NOT drop `operations.outcome_runs`.

#### Scenario: Upgrade does not backfill
- **WHEN** Alembic upgrades a database that already has confirmed sales, a CashCount, and a ClosingSnapshot
- **THEN** the head revision MUST be `0012_source_coverage_event_memory`, both new tables MUST exist, and both MUST contain no row

#### Scenario: Downgrade with a row aborts
- **WHEN** any `source_coverage_records` or `business_events` row exists and downgrade from `0012_source_coverage_event_memory` is attempted
- **THEN** the downgrade MUST abort and the row MUST remain

#### Scenario: Memory schema and vector storage stay absent
- **WHEN** migration `0012` has been applied
- **THEN** schema `memory` MUST NOT exist, and no embeddings table or vector extension MUST exist

### Requirement: Reset deletes coverage and events before the operational day
Test and reset helpers that remove sale, cash-count, and close mutations MUST delete `operations.business_events` and `operations.source_coverage_records` before `operations.operational_days` in the same transaction. The existing order MUST remain `work_items` before `outcome_runs` before `closing_snapshots` before `cash_counts` before `operational_days`. Helpers MUST NOT require a new idempotency operation type.

#### Scenario: Cleanup removes the new rows with the day
- **WHEN** the reset helper clears a tenant after a confirmed close that wrote coverage and a `daily_close_completed` event
- **THEN** it MUST delete those coverage and event rows before `operational_days`, and no foreign-key error MUST occur
