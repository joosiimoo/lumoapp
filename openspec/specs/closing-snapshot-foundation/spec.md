## Purpose

Immutable `ClosingSnapshot` for one accepted daily close: frozen totals, two-sided deferred cardinality, and a tenant-GUC save/set/restore that treats PostgreSQL 16.14 `''` as no active tenant.

## Requirements

### Requirement: ClosingSnapshot freezes one accepted close
Persistence MUST create `operations.closing_snapshots` in the existing `operations` schema. A `ClosingSnapshot` MUST include `id` (UUIDv7), `business_id`, `operational_day_id`, `cash_count_id`, `actor_id`, `business_date` (`DATE`), `currency` (`VARCHAR(3)`), `sale_count` (`INTEGER`), `gross_sales_total`, `cash_total`, `card_total`, `transfer_total`, `expected_cash`, `counted_cash`, and `cash_difference` as `numeric(12,2)`, `cash_status` (`VARCHAR(16)`), `closed_at` (`timestamptz`), `created_at`, and `updated_at`. Domain `ClosingSnapshot` MUST NOT be a SQLAlchemy model and MUST NOT import SQLAlchemy, FastAPI, or Flutter. Money MUST be `Decimal` / `numeric` and MUST NEVER be binary float. `actor_id` MUST be the closer copied from `TenantContext`. There MUST NOT be a second `closed_by` column. The table MUST NOT store denominations, a note, evidence ids, source coverage, an outcome id, product rows, a tolerance, an opening float, or a version number. `UNIQUE (operational_day_id)`, `UNIQUE (id, business_id)`, and `UNIQUE (cash_count_id)` MUST exist. Foreign key `(operational_day_id, business_id)` MUST reference `operations.operational_days (id, business_id)`. Foreign key `(cash_count_id, business_id, operational_day_id)` MUST reference `operations.cash_counts (id, business_id, operational_day_id)`, which requires `UNIQUE (id, business_id, operational_day_id)` named `uq_cash_counts_id_business_day`. Existing `uq_cash_counts_id_business` MUST remain. Schemas `workflow` and `memory` MUST NOT be created.

#### Scenario: One snapshot per day
- **WHEN** a close confirmation commits for an open OperationalDay
- **THEN** exactly one `operations.closing_snapshots` row MUST exist for that `operational_day_id`, its `business_id` MUST equal the day's `business_id`, and a second snapshot for that day MUST be rejected

#### Scenario: Snapshot cannot point at another day's count
- **WHEN** an insert sets `cash_count_id` to a `CashCount` whose `operational_day_id` or `business_id` differs from the snapshot
- **THEN** the database MUST reject the row

### Requirement: Snapshot values are internally consistent
Database CHECKs MUST enforce `sale_count >= 0`, non-negative `gross_sales_total`, `cash_total`, `card_total`, `transfer_total`, `expected_cash`, and `counted_cash`, `expected_cash = cash_total`, `gross_sales_total = cash_total + card_total + transfer_total`, and `cash_difference = counted_cash - expected_cash`. `cash_status` MUST be `over` when `cash_difference > 0`, `short` when `cash_difference < 0`, and `balanced` when `cash_difference = 0`. `not_counted` MUST NOT be a legal snapshot status. `created_at` and `updated_at` MUST both equal `closed_at` and MUST be set explicitly from the confirm transaction's clock reading.

#### Scenario: Shortage is stored exactly
- **WHEN** a snapshot is inserted with `expected_cash` `22.50` and `counted_cash` `20.00`
- **THEN** `cash_difference` MUST be `-2.50` and `cash_status` MUST be `short`

#### Scenario: Inconsistent totals are rejected
- **WHEN** an insert sets `expected_cash` different from `cash_total`, or `cash_status=balanced` while `cash_difference` is not zero
- **THEN** the database MUST reject the row

### Requirement: ClosingSnapshot is immutable in product operation
`lumo_app` MUST receive `SELECT`, `INSERT`, and `DELETE` on `operations.closing_snapshots` and MUST NOT receive `UPDATE`. A `BEFORE UPDATE` trigger `closing_snapshots_immutable` MUST raise for every role. No application path MAY update a snapshot column after insert. No product workflow, including `closing.confirm@1`, `closing.prepare@1`, `closing.submit_cash_count@1`, and `sale.commit@1`, MAY delete or rewrite a `ClosingSnapshot`. There MUST be no replacement row and no version chain. `DELETE` MUST remain granted so the existing tenant reset can remove a snapshot in the same transaction that removes its day. That reset is not a product workflow and MUST NOT reopen a day.

#### Scenario: Update is rejected
- **WHEN** any role attempts to update `counted_cash` or `cash_difference` on an existing snapshot
- **THEN** the statement MUST fail and the original values MUST remain

#### Scenario: Confirm does not delete the snapshot
- **WHEN** `closing.confirm@1` commits
- **THEN** the inserted snapshot MUST still exist and no product path MUST have updated or deleted it

