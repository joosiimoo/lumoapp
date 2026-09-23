## MODIFIED Requirements

### Requirement: Unique versus ambiguous resolution
If exactly one active tenant product matches, resolution MUST return that product. If more than one active product matches, resolution MUST return an ambiguous result and MUST NOT choose silently. If none match, resolution MUST return `none`. `catalog.resolve_product@1` MUST NOT insert a `Product`, an alias, or a `SaleItem`. Unknown names MUST NOT become catalog products. A later free-concept `SaleItem` is owned by `noncatalog-sale-item` and MUST NOT be created inside this tool.

#### Scenario: Unique Zanahoria
- **WHEN** `catalog.resolve_product@1` is invoked with query `zanahoria` against the Carrota seed
- **THEN** the result MUST be a unique match for product name `Zanahoria` with `sale_unit=kilogram` and `pricing_type=per_kilogram`

#### Scenario: Ambiguous catalog names
- **WHEN** two active products in the same business both match the normalized query
- **THEN** the result MUST be `ambiguous` and no sale mutation MUST run from that interpretation

#### Scenario: No match invents no product
- **WHEN** `catalog.resolve_product@1` is invoked with query `bolsas de hielo` and no active product or alias matches
- **THEN** `match` MUST be `none` and no `catalog.products` row MUST be inserted

### Requirement: Current price is catalog truth
`current_price` on the active `Product` MUST be the price source for a catalog-backed add-item. A free-concept line MUST NOT read `current_price`. The LLM MUST NOT supply a trusted price for either source. A grounded user amount MUST be compared to `current_price` with `Decimal` equality at scale 2, not with strings or floats. When the amounts are equal, the stored price MUST still be `Product.current_price`. When they differ, add-item MUST clarify under `CAT-001` reason `catalog_price_mismatch` and MUST NOT persist a line, create a session, reserve idempotency, apply the uttered price, or create a free concept. Price versioning tables, overrides, and discounts are out of scope. This guard is not price-override functionality.

#### Scenario: Seed price
- **WHEN** the Carrota seed product Zanahoria is loaded
- **THEN** `current_price` MUST be `25.00` MXN stored as `numeric`

#### Scenario: Uttered price does not override Tomate
- **WHEN** add-item resolves uniquely to Tomate and the utterance contains a grounded price of `30`
- **THEN** no `SaleItem` MUST be persisted and the response MUST state that Tomate is registered at `$20.00` per kg

#### Scenario: Equal uttered price uses the catalog amount
- **WHEN** add-item resolves uniquely to Tomate and the utterance contains a grounded price of `20`
- **THEN** the persisted unit price MUST be Tomate `current_price` `20.00` MXN
