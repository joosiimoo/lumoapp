## MODIFIED Requirements

### Requirement: Platform schemas
Persistence MUST create PostgreSQL schemas `identity`, `audit`, and `platform` for foundation tables, and MUST create product schemas `catalog` and `sales` for `products`, optional `product_aliases`, `sale_sessions`, `sale_items`, and `payments`. This change MUST create product schema `operations` for `operational_days` only. Product schemas `workflow` and `memory` MUST NOT exist. Tables for cash counts and export jobs MUST NOT exist.

#### Scenario: Foundation tables present
- **WHEN** migrations complete
- **THEN** `businesses`, `users`, `memberships`, `audit_events`, `idempotency_records`, and `outbox_events` MUST exist in the foundation schemas

#### Scenario: Catalog and sales schemas present
- **WHEN** catalog and sales migrations complete
- **THEN** PostgreSQL schemas `catalog` and `sales` MUST exist, and tables for catalog products, sale sessions, sale items, and payments MUST exist

#### Scenario: Operations schema is only the day table
- **WHEN** Alembic `0005` completes
- **THEN** PostgreSQL schema `operations` MUST exist with `operational_days`, and schemas `workflow` and `memory` MUST NOT exist

### Requirement: Sale integrity rows match live mutations
Committed conversational sale mutations MUST keep `sales.sale_sessions`, `sales.sale_items`, `sales.payments`, `operations.operational_days` referenced by those sessions, related `audit.audit_events`, `platform.outbox_events`, and `platform.idempotency_records` transactionally consistent. Test/reset helpers that remove those mutations MUST delete the related integrity rows in the same transaction, including `sale.totalize@1` / `sale.commit@1` / `operational_day.opened` audit, `sale.ready_to_charge` / `sale.confirmed` / `payment.recorded` / `operational_day.opened` outbox, and `lumo.message.totalize_sale` / `lumo.message.commit_sale` idempotency. Helpers MUST delete sessions before the operational days they reference.

#### Scenario: No orphan sale outbox
- **WHEN** a `sale.item.added`, `sale.ready_to_charge`, `sale.confirmed`, `payment.recorded`, or `operational_day.opened` outbox row exists for a tenant
- **THEN** the referenced `sale_session_id`, `operational_day_id`, and, when present, `sale_item_id` or `payment_id` MUST exist unless the entire mutation was rolled back (in which case the outbox row MUST NOT exist)

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
- **WHEN** commit writes `confirmed`, a `Payment`, an OperationalDay, audit, outbox, and idempotency row and the transaction fails before commit
- **THEN** the session MUST remain `ready_to_charge`, no `Payment` MUST remain, no OperationalDay inserted by that transaction MUST remain, and no `sale.confirmed` / `payment.recorded` / `operational_day.opened` outbox or successful commit idempotency completion MUST remain

## ADDED Requirements

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
