## MODIFIED Requirements

### Requirement: Sale integrity rows match live mutations
Committed conversational sale, cash-count, and close-confirmation mutations MUST keep `sales.sale_sessions`, `sales.sale_items`, `sales.payments`, `operations.operational_days` referenced by those sessions, `operations.cash_counts` referencing those days, `operations.closing_snapshots` referencing those days and current counts, `operations.work_items` referencing those days, `operations.outcome_runs` referencing those days, related `audit.audit_events`, `platform.outbox_events`, and `platform.idempotency_records` transactionally consistent. Test/reset helpers that remove those mutations MUST delete the related integrity rows in the same transaction, including `sale.totalize@1` / `sale.commit@1` / `operational_day.opened` / `closing.submit_cash_count@1` / `closing.confirm@1` / `work_item.created` / `work_item.resolved` / `outcome_run.created` / `outcome_run.status_changed` audit, `sale.ready_to_charge` / `sale.confirmed` / `payment.recorded` / `operational_day.opened` / `cash_count.recorded` / `closing.confirmed` outbox, and `lumo.message.totalize_sale` / `lumo.message.commit_sale` / `lumo.message.record_cash_count` / `lumo.message.confirm_close` idempotency. Helpers MUST delete `work_items` before `outcome_runs` before `closing_snapshots` before `cash_counts` before `operational_days`.

#### Scenario: No orphan sale outbox
- **WHEN** a `sale.item.added`, `sale.ready_to_charge`, `sale.confirmed`, `payment.recorded`, `operational_day.opened`, `cash_count.recorded`, or `closing.confirmed` outbox row exists for a tenant
- **THEN** the referenced `sale_session_id`, `operational_day_id`, `cash_count_id`, `closing_snapshot_id`, and, when present, `sale_item_id` or `payment_id` MUST exist unless the entire mutation was rolled back (in which case the outbox row MUST NOT exist)

#### Scenario: Cleanup removes work items before outcomes and snapshots
- **WHEN** the reset helper clears a tenant's mutations after a confirmed close
- **THEN** it MUST delete `operations.work_items` before `operations.outcome_runs` before `operations.closing_snapshots` before `operations.cash_counts` before `operations.operational_days` in one transaction, no foreign-key error MUST occur, and no `closing.confirm@1` audit, `outcome_run.created` audit, `work_item.created` audit, `closing.confirmed` outbox, or `lumo.message.confirm_close` idempotency row MUST remain

#### Scenario: Orphan checks cover outcomes
- **WHEN** the integrity check runs for a tenant
- **THEN** it MUST flag a cash count whose `operational_day_id` is missing, a broken `supersedes_cash_count_id` or `superseded_by_id` link, a supersede link pointing at a row with a different `business_id`, more than one current cash count for a day, a snapshot whose day or cash count is missing or in another business, a snapshot count whose day disagrees, more than one snapshot for a day, a `closed` day without exactly one snapshot, an `open` day with a snapshot, a referenced count that is not current, an internally inconsistent snapshot, an audit or outbox row referencing a missing `cash_count_id` or `closing_snapshot_id`, more than one OutcomeRun for a day and `daily_close_ready` version `1`, an OutcomeRun whose day is missing or in another business, a `completed` OutcomeRun whose `closing_snapshot_id` is not that day's snapshot, a `completed` OutcomeRun on an `open` day, and an `open` day whose OutcomeRun is `completed`

## ADDED Requirements

### Requirement: Alembic 0011 creates the daily close outcome
Alembic revision id MUST be `0011_daily_close_outcome` and `down_revision` MUST be `0010_work_items`. It MUST create `operations.outcome_runs` with the columns, checks, and unique keys required by `outcome-run-foundation`. It MUST add `uq_closing_snapshots_id_business_day` on `(id, business_id, operational_day_id)` without dropping the existing closing-snapshot unique keys. It MUST add nullable `operations.work_items.outcome_run_id` and composite foreign key `fk_work_items_outcome_run` from `(outcome_run_id, business_id, operational_day_id)` to `operations.outcome_runs (id, business_id, operational_day_id)`. It MUST `ENABLE` and `FORCE` ROW LEVEL SECURITY, create policy `tenant_isolation`, and grant `lumo_app` `SELECT`, `INSERT`, `UPDATE`, and `DELETE` on `operations.outcome_runs`. It MUST NOT insert an OutcomeRun or a WorkItem. It MUST NOT create schema `workflow` or `memory`, and it MUST NOT create `outcome_definitions`, `completion_evidence`, `next_best_actions`, source-coverage, event-memory, cost, or generic workflow tables. Downgrade MUST abort when any `outcome_runs` row exists. Otherwise it MUST drop `outcome_run_id` and `operations.outcome_runs`, and MUST drop `uq_closing_snapshots_id_business_day`. Existing WorkItem rows MAY remain.

#### Scenario: Upgrade does not backfill
- **WHEN** Alembic upgrades a database that already has an open OperationalDay and WorkItems
- **THEN** the head revision MUST be `0011_daily_close_outcome`, `operations.outcome_runs` MUST exist and MUST contain no row, and every existing `outcome_run_id` MUST be null

#### Scenario: Downgrade with an outcome aborts
- **WHEN** any `outcome_runs` row exists and downgrade from `0011_daily_close_outcome` is attempted
- **THEN** the downgrade MUST abort and the row MUST remain

#### Scenario: Forbidden tables stay absent
- **WHEN** migration `0011` has been applied
- **THEN** schemas `workflow` and `memory` MUST NOT exist, and `outcome_definitions`, `completion_evidence`, `source_coverage_records`, and `work_absorption_records` MUST NOT exist
