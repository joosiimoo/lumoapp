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
