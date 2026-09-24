## Purpose

PostgreSQL is the system of record. Persistence uses SQLAlchemy 2, Alembic, UUIDv7, `timestamptz`, Decimal money, foundation schemas `identity`, `audit`, and `platform`, product schemas `catalog` and `sales` (`sale_sessions`, `sale_items`, `payments`), and product schema `operations` (`operational_days`, `cash_counts`, `closing_snapshots`). Schemas `workflow` and `memory` remain absent. Head revision is `0007_daily_close_confirmation`.
## Requirements
### Requirement: PostgreSQL is the system of record
Confirmed application state MUST persist only in PostgreSQL. The backend MUST use SQLAlchemy 2 in the infrastructure layer and Alembic for schema migrations. Domain entities MUST NOT be SQLAlchemy models.

#### Scenario: Migration applies
- **WHEN** Alembic upgrade runs against an empty database
- **THEN** the platform tables required by this change MUST exist

#### Scenario: ORM isolation
- **WHEN** domain modules are imported
- **THEN** they MUST NOT load SQLAlchemy mapped classes

### Requirement: Identity, money, and time conventions
New persisted identifiers MUST be UUIDv7. Timestamps MUST be stored as `timestamptz` in UTC. Monetary amounts MUST use exact decimal types (`numeric` in PostgreSQL, `Decimal` in Python) and MUST NEVER use binary floating point. JSON money representations MUST be decimal strings plus an ISO 4217 currency code.

#### Scenario: Money type rejection
- **WHEN** code attempts to persist or calculate money with a `float`
- **THEN** the typed money helper or schema MUST reject the value

#### Scenario: Timestamp storage
- **WHEN** a platform row is inserted
- **THEN** its `created_at` MUST be a UTC `timestamptz`

### Requirement: Transaction boundaries
A use case that mutates state MUST run inside a single database transaction. A failure before commit MUST roll back all writes from that operation, including audit and idempotency updates that belong to the same operation. Success responses MUST be produced only after commit.

#### Scenario: Rollback leaves no partial writes
- **WHEN** a mutating use case raises after writing a domain row and an audit row in the same transaction
- **THEN** neither row MUST remain after the request completes

#### Scenario: No success before commit
- **WHEN** a transaction rolls back
- **THEN** the API MUST NOT return a success payload for that operation

### Requirement: Platform schemas
Persistence MUST create PostgreSQL schemas `identity`, `audit`, and `platform` for foundation tables, and MUST create product schemas `catalog` and `sales` for `products`, optional `product_aliases`, `sale_sessions`, `sale_items`, and `payments`. Product schema `operations` MUST contain `operational_days` and `cash_counts` only. Product schemas `workflow` and `memory` MUST NOT exist. Tables for export jobs, closing snapshots, work items, outcome runs, and payment-method configuration MUST NOT exist.

#### Scenario: Foundation tables present
- **WHEN** migrations complete
- **THEN** `businesses`, `users`, `memberships`, `audit_events`, `idempotency_records`, and `outbox_events` MUST exist in the foundation schemas

#### Scenario: Catalog and sales schemas present
- **WHEN** catalog and sales migrations complete
- **THEN** PostgreSQL schemas `catalog` and `sales` MUST exist, and tables for catalog products, sale sessions, sale items, and payments MUST exist

#### Scenario: Operations schema holds days and cash counts
- **WHEN** Alembic `0006` completes
- **THEN** PostgreSQL schema `operations` MUST contain exactly `operational_days` and `cash_counts`, and schemas `workflow` and `memory` MUST NOT exist

#### Scenario: Close tables stay absent
- **WHEN** the database is inspected after `0006`
- **THEN** `closing_snapshots`, `work_items`, `outcome_runs`, and `export_jobs` MUST NOT exist

### Requirement: Local PostgreSQL host port
Local Compose MUST publish the Postgres container, which already listens on `5432` internally, to the host as `5432:5432`. README, pytest defaults, and local scripts MUST use `localhost:5432`. They MUST NOT assume host port `5433`.

#### Scenario: Host mapping
- **WHEN** a developer runs `docker compose up` locally
- **THEN** PostgreSQL MUST be reachable on `localhost:5432`

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

