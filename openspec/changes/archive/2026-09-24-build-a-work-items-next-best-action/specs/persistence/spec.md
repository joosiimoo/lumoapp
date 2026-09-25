## MODIFIED Requirements

### Requirement: Sale integrity rows match live mutations
Committed conversational sale, cash-count, and close-confirmation mutations MUST keep `sales.sale_sessions`, `sales.sale_items`, `sales.payments`, `operations.operational_days` referenced by those sessions, `operations.cash_counts` referencing those days, `operations.closing_snapshots` referencing those days and current counts, `operations.work_items` referencing those days, related `audit.audit_events`, `platform.outbox_events`, and `platform.idempotency_records` transactionally consistent. Test/reset helpers that remove those mutations MUST delete the related integrity rows in the same transaction, including `sale.totalize@1` / `sale.commit@1` / `operational_day.opened` / `closing.submit_cash_count@1` / `closing.confirm@1` / `work_item.created` / `work_item.resolved` audit, `sale.ready_to_charge` / `sale.confirmed` / `payment.recorded` / `operational_day.opened` / `cash_count.recorded` / `closing.confirmed` outbox, and `lumo.message.totalize_sale` / `lumo.message.commit_sale` / `lumo.message.record_cash_count` / `lumo.message.confirm_close` idempotency. Helpers MUST delete `closing_snapshots` before `cash_counts` before `work_items` before `operational_days`.

#### Scenario: No orphan sale outbox
- **WHEN** a `sale.item.added`, `sale.ready_to_charge`, `sale.confirmed`, `payment.recorded`, `operational_day.opened`, `cash_count.recorded`, or `closing.confirmed` outbox row exists for a tenant
- **THEN** the referenced `sale_session_id`, `operational_day_id`, `cash_count_id`, `closing_snapshot_id`, and, when present, `sale_item_id` or `payment_id` MUST exist unless the entire mutation was rolled back (in which case the outbox row MUST NOT exist)

#### Scenario: Cleanup removes snapshots before counts and days
- **WHEN** the reset helper clears a tenant's mutations after a confirmed close
- **THEN** it MUST delete `operations.closing_snapshots` before `operations.cash_counts` before `operations.work_items` before `operations.operational_days` in one transaction, no foreign-key error MUST occur, and no `closing.confirm@1` audit, `work_item.created` audit, `closing.confirmed` outbox, or `lumo.message.confirm_close` idempotency row MUST remain

#### Scenario: Orphan checks cover cash counts and snapshots
- **WHEN** the integrity check runs for a tenant
- **THEN** it MUST flag a cash count whose `operational_day_id` is missing, a broken `supersedes_cash_count_id` or `superseded_by_id` link, a supersede link pointing at a row with a different `business_id`, more than one current cash count for a day, a snapshot whose day or cash count is missing or in another business, a snapshot count whose day disagrees, more than one snapshot for a day, a `closed` day without exactly one snapshot, an `open` day with a snapshot, a referenced count that is not current, an internally inconsistent snapshot, and an audit or outbox row referencing a missing `cash_count_id` or `closing_snapshot_id`

### Requirement: Daily sales export adds no persistence
Daily sales export MUST NOT add an Alembic revision of its own. It MUST NOT create `export_jobs`, an export-history table, a checksum column, or an object-storage pointer. Generating a file MUST NOT insert or update `audit.audit_events`, `platform.outbox_events`, or `platform.idempotency_records`.

#### Scenario: Export schema is unchanged
- **WHEN** the export feature is present and migrations are inspected
- **THEN** `export_jobs` MUST NOT exist

#### Scenario: A download writes no integrity row
- **WHEN** a tenant downloads CSV and XLSX for one day
- **THEN** audit, outbox, and idempotency row counts for that business MUST be unchanged by those requests

## ADDED Requirements

### Requirement: Alembic 0010 creates work items
Alembic revision id MUST be `0010_work_items` and `down_revision` MUST be `0009_catalog_price_override`. It MUST create `operations.work_items` with the columns and checks required by `work-item-foundation`, unique constraint support for `(id, business_id)` if needed by the composite key, composite foreign key `fk_work_items_operational_day` from `(operational_day_id, business_id)` to `operations.operational_days (id, business_id)`, and partial unique index `uq_work_items_one_open` on `(business_id, operational_day_id, type)` WHERE `status = 'open'`. It MUST `ENABLE` and `FORCE` ROW LEVEL SECURITY, create policy `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`, and grant `lumo_app` `SELECT`, `INSERT`, `UPDATE`, and `DELETE`. It MUST NOT insert a WorkItem. It MUST NOT create schema `workflow` or `memory`, a `next_best_actions` table, or an `outcome_runs` table. Downgrade MUST abort when any `work_items` row exists and otherwise MUST drop only `operations.work_items`.

#### Scenario: Upgrade does not backfill
- **WHEN** Alembic upgrades a database that already has an open OperationalDay
- **THEN** the head revision MUST be `0010_work_items`, `operations.work_items` MUST exist, and that table MUST contain no row

#### Scenario: Downgrade with rows aborts
- **WHEN** any `work_items` row exists and downgrade from `0010_work_items` is attempted
- **THEN** the downgrade MUST abort and the row MUST remain
