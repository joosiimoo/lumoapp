## ADDED Requirements

### Requirement: Daily sales export adds no persistence
Daily sales export MUST NOT add an Alembic revision. Head MUST remain `0009_catalog_price_override`. It MUST NOT create `export_jobs`, an export-history table, a checksum column, or an object-storage pointer. Generating a file MUST NOT insert or update `audit.audit_events`, `platform.outbox_events`, or `platform.idempotency_records`.

#### Scenario: Schema is unchanged
- **WHEN** the export feature is present and migrations are inspected
- **THEN** the Alembic head MUST be `0009_catalog_price_override` and `export_jobs` MUST NOT exist

#### Scenario: A download writes no integrity row
- **WHEN** a tenant downloads CSV and XLSX for one day
- **THEN** audit, outbox, and idempotency row counts for that business MUST be unchanged by those requests
