## Purpose

PostgreSQL is the system of record. Persistence uses SQLAlchemy 2, Alembic, UUIDv7, `timestamptz`, Decimal money, foundation schemas `identity`, `audit`, and `platform`, product schemas `catalog` and `sales` (`sale_sessions`, `sale_items`, `payments`), and product schema `operations` (`operational_days`, `cash_counts`). Schemas `workflow` and `memory` remain absent.

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
Committed conversational sale and cash-count mutations MUST keep `sales.sale_sessions`, `sales.sale_items`, `sales.payments`, `operations.operational_days` referenced by those sessions, `operations.cash_counts` referencing those days, related `audit.audit_events`, `platform.outbox_events`, and `platform.idempotency_records` transactionally consistent. Test/reset helpers that remove those mutations MUST delete the related integrity rows in the same transaction, including `sale.totalize@1` / `sale.commit@1` / `operational_day.opened` / `closing.submit_cash_count@1` audit, `sale.ready_to_charge` / `sale.confirmed` / `payment.recorded` / `operational_day.opened` / `cash_count.recorded` outbox, and `lumo.message.totalize_sale` / `lumo.message.commit_sale` / `lumo.message.record_cash_count` idempotency. Helpers MUST delete sessions and cash counts before the operational days they reference.

#### Scenario: No orphan sale outbox
- **WHEN** a `sale.item.added`, `sale.ready_to_charge`, `sale.confirmed`, `payment.recorded`, `operational_day.opened`, or `cash_count.recorded` outbox row exists for a tenant
- **THEN** the referenced `sale_session_id`, `operational_day_id`, `cash_count_id`, and, when present, `sale_item_id` or `payment_id` MUST exist unless the entire mutation was rolled back (in which case the outbox row MUST NOT exist)

#### Scenario: Cleanup removes cash counts before days
- **WHEN** the reset helper clears a tenant's mutations after a recorded cash count
- **THEN** it MUST delete `operations.cash_counts` before `operations.operational_days` in one transaction, no foreign-key error MUST occur, and no `closing.submit_cash_count@1` audit, `cash_count.recorded` outbox, or `lumo.message.record_cash_count` idempotency row MUST remain

#### Scenario: Orphan checks cover cash counts
- **WHEN** the integrity check runs for a tenant
- **THEN** it MUST flag a cash count whose `operational_day_id` is missing, a broken `supersedes_cash_count_id` or `superseded_by_id` link, a supersede link pointing at a row with a different `business_id`, more than one current cash count for a day, and an audit or outbox row referencing a missing `cash_count_id`

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
