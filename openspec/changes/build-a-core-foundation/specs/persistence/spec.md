## ADDED Requirements

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
Persistence MUST create PostgreSQL schemas `identity`, `audit`, and `platform` for foundation tables. Product schemas `catalog`, `sales`, `operations`, `workflow`, and `memory` MUST NOT be created in this change; later OpenSpec changes that own those capabilities MUST introduce them.

#### Scenario: Foundation tables present
- **WHEN** migrations complete
- **THEN** `businesses`, `users`, `memberships`, `audit_events`, `idempotency_records`, and `outbox_events` MUST exist in the foundation schemas

#### Scenario: Product schemas absent
- **WHEN** migrations for this change complete
- **THEN** PostgreSQL schemas `catalog`, `sales`, `operations`, `workflow`, and `memory` MUST NOT exist, and tables for sales, catalog products, operational days, cash counts, and export jobs MUST NOT exist
