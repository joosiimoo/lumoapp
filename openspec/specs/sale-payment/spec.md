## Purpose

Minimum persisted payment for Build A: one recorded `Payment` per confirmed `SaleSession`, method from a closed enum, amount equal to the sale total. This is not Daily Close and not acquirer settlement.

## Requirements

### Requirement: Payment is a separate persisted entity
Persistence MUST create `sales.payments` in the existing `sales` schema. `Payment` MUST include `id` (UUIDv7), `business_id`, `sale_session_id`, `actor_id`, `method`, `amount`, `currency`, `status`, `source`, `created_at`, and `updated_at`. Domain `Payment` MUST NOT be a SQLAlchemy model. Money MUST be `numeric`/`Decimal`. `source` MUST be `manual_capture` for this slice. A `Payment` MUST belong to the same tenant as its `SaleSession`. Schemas `operations`, `workflow`, and `memory` MUST NOT be created.

#### Scenario: Payment row exists after cash commit
- **WHEN** `sale.commit@1` commits for a `ready_to_charge` session totaling `56.50` MXN with method `cash`
- **THEN** exactly one `sales.payments` row MUST exist for that `sale_session_id` with `method=cash`, `amount=56.50`, `currency=MXN`, `status=recorded`, and `source=manual_capture`

#### Scenario: No separate Sale table
- **WHEN** Alembic migrations for this change complete
- **THEN** `sales.sales` and `sales.sale_lines` MUST NOT exist, and the confirmed `SaleSession` plus its `SaleItem`s MUST be the durable completed sale

### Requirement: Closed payment methods
`Payment.method` MUST be exactly one of `cash`, `card`, or `transfer`. Mixed, split, partial, installment, and unknown methods MUST NOT persist. The interpreter MUST NOT infer `cash` when the method is missing (`PAY-001`). A `payment_methods` configuration table MUST NOT be created in this change.

#### Scenario: Card persists as card
- **WHEN** commit runs with `payment_method=card`
- **THEN** the persisted `Payment.method` MUST be `card` and MUST NOT be stored as Spanish display text

#### Scenario: Unknown method does not persist
- **WHEN** the actor posts a payment phrase that is not in the approved closed set
- **THEN** no `Payment` MUST be written and the sale status MUST NOT change

### Requirement: Payment amount equals sale total
The commit path MUST set `Payment.amount` to the Decimal sum of the locked session's persisted `SaleItem.line_total` values using the existing money helper. The client, interpreter, and tool input MUST NOT supply the amount as source of truth. Partial amounts, overpayment, underpayment, change due, tips, fees, discounts, and rounding adjustments MUST NOT be implemented.

#### Scenario: Golden three-item cash amount
- **WHEN** a `ready_to_charge` session has line totals `22.50`, `10.00`, and `24.00` MXN and commit records `cash`
- **THEN** `Payment.amount` MUST be `56.50` MXN and MUST equal the composed `sale_confirmed@1` `data.total.amount` and `data.payment.amount.amount`

### Requirement: One recorded payment per sale
Exactly one `Payment` MUST exist per confirmed `SaleSession` in this change. PostgreSQL MUST enforce uniqueness on `sale_session_id`. `Payment.status` MUST be `recorded` after a successful commit. Pending payment without a method MUST NOT be implemented. Inserting a second payment for the same session MUST fail the transaction.

#### Scenario: Second insert rejected
- **WHEN** a confirmed session already has a `Payment` and another insert targets the same `sale_session_id`
- **THEN** the write MUST fail and the original payment row MUST remain unchanged

### Requirement: Payment tenant isolation
`sales.payments` MUST include `business_id`, enable FORCE RLS with the same `tenant_isolation` policy as other sales tables, and require an explicit `TenantContext` on repository methods. Cross-business reads and writes MUST NOT return or mutate another tenant's payments.

`Payment.business_id` MUST be copied from the trusted `TenantContext` of the locked `SaleSession`. It MUST NOT come from client input, interpreter output, or tool arguments. `CommitSaleSession` MUST load the `SaleSession` with `SELECT ... FOR UPDATE` under that tenant **before** creating a `Payment`. `add_payment` MUST set `business_id` from `tenant.business_id` and MUST reject the write if that value does not equal the locked session's `business_id`. Cross-tenant payment creation MUST fail before commit. FORCE RLS is defense-in-depth and MUST NOT be the only invariant. Follow the existing `sale_items` pattern: FK on `sale_session_id` only; do not add a composite `(business_id, sale_session_id)` foreign key.

#### Scenario: Cross-business payment denied
- **WHEN** an authenticated actor for business B queries payments for a Carrota `sale_session_id`
- **THEN** PostgreSQL MUST return no rows and no Carrota payment MUST be updated

#### Scenario: Tenant mismatch cannot persist
- **WHEN** `add_payment` is invoked under tenant A with `Payment.business_id` of business B, or with a `sale_session_id` whose `SaleSession.business_id` is not A
- **THEN** the write MUST fail before commit and no `sales.payments` row MUST remain

#### Scenario: Commit copies tenant from locked session
- **WHEN** `CommitSaleSession` records cash for a Carrota `ready_to_charge` session
- **THEN** the persisted `Payment.business_id` MUST equal that session's `business_id` and the authenticated `TenantContext.business_id`
