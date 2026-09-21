## Purpose

PostgreSQL is the system of record. Persistence uses SQLAlchemy 2, Alembic, UUIDv7, `timestamptz`, Decimal money, foundation schemas `identity`, `audit`, and `platform`, and product schemas `catalog` and `sales`. Schemas `operations`, `workflow`, and `memory` remain absent.

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
Persistence MUST create PostgreSQL schemas `identity`, `audit`, and `platform` for foundation tables, and MUST create product schemas `catalog` and `sales` for `products`, optional `product_aliases`, `sale_sessions`, and `sale_items`. Product schemas `operations`, `workflow`, and `memory` MUST NOT exist yet; later OpenSpec changes that own those capabilities MUST introduce them.

#### Scenario: Foundation tables present
- **WHEN** migrations complete
- **THEN** `businesses`, `users`, `memberships`, `audit_events`, `idempotency_records`, and `outbox_events` MUST exist in the foundation schemas

#### Scenario: Catalog and sales schemas present
- **WHEN** catalog and sales migrations complete
- **THEN** PostgreSQL schemas `catalog` and `sales` MUST exist, and tables for catalog products, sale sessions, and sale items MUST exist

#### Scenario: Later product schemas absent
- **WHEN** current migrations complete
- **THEN** PostgreSQL schemas `operations`, `workflow`, and `memory` MUST NOT exist, and tables for operational days, cash counts, and export jobs MUST NOT exist

### Requirement: Local PostgreSQL host port
Local Compose MUST publish the Postgres container, which already listens on `5432` internally, to the host as `5432:5432`. README, pytest defaults, and local scripts MUST use `localhost:5432`. They MUST NOT assume host port `5433`.

#### Scenario: Host mapping
- **WHEN** a developer runs `docker compose up` locally
- **THEN** PostgreSQL MUST be reachable on `localhost:5432`

### Requirement: Sale integrity rows match live mutations
Committed conversational sale mutations MUST keep `sales.sale_sessions`, `sales.sale_items`, related `audit.audit_events`, `platform.outbox_events`, and `platform.idempotency_records` transactionally consistent. Test/reset helpers that remove those mutations MUST delete the related integrity rows in the same transaction, including `sale.totalize@1` audit, `sale.ready_to_charge` outbox, and `lumo.message.totalize_sale` idempotency.

#### Scenario: No orphan sale outbox
- **WHEN** a `sale.item.added` or `sale.ready_to_charge` outbox row exists for a tenant
- **THEN** the referenced `sale_session_id` and, when present, `sale_item_id` MUST exist unless the entire mutation was rolled back (in which case the outbox row MUST NOT exist)

### Requirement: SaleSession status persistence
`sales.sale_sessions.status` MUST allow `open` and `ready_to_charge` only. `conversation_id` MUST remain `VARCHAR(128) NULL` as created in `0002_catalog_sales`. Migration `0003` MUST drop `uq_sale_sessions_open_context` and recreate uniqueness with the same expression:

```sql
CREATE UNIQUE INDEX uq_sale_sessions_active_context
ON sales.sale_sessions (business_id, actor_id, COALESCE(conversation_id, ''))
WHERE status IN ('open', 'ready_to_charge');
```

It MUST NOT change the column type, MUST NOT replace `COALESCE(conversation_id, '')` with a UUID coalesce, and MUST NOT add a duplicated mutable total column. Schemas `operations`, `workflow`, and `memory` MUST remain absent.

#### Scenario: Status check
- **WHEN** Alembic migrations for this change complete
- **THEN** inserting a `SaleSession` with `status=confirmed` MUST fail, and two `open` or mixed `open`/`ready_to_charge` rows MUST NOT exist for the same `(business_id, actor_id, COALESCE(conversation_id, ''))`

#### Scenario: Totalize rollback is consistent
- **WHEN** totalize writes a status change, audit, outbox, and idempotency row and the transaction fails before commit
- **THEN** the session MUST remain `open`, and no `sale.ready_to_charge` outbox or successful totalize audit/idempotency completion MUST remain