### Requirement: SaleSession status persistence
`sales.sale_sessions.status` MUST allow `open`, `ready_to_charge`, and `confirmed`. `conversation_id` MUST remain `VARCHAR(128) NULL` as created in `0002_catalog_sales`. Migration `0004` MUST replace `ck_sale_sessions_status` so status IN (`open`, `ready_to_charge`, `confirmed`) and MUST keep unique index `uq_sale_sessions_active_context` unchanged:

```sql
CREATE UNIQUE INDEX uq_sale_sessions_active_context
ON sales.sale_sessions (business_id, actor_id, COALESCE(conversation_id, ''))
WHERE status IN ('open', 'ready_to_charge');
```

Migration revision `0005_operational_day` MUST add nullable `operational_day_id` and `confirmed_at` without adding `confirmed` to that unique index, without a session total column, and without replacing `COALESCE(conversation_id, '')`. Its `down_revision` MUST be `0004_confirmed_payment`, which is the Alembic revision id inside `0004_sale_session_confirmed_payment.py`, not that filename. The membership CHECK MUST be added only after legacy `confirmed` rows are backfilled. After that CHECK, `confirmed` rows MUST have both new columns and `open` / `ready_to_charge` rows MUST have both NULL.

#### Scenario: Status check
- **WHEN** Alembic migrations for this change complete
- **THEN** inserting a `SaleSession` with `status=paid` MUST fail, inserting `status=confirmed` MUST succeed only when `operational_day_id` and `confirmed_at` are set, and two `open` or mixed `open`/`ready_to_charge` rows MUST NOT exist for the same `(business_id, actor_id, COALESCE(conversation_id, ''))`

#### Scenario: Totalize rollback is consistent
- **WHEN** totalize writes a status change, audit, outbox, and idempotency row and the transaction fails before commit
- **THEN** the session MUST remain `open`, and no `sale.ready_to_charge` outbox or successful totalize audit/idempotency completion MUST remain

#### Scenario: Commit rollback is consistent
- **WHEN** commit writes `confirmed`, a `Payment`, audit, outbox, and idempotency row and the transaction fails before commit
- **THEN** the session MUST remain `ready_to_charge`, no `Payment` MUST remain, no OperationalDay inserted by that transaction MUST remain, and no `sale.confirmed` / `payment.recorded` / `operational_day.opened` outbox or successful commit idempotency completion MUST remain

### Requirement: Payments table persistence
Alembic `0004_sale_session_confirmed_payment` MUST create `sales.payments` with `id`, `business_id`, `sale_session_id` (FK to `sales.sale_sessions.id` only, matching `sale_items`), `actor_id`, `method` CHECK (`cash`, `card`, `transfer`), `amount numeric(12,2)`, `currency`, `status` CHECK (`recorded`), `source` CHECK (`manual_capture`), and timestamps. It MUST add UNIQUE (`sale_session_id`), ENABLE and FORCE ROW LEVEL SECURITY, and create policy `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`. Grants MUST match other `sales` tables for `lumo_app`. It MUST NOT add a composite foreign key on `(business_id, sale_session_id)`. Application `add_payment` remains the tenant-match invariant (see `sale-payment`).

#### Scenario: Payments table exists
- **WHEN** Alembic `0004` completes
- **THEN** `sales.payments` MUST exist with FORCE RLS enabled and uniqueness on `sale_session_id`

### Requirement: Operational days table persistence
Alembic revision id MUST be `0005_operational_day` and `down_revision` MUST be `0004_confirmed_payment`. It MUST create `operations.operational_days` with `id`, `business_id`, `business_date` `DATE`, `status` CHECK (`open`), `timezone` `VARCHAR(64)`, and timestamps. It MUST add `UNIQUE (business_id, business_date)`, `UNIQUE (id, business_id)`, ENABLE and FORCE ROW LEVEL SECURITY, policy `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`, and the same `lumo_app` DML grants as `sales.payments`. It MUST add nullable `sales.sale_sessions.operational_day_id` and `confirmed_at`, backfill existing `confirmed` sessions, verify none remain unattached, and only then add the membership CHECK, the composite foreign key `(operational_day_id, business_id)` to `operational_days (id, business_id)`, and an index on `operational_day_id`. Upgrade order MUST be: create schema `operations`; create `operational_days` with RLS and constraints; add nullable `operational_day_id`; add nullable `confirmed_at`; backfill; verify; add the membership CHECK; add the composite FK and index. Downgrade MUST drop the CHECK, the foreign key, and the new index, then the two columns, then the table and `operations` schema, without deleting payments or sale items and without rewriting session status. It MUST NOT create `cash_counts`, `workflow`, or `memory`. A successful upgrade MUST leave FORCE RLS enabled.

