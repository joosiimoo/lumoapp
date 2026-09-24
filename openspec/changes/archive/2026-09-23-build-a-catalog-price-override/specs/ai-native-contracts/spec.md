## MODIFIED Requirements

### Requirement: PolicyEngine contract
`PolicyEngine` MUST evaluate a proposed action and return `allow`, `deny`, `clarify`, or `confirm` with rule ids, a reason code, and evidence requirements. Evaluation order MUST be security, integrity, tenant and permissions, workflow gates, business rules, catalog and pricing, confidence, then user experience. Registered policies MUST include `SEC-001`, `SEC-002`, `SEC-003`, `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, `SALE-001`, `SALE-002`, `SALE-003`, `SALE-004`, `SALE-005`, `PAY-001`, `DAY-001`, `CLOSE-001`, `CLOSE-002`, and `CLOSE-003`. `SALE-005` MUST allow `sale.add_item@1` with `source_type=free_concept` only when resolution is `none`, the concept is non-empty, quantity is positive, the unit is supported, and `unit_price` is an explicit positive business-currency amount with at most two decimal places grounded in user text. For `gram` and `kilogram`, `SALE-005` MUST also require an explicit per-kilogram basis and MUST clarify with reason `price_basis_required` when that basis is missing. `SALE-005` MUST clarify when that price or quantity is missing and MUST deny a non-positive price. `SALE-005` MUST NOT allow a free concept when resolution is `unique`, `ambiguous`, or an inactive name collision. A unique catalog match whose grounded user amount differs from `Product.current_price` MUST clarify under `CAT-001` with reason `catalog_price_override_reason_required` and MUST NOT be allowed or refused through `SALE-005`. A completed catalog override MUST be allowed under `SALE-001` and `CAT-001` with reason `catalog_price_override` only after the server re-reads `Product.current_price` and accepts a merchant reason. No new policy id is added. `DAY-001` MUST allow `operational_day.summary@1` only as a registered read and MUST NOT treat model-supplied totals or dates as operational truth. `CLOSE-001` MUST allow `closing.submit_cash_count@1` only for a server-parsed non-negative amount when an `OperationalDay` exists for today's business date, MUST clarify with reason `operational_day_not_started` when no such day exists, and MUST NOT treat model-supplied expected cash, counted cash, difference, status, `operational_day_id`, or business date as operational truth. `CLOSE-002` MUST allow `closing.prepare@1` only as a registered read with the same prohibition on model-supplied values. `CLOSE-003` MUST deny `closing.confirm@1` when arguments include `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, `operational_day_id`, `closing_snapshot_id`, `business_date`, `closed_at`, `sale_count`, `gross_sales_total`, `cash_total`, `card_total`, `transfer_total`, `currency`, `actor_id`, or `cash_count_id`. The confirm workflow under the day lock remains the authority for whether the token matches current state.

#### Scenario: Deny unregistered tool
- **WHEN** policy evaluates a request to execute an unregistered tool
- **THEN** the decision MUST be `deny` under `SEC-002`

#### Scenario: Decision is auditable
- **WHEN** the engine returns a decision
- **THEN** the result MUST include rule ids and a reason code suitable for `AuditEvent`

#### Scenario: Catalog product must be active
- **WHEN** policy evaluates add-item for an inactive product
- **THEN** the decision MUST NOT be `allow` under `CAT-001`

#### Scenario: Unresolved concept without a price is not allowed
- **WHEN** policy evaluates add-item and resolution is `none` and unit price is missing
- **THEN** the decision MUST NOT be `allow`

#### Scenario: Complete free concept is allowed
- **WHEN** policy evaluates add-item with resolution `none`, `source_type=free_concept`, quantity `2`, unit `package`, and unit price `18.00` MXN
- **THEN** the decision MUST be `allow` under `SALE-005`

#### Scenario: Mass free concept without a basis is not allowed
- **WHEN** policy evaluates add-item with resolution `none`, unit `gram`, unit price `40.00` MXN, and no per-kilogram basis
- **THEN** the decision MUST be `clarify` with reason `price_basis_required` and MUST NOT be `allow` under `SALE-005`

#### Scenario: Catalog price difference asks for a reason
- **WHEN** policy evaluates add-item with resolution `unique` and a grounded price that differs from `Product.current_price` before a merchant reason exists
- **THEN** the decision MUST be `clarify` under `CAT-001` with reason `catalog_price_override_reason_required` and MUST NOT be a `SALE-005` decision

#### Scenario: Completed override is allowed on the add-item tool
- **WHEN** policy evaluates a catalog `sale.add_item@1` whose re-read price differs from the grounded override and whose merchant reason is valid
- **THEN** the decision MUST be `allow` with reason `catalog_price_override` and rule ids including `SALE-001` and `CAT-001`

