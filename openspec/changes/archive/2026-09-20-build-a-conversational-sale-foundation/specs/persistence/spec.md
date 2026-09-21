## MODIFIED Requirements

### Requirement: Platform schemas
Persistence MUST create PostgreSQL schemas `identity`, `audit`, and `platform` for foundation tables, and MUST create product schemas `catalog` and `sales` for `products`, optional `product_aliases`, `sale_sessions`, and `sale_items`. Product schemas `operations`, `workflow`, and `memory` MUST NOT be created in this change; later OpenSpec changes that own those capabilities MUST introduce them.

#### Scenario: Foundation tables present
- **WHEN** migrations complete
- **THEN** `businesses`, `users`, `memberships`, `audit_events`, `idempotency_records`, and `outbox_events` MUST exist in the foundation schemas

#### Scenario: Catalog and sales schemas present
- **WHEN** migrations for this change complete
- **THEN** PostgreSQL schemas `catalog` and `sales` MUST exist, and tables for catalog products, sale sessions, and sale items MUST exist

#### Scenario: Later product schemas absent
- **WHEN** migrations for this change complete
- **THEN** PostgreSQL schemas `operations`, `workflow`, and `memory` MUST NOT exist, and tables for operational days, cash counts, and export jobs MUST NOT exist

### Requirement: Local PostgreSQL host port
Local Compose MUST publish the Postgres container, which already listens on `5432` internally, to the host as `5432:5432`. README, pytest defaults, and local scripts MUST use `localhost:5432`. They MUST NOT assume host port `5433`.

#### Scenario: Host mapping
- **WHEN** a developer runs `docker compose up` locally
- **THEN** PostgreSQL MUST be reachable on `localhost:5432`

### Requirement: Sale integrity rows match live mutations
Committed conversational sale mutations MUST keep `sales.sale_sessions`, `sales.sale_items`, related `audit.audit_events`, `platform.outbox_events`, and `platform.idempotency_records` transactionally consistent. Test/reset helpers that remove those mutations MUST delete the related integrity rows in the same transaction.

#### Scenario: No orphan sale outbox
- **WHEN** a `sale.item.added` outbox row exists for a tenant
- **THEN** the referenced `sale_session_id` and `sale_item_id` MUST exist unless the entire mutation was rolled back (in which case the outbox row MUST NOT exist)