#### Scenario: Migration head
- **WHEN** Alembic upgrade completes on a database whose Alembic revision is `0004_confirmed_payment`
- **THEN** the head revision id MUST be `0005_operational_day` and `operations.operational_days` MUST exist with FORCE RLS and the unique business-date constraint

### Requirement: Legacy confirmed sales are backfilled without runtime events
`0005` MUST succeed on a database that already contains `confirmed` `SaleSession` rows created under revision `0004_confirmed_payment`. For each such row, `legacy_confirmed_at` MUST be that row's `updated_at` at migration time. `business_date` MUST be `legacy_confirmed_at` converted with the same IANA rule as runtime `business_date_for`, using `identity.businesses.timezone` for that `business_id`. The migration MUST NOT hardcode a timezone. An invalid or missing timezone MUST fail the upgrade and leave the database at `0004_confirmed_payment`. The upgrade MUST insert one OperationalDay per distinct `(business_id, business_date)` with `status=open` and that timezone snapshot. For that group, `legacy_opened_at` MUST be the minimum `legacy_confirmed_at`. The inserted row's `created_at` and `updated_at` MUST both equal `legacy_opened_at` and MUST NOT equal the migration execution time. The `INSERT` MUST set those two timestamps explicitly and MUST NOT rely on `DEFAULT now()`. The id MUST be a `new_uuid7()` from the existing helper, which does not accept a historical instant. Do not change that helper so the embedded UUID time matches `legacy_opened_at`. `created_at` is the canonical reconstructed open instant. Then set `confirmed_at` and `operational_day_id` on each legacy confirmed session. The `UPDATE` MUST NOT change `updated_at`, `status`, `SaleItem`s, or `Payment`s. `open` and `ready_to_charge` rows MUST keep both new columns NULL. Sessions that share a business and a computed business date MUST share one OperationalDay. The backfill MUST NOT write `operational_day.opened` audit or outbox, `sale.commit` audit, `sale.confirmed` outbox, or idempotency records, and MUST NOT rewrite existing `sale.confirmed` or `sale.commit@1` rows to add `operational_day_id`.

Alembic runs as `lumo_admin`, which is not a superuser and has no `BYPASSRLS`. FORCE RLS hides other tenants when `app.current_business_id` is unset. The backfill and the post-backfill verification MUST see every tenant. The upgrade MUST disable row level security on `identity.businesses`, `sales.sale_sessions`, and `operations.operational_days` only for that read, insert, update, and verification inside the migration transaction, then ENABLE and FORCE it again before the migration returns. Verification MUST fail the upgrade if any `confirmed` session still has a NULL membership field.

#### Scenario: Upgrade attaches existing confirmed sales
- **WHEN** revision `0004_confirmed_payment` contains two `confirmed` sessions for one business whose pre-upgrade `updated_at` values are `T1` and `T2` with `T1` earlier than `T2` and both on the same local date in that business timezone, plus one `open` session and one `ready_to_charge` session, and each confirmed session has a `Payment` and `SaleItem`s
- **THEN** upgrade to `0005_operational_day` MUST succeed, both confirmed sessions MUST receive the same `operational_day_id`, each `confirmed_at` MUST equal that session's own pre-upgrade `updated_at`, both sessions' `updated_at` values MUST be unchanged, the OperationalDay `created_at` and `updated_at` MUST both equal `T1` and MUST NOT equal the migration execution time, `business_date` MUST be that local date, the `open` and `ready_to_charge` sessions MUST keep both new columns NULL, payments and items MUST be unchanged, and no `operational_day.opened` audit or outbox row MUST exist

#### Scenario: Invalid timezone fails the upgrade
- **WHEN** a `confirmed` session's business timezone is not a valid IANA name and `0005` runs
- **THEN** the upgrade MUST fail and the Alembic revision MUST remain `0004_confirmed_payment`

#### Scenario: Membership check holds after backfill
- **WHEN** `0005_operational_day` has completed on a database that had legacy `confirmed` rows
- **THEN** every `confirmed` session MUST have non-null `operational_day_id` and `confirmed_at`, and the membership CHECK MUST be in force