### Requirement: Day and snapshot cardinality is enforced from both tables
An `open` `OperationalDay` MUST have zero `ClosingSnapshot` rows. A `closed` `OperationalDay` MUST have exactly one. No other `status` is legal. Enforcement MUST be the function `operations.assert_closing_snapshot_cardinality()`, `SECURITY DEFINER`, with `search_path` limited to `operations` and `pg_temp`, owned by the owner of `operations.operational_days`. `SECURITY DEFINER` MUST NOT be treated as bypassing `FORCE ROW LEVEL SECURITY`. The owner MUST remain a non-superuser without `BYPASSRLS`, and this change MUST NOT grant `BYPASSRLS` or create a bypass role. `lumo_app` MUST remain without `BYPASSRLS`. Each execution MUST take `target_day_id` and `target_business_id` only from `NEW` or `OLD` and MUST follow the tenant-GUC requirement below. It MUST run from two `FOR EACH ROW` constraint triggers, both `DEFERRABLE INITIALLY DEFERRED`:

- `closing_snapshots_match_day` on `operations.closing_snapshots` for `AFTER INSERT` and `AFTER DELETE`. Snapshot `UPDATE` MUST NOT be one of its events.
- `operational_days_match_snapshot` on `operations.operational_days` for `AFTER INSERT`, `AFTER UPDATE OF status`, and `AFTER DELETE`.

At `COMMIT` the function MUST see the final rows for that pair. A missing day with zero snapshots MUST succeed. A missing day that still has a snapshot MUST fail. `open` MUST have `snapshot_count = 0`. `closed` MUST have `snapshot_count = 1`. The confirm transaction MUST be allowed to insert the snapshot while the day is still `open` and then set `status=closed` before `COMMIT`. The foreign key from snapshot to day MUST stay immediate.

#### Scenario: Closed without a snapshot fails at commit
- **WHEN** a transaction sets `operations.operational_days.status` to `closed` for a day that has no snapshot and then commits
- **THEN** `COMMIT` MUST fail because `operational_days_match_snapshot` ran, and rollback MUST leave that day `open` with zero snapshots

#### Scenario: Snapshot on an open day fails at commit
- **WHEN** a transaction inserts a `closing_snapshots` row and leaves that day's `status` as `open`
- **THEN** `COMMIT` MUST fail and no snapshot row MUST remain

#### Scenario: Atomic close commits
- **WHEN** one transaction inserts the snapshot and then sets that day's `status` to `closed`
- **THEN** `COMMIT` MUST succeed with `status=closed` and exactly one snapshot

#### Scenario: Deleting the snapshot of a closed day fails at commit
- **WHEN** a transaction deletes the only snapshot of a `closed` day and does not delete that day
- **THEN** `COMMIT` MUST fail and the snapshot MUST still exist after rollback

#### Scenario: Cleanup of snapshot and day commits
- **WHEN** one transaction deletes that day's `closing_snapshots` row, then its `cash_counts` rows, then its `operational_days` row
- **THEN** `COMMIT` MUST succeed, and neither the day nor the snapshot MUST remain

### Requirement: Cardinality validator sets and restores the tenant GUC
Before `operations.assert_closing_snapshot_cardinality()` queries `operations.operational_days` or `operations.closing_snapshots`, it MUST save `current_setting('app.current_business_id', true)` and then call `set_config('app.current_business_id', target_business_id::text, true)`. `target_business_id` MUST come from the trigger row. The cardinality queries MUST filter to `business_id = target_business_id` and to that day id, and MUST NOT scan other tenants. `set_config` MUST use the local flag `true`. The function MUST NOT use dynamic SQL, MUST NOT try to force the custom GUC back to SQL NULL, and MUST NOT `RESET` the session value. Before every normal return, and in the exception handler before every `RAISE`, it MUST restore the caller context. A NULL saved value means the setting was never initialized and MUST be restored with `SET LOCAL app.current_business_id TO DEFAULT`. On PostgreSQL 16.14 that leaves `current_setting('app.current_business_id', true) = ''`, which is an effectively unset tenant: `business_id::text = ''` matches no business UUID. True SQL NULL is required only when the custom GUC was never initialized in the session. Any non-NULL saved value, including the empty string, MUST be restored with `set_config('app.current_business_id', saved_value, true)`. A non-empty caller UUID MUST be restored exactly. After the function returns or raises, the target business UUID MUST NOT remain the caller's setting. `NULL` and `''` both mean no active tenant. The RLS policy MUST NOT be changed so that `''` matches a business.

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
- **WHEN** `lumo_app` runs the snapshot insert and `open` to `closed` update under the Carrota `app.current_business_id`
- **THEN** `COMMIT` MUST succeed and the caller GUC MUST still be Carrota

#### Scenario: Cleanup restores the caller GUC
- **WHEN** one transaction deletes the snapshot, the cash counts, and the day while `app.current_business_id` is business A
- **THEN** `COMMIT` MUST succeed and `current_setting('app.current_business_id', true)` MUST still be business A

### Requirement: ClosingSnapshot is tenant scoped
The table MUST ENABLE and FORCE ROW LEVEL SECURITY with policy `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`. `business_id` MUST be copied from `TenantContext` and MUST NEVER come from client, interpreter, or tool input. A snapshot MUST NOT be readable under another business's tenant setting.

#### Scenario: Another business cannot read the snapshot
- **WHEN** business B queries `operations.closing_snapshots` under its own `app.current_business_id` after Carrota has confirmed a close
- **THEN** Carrota's snapshot MUST NOT be returned
