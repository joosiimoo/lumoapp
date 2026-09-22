## MODIFIED Requirements

### Requirement: Sale integrity rows match live mutations
Committed conversational sale, cash-count, and close-confirmation mutations MUST keep `sales.sale_sessions`, `sales.sale_items`, `sales.payments`, `operations.operational_days` referenced by those sessions, `operations.cash_counts` referencing those days, `operations.closing_snapshots` referencing those days and current counts, related `audit.audit_events`, `platform.outbox_events`, and `platform.idempotency_records` transactionally consistent. Test/reset helpers that remove those mutations MUST delete the related integrity rows in the same transaction, including `sale.totalize@1` / `sale.commit@1` / `operational_day.opened` / `closing.submit_cash_count@1` / `closing.confirm@1` audit, `sale.ready_to_charge` / `sale.confirmed` / `payment.recorded` / `operational_day.opened` / `cash_count.recorded` / `closing.confirmed` outbox, and `lumo.message.totalize_sale` / `lumo.message.commit_sale` / `lumo.message.record_cash_count` / `lumo.message.confirm_close` idempotency. Helpers MUST delete `closing_snapshots` before `cash_counts` before `operational_days`.

#### Scenario: No orphan sale outbox
- **WHEN** a `sale.item.added`, `sale.ready_to_charge`, `sale.confirmed`, `payment.recorded`, `operational_day.opened`, `cash_count.recorded`, or `closing.confirmed` outbox row exists for a tenant
- **THEN** the referenced `sale_session_id`, `operational_day_id`, `cash_count_id`, `closing_snapshot_id`, and, when present, `sale_item_id` or `payment_id` MUST exist unless the entire mutation was rolled back (in which case the outbox row MUST NOT exist)

#### Scenario: Cleanup removes snapshots before counts and days
- **WHEN** the reset helper clears a tenant's mutations after a confirmed close
- **THEN** it MUST delete `operations.closing_snapshots` before `operations.cash_counts` before `operations.operational_days` in one transaction, no foreign-key error MUST occur, and no `closing.confirm@1` audit, `closing.confirmed` outbox, or `lumo.message.confirm_close` idempotency row MUST remain

#### Scenario: Orphan checks cover cash counts and snapshots
- **WHEN** the integrity check runs for a tenant
- **THEN** it MUST flag a cash count whose `operational_day_id` is missing, a broken `supersedes_cash_count_id` or `superseded_by_id` link, a supersede link pointing at a row with a different `business_id`, more than one current cash count for a day, a snapshot whose day or cash count is missing or in another business, a snapshot count whose day disagrees, more than one snapshot for a day, a `closed` day without exactly one snapshot, an `open` day with a snapshot, a referenced count that is not current, an internally inconsistent snapshot, and an audit or outbox row referencing a missing `cash_count_id` or `closing_snapshot_id`

## ADDED Requirements

### Requirement: Daily close confirmation migration
Alembic revision id MUST be `0007_daily_close_confirmation` and `down_revision` MUST be `0006_cash_count`. It MUST replace `ck_operational_days_status` so `status IN ('open', 'closed')`. It MUST add `uq_cash_counts_id_business_day` on `(id, business_id, operational_day_id)` without dropping `uq_cash_counts_id_business`. It MUST create `operations.closing_snapshots` with the columns, CHECKs, unique keys, composite foreign keys, `ENABLE` and `FORCE` ROW LEVEL SECURITY, policy `tenant_isolation`, and `lumo_app` `SELECT`/`INSERT`/`DELETE` without `UPDATE`, as required by `closing-snapshot-foundation`. It MUST create `closing_snapshots_immutable`, function `operations.assert_closing_snapshot_cardinality()` as `SECURITY DEFINER` with `search_path` limited to `operations` and `pg_temp`, and deferred constraint triggers `closing_snapshots_match_day` and `operational_days_match_snapshot` with the events, commit rules, and tenant-GUC save/set/restore rules in `closing-snapshot-foundation`. The function owner MUST stay a non-superuser without `BYPASSRLS`. The migration MUST NOT grant `BYPASSRLS`, MUST NOT create a bypass role, and MUST NOT weaken `FORCE ROW LEVEL SECURITY`. `SECURITY DEFINER` MUST NOT be described or implemented as a bypass of `FORCE RLS`. There MUST be no backfill. Existing operational days MUST remain `open`. No snapshot row MUST be inserted by the migration. It MUST NOT create `workflow`, `memory`, `work_items`, `outcome_runs`, or reopen tables. Downgrade MUST abort if any `operational_days.status` is `closed` or any `closing_snapshots` row exists. When neither exists, downgrade MUST drop `closing_snapshots_immutable`, both deferred constraint triggers, `operations.assert_closing_snapshot_cardinality()`, and `closing_snapshots`, drop `uq_cash_counts_id_business_day`, and restore `ck_operational_days_status` to `status IN ('open')`. Downgrade MUST NOT rewrite `closed` to `open` and MUST NOT delete sales, payments, cash counts, or day rows.