### Requirement: Cash counts table persistence
Alembic revision id MUST be `0006_cash_count` and `down_revision` MUST be `0005_operational_day`. It MUST create `operations.cash_counts` with `id` UUID PK, `business_id` UUID, `operational_day_id` UUID, `actor_id` UUID, `amount numeric(12,2)`, `currency VARCHAR(3)`, `source VARCHAR(32)`, `counted_at timestamptz`, `supersedes_cash_count_id` UUID NULL, `superseded_by_id` UUID NULL, and timestamps. It MUST add CHECK `amount >= 0`, CHECK `source IN ('manual_capture')`, CHECKs preventing a row from referencing itself through either supersede column, the composite foreign key `(operational_day_id, business_id)` to `operations.operational_days (id, business_id)`, `UNIQUE (id, business_id)`, `UNIQUE (supersedes_cash_count_id)`, `UNIQUE (superseded_by_id)`, partial unique index `uq_cash_counts_current` on `(operational_day_id) WHERE superseded_by_id IS NULL`, and indexes on `business_id` and `operational_day_id`.

Both self-references MUST be composite foreign keys to `operations.cash_counts (id, business_id)` and MUST NOT reference `id` alone: `(supersedes_cash_count_id, business_id)` immediate, and `(superseded_by_id, business_id)` declared `DEFERRABLE INITIALLY DEFERRED`. `UNIQUE (id, business_id)` MUST be created before them. The partial unique index and both unique constraints on the supersede columns MUST remain immediate and MUST NOT be declared deferrable. It MUST ENABLE and FORCE ROW LEVEL SECURITY, create policy `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`, and grant `lumo_app` the same DML as `operations.operational_days`. There MUST be no backfill, because no prior cash data exists. It MUST NOT alter `operations.operational_days`, `sales.sale_sessions`, `sales.sale_items`, or `sales.payments`, MUST NOT add a status value to `ck_operational_days_status`, and MUST NOT create `workflow`, `memory`, `closing_snapshots`, `work_items`, or `export_jobs`. Downgrade MUST drop `operations.cash_counts` with its indexes, policy, and constraints, MUST keep schema `operations` and `operational_days`, and MUST NOT delete sales, items, payments, or day rows. A successful upgrade MUST leave FORCE RLS enabled.

#### Scenario: Migration head
- **WHEN** Alembic upgrade completes on a database whose revision is `0005_operational_day`
- **THEN** the head revision id MUST be `0006_cash_count` and `operations.cash_counts` MUST exist with FORCE ROW LEVEL SECURITY, the `tenant_isolation` policy, and the partial unique current-count index

#### Scenario: Upgrade does not disturb existing data
- **WHEN** `0006_cash_count` runs against a database that already contains confirmed sales, payments, and operational days
- **THEN** those rows MUST be unchanged, `ck_operational_days_status` MUST still allow only `open`, and no cash-count row MUST be created by the migration

#### Scenario: Supersede foreign keys are composite and correctly deferred
- **WHEN** the constraints of `operations.cash_counts` are inspected after `0006_cash_count`
- **THEN** the `supersedes_cash_count_id` and `superseded_by_id` foreign keys MUST each reference `(id, business_id)`, the `superseded_by_id` foreign key MUST be `DEFERRABLE INITIALLY DEFERRED`, the `supersedes_cash_count_id` foreign key MUST NOT be deferrable, and `uq_cash_counts_current` MUST be a partial unique index on `(operational_day_id) WHERE superseded_by_id IS NULL`

#### Scenario: Deferred link is rejected at commit when it points nowhere
- **WHEN** a transaction sets `superseded_by_id` to an id that is never inserted and then commits
- **THEN** the commit MUST fail on the deferred foreign key and no row MUST retain the dangling link

#### Scenario: Downgrade removes only cash counts
- **WHEN** the database is downgraded from `0006_cash_count` to `0005_operational_day`
- **THEN** `operations.cash_counts` MUST NOT exist, schema `operations` and `operational_days` MUST remain, and sale sessions, items, and payments MUST be unchanged

### Requirement: Cash count rollback is consistent
When a cash-count write persists a row, a supersede link, audit, outbox, and an idempotency record and the transaction fails before commit, no new `operations.cash_counts` row MUST remain, the previously current row MUST still have `superseded_by_id` NULL with its original `amount`, and no `closing.submit_cash_count@1` audit, `cash_count.recorded` outbox, or completed `lumo.message.record_cash_count` idempotency row MUST remain. A retry with the same key and payload MUST be allowed to execute exactly once successfully. Recovery MUST rely on transaction rollback only; no compensating update that re-nulls `superseded_by_id` MUST be implemented.

