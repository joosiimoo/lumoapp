## MODIFIED Requirements

### Requirement: Platform schemas
Persistence MUST create PostgreSQL schemas `identity`, `audit`, and `platform` for foundation tables, and MUST create product schemas `catalog` and `sales` for `products`, optional `product_aliases`, `sale_sessions`, `sale_items`, and `payments`. Product schemas `operations`, `workflow`, and `memory` MUST NOT exist yet; later OpenSpec changes that own those capabilities MUST introduce them.

#### Scenario: Foundation tables present
- **WHEN** migrations complete
- **THEN** `businesses`, `users`, `memberships`, `audit_events`, `idempotency_records`, and `outbox_events` MUST exist in the foundation schemas

#### Scenario: Catalog and sales schemas present
- **WHEN** catalog and sales migrations complete
- **THEN** PostgreSQL schemas `catalog` and `sales` MUST exist, and tables for catalog products, sale sessions, sale items, and payments MUST exist

#### Scenario: Later product schemas absent
- **WHEN** current migrations complete
- **THEN** PostgreSQL schemas `operations`, `workflow`, and `memory` MUST NOT exist, and tables for operational days, cash counts, and export jobs MUST NOT exist

### Requirement: Sale integrity rows match live mutations
Committed conversational sale mutations MUST keep `sales.sale_sessions`, `sales.sale_items`, `sales.payments`, related `audit.audit_events`, `platform.outbox_events`, and `platform.idempotency_records` transactionally consistent. Test/reset helpers that remove those mutations MUST delete the related integrity rows in the same transaction, including `sale.totalize@1` / `sale.commit@1` audit, `sale.ready_to_charge` / `sale.confirmed` / `payment.recorded` outbox, and `lumo.message.totalize_sale` / `lumo.message.commit_sale` idempotency.

#### Scenario: No orphan sale outbox
- **WHEN** a `sale.item.added`, `sale.ready_to_charge`, `sale.confirmed`, or `payment.recorded` outbox row exists for a tenant
- **THEN** the referenced `sale_session_id` and, when present, `sale_item_id` or `payment_id` MUST exist unless the entire mutation was rolled back (in which case the outbox row MUST NOT exist)

### Requirement: SaleSession status persistence
`sales.sale_sessions.status` MUST allow `open`, `ready_to_charge`, and `confirmed`. `conversation_id` MUST remain `VARCHAR(128) NULL` as created in `0002_catalog_sales`. Migration `0004` MUST replace `ck_sale_sessions_status` so status IN (`open`, `ready_to_charge`, `confirmed`) and MUST keep unique index `uq_sale_sessions_active_context` unchanged:

```sql
CREATE UNIQUE INDEX uq_sale_sessions_active_context
ON sales.sale_sessions (business_id, actor_id, COALESCE(conversation_id, ''))
WHERE status IN ('open', 'ready_to_charge');
```

It MUST NOT change the column type, MUST NOT replace `COALESCE(conversation_id, '')` with a UUID coalesce, MUST NOT add `confirmed` to the unique-index predicate, and MUST NOT add a duplicated mutable total column. Schemas `operations`, `workflow`, and `memory` MUST remain absent.

#### Scenario: Status check
- **WHEN** Alembic migrations for this change complete
- **THEN** inserting a `SaleSession` with `status=paid` MUST fail, inserting `status=confirmed` MUST succeed, and two `open` or mixed `open`/`ready_to_charge` rows MUST NOT exist for the same `(business_id, actor_id, COALESCE(conversation_id, ''))`

#### Scenario: Totalize rollback is consistent
- **WHEN** totalize writes a status change, audit, outbox, and idempotency row and the transaction fails before commit
- **THEN** the session MUST remain `open`, and no `sale.ready_to_charge` outbox or successful totalize audit/idempotency completion MUST remain

#### Scenario: Commit rollback is consistent
- **WHEN** commit writes `confirmed`, a `Payment`, audit, outbox, and idempotency row and the transaction fails before commit
- **THEN** the session MUST remain `ready_to_charge`, no `Payment` MUST remain, and no `sale.confirmed` / `payment.recorded` outbox or successful commit idempotency completion MUST remain

## ADDED Requirements

### Requirement: Payments table persistence
Alembic `0004_sale_session_confirmed_payment` MUST create `sales.payments` with `id`, `business_id`, `sale_session_id` (FK to `sales.sale_sessions.id` only, matching `sale_items`), `actor_id`, `method` CHECK (`cash`, `card`, `transfer`), `amount numeric(12,2)`, `currency`, `status` CHECK (`recorded`), `source` CHECK (`manual_capture`), and timestamps. It MUST add UNIQUE (`sale_session_id`), ENABLE and FORCE ROW LEVEL SECURITY, and create policy `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`. Grants MUST match other `sales` tables for `lumo_app`. It MUST NOT add a composite foreign key on `(business_id, sale_session_id)`. Application `add_payment` remains the tenant-match invariant (see `sale-payment`).

#### Scenario: Payments table exists
- **WHEN** Alembic `0004` completes
- **THEN** `sales.payments` MUST exist with FORCE RLS enabled and uniqueness on `sale_session_id`