#### Scenario: Upgrade from the cash-count head
- **WHEN** Alembic upgrade completes on a database whose revision is `0006_cash_count` and that database already has open days and cash counts
- **THEN** the head revision id MUST be `0007_daily_close_confirmation`, those day and count rows MUST be unchanged, `ck_operational_days_status` MUST allow `open` and `closed`, `operations.closing_snapshots` MUST exist with FORCE RLS, and no snapshot row MUST have been inserted

#### Scenario: Downgrade refuses a confirmed close
- **WHEN** a `closed` day or a `closing_snapshots` row exists and downgrade from `0007_daily_close_confirmation` is attempted
- **THEN** the downgrade MUST abort and the snapshot and `closed` status MUST remain

#### Scenario: Downgrade of an unconfirmed database
- **WHEN** every operational day is `open`, no snapshot row exists, and the database is downgraded to `0006_cash_count`
- **THEN** `operations.closing_snapshots` MUST NOT exist and `ck_operational_days_status` MUST allow only `open`

#### Scenario: Close rollback is consistent
- **WHEN** a confirm writes a snapshot, sets `status=closed`, writes audit and outbox, and the transaction fails before commit
- **THEN** the day MUST remain `open`, no snapshot MUST remain, and no `closing.confirm@1` audit or `closing.confirmed` outbox row MUST remain

#### Scenario: Direct close without a snapshot fails at commit
- **WHEN** a migration-level transaction updates an existing open day to `status=closed` without inserting a snapshot and then commits
- **THEN** `COMMIT` MUST fail and the day MUST still be `open` with zero snapshots

#### Scenario: Direct snapshot on an open day fails at commit
- **WHEN** a migration-level transaction inserts a `closing_snapshots` row for an open day and then commits
- **THEN** `COMMIT` MUST fail and that snapshot MUST NOT remain

#### Scenario: Snapshot and closed status commit together
- **WHEN** a migration-level transaction inserts a snapshot for an open day and sets that day to `status=closed` before commit
- **THEN** `COMMIT` MUST succeed with exactly one snapshot and `status=closed`

#### Scenario: Deleting a closed day's snapshot fails at commit
- **WHEN** a migration-level transaction deletes the only snapshot of a `closed` day and then commits
- **THEN** `COMMIT` MUST fail and the snapshot MUST remain

#### Scenario: Same-transaction cleanup of a closed day succeeds
- **WHEN** a migration-level transaction deletes the snapshot, then the cash counts, then the operational day, and then commits
- **THEN** `COMMIT` MUST succeed and neither the day nor the snapshot MUST remain

#### Scenario: Unset tenant GUC still rejects a close without a snapshot
- **WHEN** an administrative connection sets `app.current_business_id` to the day's business, updates that open day to `status=closed` without a snapshot, clears `app.current_business_id` so it is unset, and commits
- **THEN** `COMMIT` MUST fail and the day MUST remain `open`

#### Scenario: Wrong caller GUC does not hide the affected business
- **WHEN** an administrative connection updates an open day to `status=closed` without a snapshot while `app.current_business_id` is that day's business, then sets `app.current_business_id` to a different business and commits
- **THEN** `COMMIT` MUST fail and the day MUST remain `open`

#### Scenario: Successful validation restores the caller GUC
- **WHEN** `app.current_business_id` is business A and a valid snapshot-plus-close passes `SET CONSTRAINTS ALL IMMEDIATE`
- **THEN** `current_setting('app.current_business_id', true)` MUST still be business A before `COMMIT`

#### Scenario: Failed validation restores the caller GUC
- **WHEN** business A is set at session scope, a transaction makes a cardinality violation, and the validator raises
- **THEN** after that transaction ends, `current_setting('app.current_business_id', true)` MUST still be business A

#### Scenario: Previously unset GUC is effectively unset
- **WHEN** `app.current_business_id` is unset and a valid open-day check runs to completion inside the transaction on PostgreSQL 16.14
- **THEN** `current_setting('app.current_business_id', true)` MUST equal `''`, MUST NOT equal the affected business id, and a tenant-scoped read under that setting MUST return zero rows

#### Scenario: Normal tenant close still commits
- **WHEN** `lumo_app` inserts the snapshot and sets the day from `open` to `closed` under the Carrota `app.current_business_id`
- **THEN** `COMMIT` MUST succeed and the caller GUC MUST still be Carrota

#### Scenario: Cleanup leaves the caller GUC unchanged
- **WHEN** one transaction deletes the snapshot, the cash counts, and the day while `app.current_business_id` is business A
- **THEN** `COMMIT` MUST succeed and `current_setting('app.current_business_id', true)` MUST still be business A