#### Scenario: Forced failure after the cash-count write
- **WHEN** a recount request is forced to fail after writing in local or test mode
- **THEN** the current count MUST remain the previous amount and the failed attempt MUST leave no cash-count, audit, or outbox row

#### Scenario: Failure between retiring and inserting leaves one current row
- **WHEN** a recount transaction updates the previous row's `superseded_by_id` and then fails before commit
- **THEN** rollback alone MUST restore that row to `superseded_by_id` NULL, exactly one current row MUST exist for the day, and the new count id MUST NOT exist in the table

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

### Requirement: Noncatalog sale item migration
Alembic revision id MUST be `0008_noncatalog_sale_item` and `down_revision` MUST be `0007_daily_close_confirmation`. It MUST add `sales.sale_items.source_type` `VARCHAR(32) NOT NULL`, backfill every existing row to `catalog`, and drop `NOT NULL` on `product_id` while keeping the foreign key from `product_id` to `catalog.products(id)`. It MUST add `ck_sale_items_source` so `catalog` rows have `product_id` NOT NULL and `free_concept` rows have `product_id` NULL and a non-blank `product_name_snapshot`. It MUST add `ck_sale_items_money_positive` so `unit_price > 0` and `line_total > 0`. It MUST add `uq_products_id_business` on `catalog.products (id, business_id)` and `fk_sale_items_product_business` from `sales.sale_items (product_id, business_id)` to `catalog.products (id, business_id)`. It MUST NOT delete sale rows. It MUST NOT grant `BYPASSRLS`. Because `lumo_admin` is `NOBYPASSRLS`, the upgrade MUST disable row level security on `catalog.products` and `sales.sale_items` only while it backfills and validates constraints, then `ENABLE` and `FORCE` row level security again before it returns. `tenant_isolation` MUST remain. After `0009_catalog_price_override` is applied, head revision MUST be `0009_catalog_price_override`, not `0008_noncatalog_sale_item`.

#### Scenario: Upgrade preserves catalog lines
- **WHEN** Alembic upgrade runs from `0007_daily_close_confirmation` on a database that already has catalog `SaleItem` rows
- **THEN** those rows MUST have `source_type=catalog`, their `product_id` values MUST be unchanged, and `FORCE` row level security MUST still be enabled on `sales.sale_items`

#### Scenario: Catalog line cannot point at another business
- **WHEN** a `SaleItem` is inserted with `source_type=catalog` and a `product_id` that belongs to a different `business_id`
- **THEN** `fk_sale_items_product_business` MUST reject the row

#### Scenario: Free concept allows a null product
- **WHEN** a `SaleItem` is inserted with `source_type=free_concept`, `product_id` NULL, a non-blank `product_name_snapshot`, and positive money
- **THEN** the insert MUST succeed under that row's `business_id`

#### Scenario: Downgrade refuses free-concept rows
- **WHEN** any `sales.sale_items` row has `source_type=free_concept` or `product_id` NULL and downgrade from `0008_noncatalog_sale_item` is attempted
- **THEN** the downgrade MUST abort, those rows MUST remain, and the revision MUST stay `0008_noncatalog_sale_item`

#### Scenario: Downgrade of a catalog-only database
- **WHEN** every `SaleItem` has `source_type=catalog` and a non-null `product_id`, and the database is downgraded to `0007_daily_close_confirmation`
- **THEN** `source_type` MUST NOT exist, `product_id` MUST be `NOT NULL`, and the catalog sale rows MUST remain

### Requirement: Tenant cannot read another business free-concept line
`sales.sale_items` MUST keep `ENABLE` and `FORCE` row level security and policy `tenant_isolation` on `business_id`. A session whose `app.current_business_id` is business B MUST NOT read business A's free-concept rows.

#### Scenario: Cross-tenant read is empty
- **WHEN** business A has a free-concept `SaleItem` and the session GUC is business B
- **THEN** a select of `sales.sale_items` MUST NOT return that row

