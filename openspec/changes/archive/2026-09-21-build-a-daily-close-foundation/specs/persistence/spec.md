## MODIFIED Requirements

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

## ADDED Requirements

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
