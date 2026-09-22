## MODIFIED Requirements

### Requirement: Payment is a separate persisted entity
Persistence MUST create `sales.payments` in the existing `sales` schema. `Payment` MUST include `id` (UUIDv7), `business_id`, `sale_session_id`, `actor_id`, `method`, `amount`, `currency`, `status`, `source`, `created_at`, and `updated_at`. Domain `Payment` MUST NOT be a SQLAlchemy model. Money MUST be `numeric`/`Decimal`. `source` MUST be `manual_capture` for this slice. A `Payment` MUST belong to the same tenant as its `SaleSession`. Schema `operations` MAY exist for `OperationalDay`. Schemas `workflow` and `memory` MUST NOT be created by this capability. Payment columns, method checks, and the one-payment unique constraint MUST stay unchanged.

#### Scenario: Payment row exists after cash commit
- **WHEN** `sale.commit@1` commits for a `ready_to_charge` session totaling `56.50` MXN with method `cash`
- **THEN** exactly one `sales.payments` row MUST exist for that `sale_session_id` with `method=cash`, `amount=56.50`, `currency=MXN`, `status=recorded`, and `source=manual_capture`

#### Scenario: No separate Sale table
- **WHEN** Alembic migrations for this change complete
- **THEN** `sales.sales` and `sales.sale_lines` MUST NOT exist, and the confirmed `SaleSession` plus its `SaleItem`s MUST be the durable completed sale