### Requirement: Catalog price override migration
Alembic revision id MUST be `0009_catalog_price_override` and `down_revision` MUST be `0008_noncatalog_sale_item`. It MUST add `sales.sale_items.catalog_unit_price_snapshot` `NUMERIC(12, 2) NULL` and `sales.sale_items.price_override_reason` `VARCHAR(200) NULL`. It MUST backfill `source_type=catalog` rows with `catalog_unit_price_snapshot = unit_price` and `price_override_reason` NULL, and `source_type=free_concept` rows with both columns NULL. It MUST add `ck_sale_items_catalog_price` so a catalog row has a positive snapshot and either equal `unit_price` with a null reason, or a different `unit_price` with a non-blank trimmed reason, and a free-concept row has both columns NULL. It MUST keep `ck_sale_items_source`, `ck_sale_items_money_positive`, `fk_sale_items_product_business`, and `tenant_isolation`. Downgrade MUST refuse only catalog overrides, using `source_type = 'catalog' AND (price_override_reason IS NOT NULL OR catalog_unit_price_snapshot IS DISTINCT FROM unit_price)`. It MUST NOT treat a `free_concept` null snapshot as an override. It MUST NOT delete sale rows and MUST NOT grant `BYPASSRLS`. Because `lumo_admin` is `NOBYPASSRLS`, the upgrade MUST disable row level security on `sales.sale_items` only while it backfills and validates the new check, then `ENABLE` and `FORCE` row level security again before it returns. Head revision after a successful upgrade MUST be `0009_catalog_price_override`.

#### Scenario: Existing catalog rows gain an equal snapshot
- **WHEN** upgrade runs on a database whose catalog `SaleItem` rows have `unit_price` `20.00`
- **THEN** those rows MUST have `catalog_unit_price_snapshot` `20.00` and `price_override_reason` NULL, and `FORCE` row level security MUST still be enabled

#### Scenario: Existing free-concept rows stay without a snapshot
- **WHEN** upgrade runs on a database that already has a `free_concept` `SaleItem`
- **THEN** that row MUST have `catalog_unit_price_snapshot` NULL and `price_override_reason` NULL

#### Scenario: Override without a reason is rejected
- **WHEN** a catalog insert sets `unit_price` different from `catalog_unit_price_snapshot` and `price_override_reason` NULL
- **THEN** `ck_sale_items_catalog_price` MUST reject the row

#### Scenario: Catalog-only database downgrades
- **WHEN** every `SaleItem` is `source_type=catalog`, every snapshot equals `unit_price`, every reason is NULL, and downgrade to `0008_noncatalog_sale_item` runs
- **THEN** the downgrade MUST succeed and both new columns MUST NOT exist

#### Scenario: Free-concept rows do not block downgrade
- **WHEN** the database has normal catalog rows and `free_concept` rows, no catalog row has a reason or a snapshot distinct from `unit_price`, and downgrade to `0008_noncatalog_sale_item` runs
- **THEN** the downgrade MUST succeed and those sale rows MUST remain

#### Scenario: A free-concept null snapshot is not an override
- **WHEN** a `free_concept` row has `catalog_unit_price_snapshot` NULL and `unit_price` `18.00`, and no catalog override exists
- **THEN** downgrade MUST NOT treat that row as a catalog override

#### Scenario: Downgrade refuses a catalog override
- **WHEN** at least one `source_type=catalog` row has a non-null `price_override_reason` or a snapshot distinct from `unit_price`, and downgrade from `0009_catalog_price_override` is attempted
- **THEN** the downgrade MUST abort, no sale row MUST be deleted, and the revision MUST stay `0009_catalog_price_override`

#### Scenario: Successful downgrade keeps free-concept rows
- **WHEN** downgrade from `0009_catalog_price_override` to `0008_noncatalog_sale_item` succeeds on a database that contains a `free_concept` row
- **THEN** that row MUST still exist with `source_type=free_concept`, `product_id` NULL, its `product_name_snapshot`, its `unit_price`, and its `line_total`

### Requirement: Tenant cannot read another business override line
`sales.sale_items` MUST keep `ENABLE` and `FORCE` row level security and policy `tenant_isolation` on `business_id`. A session whose `app.current_business_id` is business B MUST NOT read business A's override rows. This migration MUST NOT add a policy and MUST NOT change `tenant_isolation`.

#### Scenario: Cross-tenant override read is empty
- **WHEN** business A has a catalog override `SaleItem` and the session GUC is business B
- **THEN** a select of `sales.sale_items` MUST NOT return that row

