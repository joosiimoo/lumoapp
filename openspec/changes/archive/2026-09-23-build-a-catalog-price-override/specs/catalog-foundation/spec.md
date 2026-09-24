## MODIFIED Requirements

### Requirement: Current price is catalog truth
`current_price` on the active `Product` MUST remain the catalog price. A catalog price override MUST NOT update it. A free-concept line MUST NOT read `current_price`. The LLM MUST NOT supply a trusted price. A grounded user amount MUST be compared to `current_price` with `Decimal` equality at scale 2, not with strings or floats. When the amounts are equal, the stored `unit_price` and `catalog_unit_price_snapshot` MUST be `Product.current_price` and `price_override_reason` MUST be NULL. When they differ, the first turn MUST clarify under `CAT-001` reason `catalog_price_override_reason_required` and MUST NOT persist a line, create a session, reserve idempotency, apply the uttered price, create a free concept, or update the product. Completing that override is owned by `catalog-price-override`. Price versioning tables, promotions, and discounts remain out of scope.

#### Scenario: Seed price
- **WHEN** the Carrota seed product Zanahoria is loaded
- **THEN** `current_price` MUST be `25.00` MXN stored as `numeric`

#### Scenario: Different uttered price asks for a reason
- **WHEN** add-item resolves uniquely to Tomate and the utterance contains a grounded price of `30`
- **THEN** no `SaleItem` MUST be persisted on that turn, `Product.current_price` MUST remain `20.00`, and the response MUST ask why Tomate was sold at `$30.00`

#### Scenario: Equal uttered price uses the catalog amount
- **WHEN** add-item resolves uniquely to Tomate and the utterance contains a grounded price of `20`
- **THEN** the persisted unit price and `catalog_unit_price_snapshot` MUST be Tomate `current_price` `20.00` MXN and `price_override_reason` MUST be NULL