#### Scenario: Ambiguous match is not a free concept
- **WHEN** policy evaluates add-item and resolution is `ambiguous`
- **THEN** the decision MUST NOT be `allow` under `SALE-005`

#### Scenario: Ready_to_charge blocks add-item
- **WHEN** policy evaluates add-item for a session whose status is `ready_to_charge`
- **THEN** the decision MUST NOT be `allow` under `SALE-002`

#### Scenario: SALE-003 gates the transition only
- **WHEN** policy evaluates totalize for an `open` session with no items
- **THEN** the decision MUST NOT be `allow` under `SALE-003`

#### Scenario: SALE-003 allows ready_to_charge read-back
- **WHEN** policy evaluates totalize for a session whose status is already `ready_to_charge`
- **THEN** the decision MUST NOT treat that request as a forbidden transition under `SALE-003`

#### Scenario: SALE-004 gates commit to ready_to_charge
- **WHEN** policy evaluates commit for an `open` session
- **THEN** the decision MUST NOT be `allow` under `SALE-004`

#### Scenario: PAY-001 requires an explicit method
- **WHEN** policy evaluates commit without a closed-enum `payment_method`
- **THEN** the decision MUST NOT be `allow` under `PAY-001` and MUST NOT infer `cash`

#### Scenario: DAY-001 does not accept client totals
- **WHEN** policy evaluates `operational_day.summary@1` and the model arguments include a sale count or a total
- **THEN** the decision MUST NOT persist those arguments and the summary MUST still be computed from confirmed rows under `DAY-001`

#### Scenario: CLOSE-001 clarifies when the day has not started
- **WHEN** policy evaluates `closing.submit_cash_count@1` and no `OperationalDay` exists for today's business date
- **THEN** the decision MUST NOT be `allow`, the reason code MUST be `operational_day_not_started`, and no cash count or operational day MUST be persisted

#### Scenario: CLOSE-001 rejects model-supplied cash figures
- **WHEN** policy evaluates `closing.submit_cash_count@1` with model arguments carrying `expected_cash`, `cash_difference`, or `operational_day_id`
- **THEN** those arguments MUST NOT be persisted and the backend MUST still compute expected cash and the difference from persisted rows under `CLOSE-001`

#### Scenario: CLOSE-002 keeps preparation a read
- **WHEN** policy evaluates `closing.prepare@1`
- **THEN** the decision MUST allow it only as a registered read and MUST NOT authorize any write, status change, or close confirmation

#### Scenario: CLOSE-003 rejects model-supplied close figures
- **WHEN** policy evaluates `closing.confirm@1` with model arguments carrying `counted_cash`, `closing_snapshot_id`, or `closed_at`
- **THEN** the decision MUST be `deny` under `CLOSE-003` and no snapshot MUST be written

### Requirement: sale.add_item source mode
`sale.add_item@1` MUST remain the only add-item tool and MUST remain version `1`. Its input schema MUST require `source_type`. `catalog` MUST require `product_id`. Without `price_override`, catalog mode MUST NOT accept a client unit price as the stored price. With `price_override`, the object MUST contain `unit_price` `{amount, currency}` and `reason`. The server MUST re-read `Product.current_price` and MUST persist that client amount only when `catalog-price-override` accepts it. `free_concept` MUST require `concept_name` and `unit_price` and MUST NOT require `product_id`. `sale.override_price@1`, `sale.add_override_item@1`, and `sale.add_free_item@1` MUST remain unregistered. `sale_item_added@1`, `sale_summary@1`, and `sale_confirmed@1` MUST remain version `1`. Generative UI actions MUST NOT gain a save-to-catalog action.

#### Scenario: Free-item tool stays unregistered
- **WHEN** a caller asks the registry for `sale.add_free_item@1`
- **THEN** the registry MUST report the tool as unregistered

#### Scenario: Override tools stay unregistered
- **WHEN** a caller asks the registry for `sale.override_price@1` or `sale.add_override_item@1`
- **THEN** the registry MUST report each tool as unregistered

#### Scenario: No catalog-save action
- **WHEN** `sale_item_added@1` is emitted for a free-concept line or a catalog override
- **THEN** `actions` MUST be empty

## ADDED Requirements

### Requirement: Override caption stays on version 1
`GenerativeUIRegistry` MUST NOT register version `2` of `sale_item_added`, `sale_summary`, or `sale_confirmed` for this change. An override payload MAY include `catalog_unit_price` on version `1`. Existing required fields MUST keep their meaning. The composer MUST still refuse an unregistered component or version.

#### Scenario: Version 2 is not registered
- **WHEN** the registry is queried for `sale_item_added` version `2`
- **THEN** the component version MUST be absent
