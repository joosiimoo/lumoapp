## MODIFIED Requirements

### Requirement: Catalog match wins
A unique active catalog match with no grounded price, or with a grounded price `Decimal`-equal to `Product.current_price`, MUST stay on the catalog path and MUST store `Product.current_price` as both `unit_price` and `catalog_unit_price_snapshot`, with `price_override_reason` NULL. A grounded price that differs MUST ask for an override reason under `catalog-price-override`, MUST NOT persist a `SaleItem` on that first turn, MUST NOT create a `SaleSession`, MUST NOT reserve idempotency, and MUST NOT create a free concept or a `Product`. The first-turn copy MUST be `Tomate está registrado a $20.00 por kg. ¿Por qué lo vendiste a $30.00?` for that Tomate case, and the same sentence with `por unidad` or `por paquete` for those sale units. An ambiguous match MUST keep the current clarification and MUST NOT become a free concept even when a price was uttered. An inactive product or alias with the same normalized name MUST NOT become a free concept. A free-concept price MUST NOT ask for `price_override_reason`.

#### Scenario: Tomate stays catalog
- **WHEN** a Carrota actor posts `900gr tomate`
- **THEN** the line MUST have `source_type=catalog`, Tomate's `product_id`, `unit_price.amount` `20.00`, `catalog_unit_price_snapshot` `20.00`, `price_override_reason` NULL, and `line_total.amount` `18.00`

#### Scenario: Uttered catalog price asks for a reason
- **WHEN** a Carrota actor posts `900gr tomate a 30`
- **THEN** the response MUST be `Tomate está registrado a $20.00 por kg. ¿Por qué lo vendiste a $30.00?` and no `SaleItem`, new `SaleSession`, free concept, or idempotency row MUST be written

#### Scenario: Ambiguity is not a free concept
- **WHEN** two active products share the alias used in `900gr zanahoria a 18`
- **THEN** the response MUST ask which product was sold, and no `SaleItem` MUST be persisted

#### Scenario: Inactive name is not a free concept
- **WHEN** the only name match is an inactive product
- **THEN** the response MUST be `Ese producto está inactivo.` and no `SaleItem` or `Product` MUST be inserted

#### Scenario: Free concept does not ask for an override reason
- **WHEN** a Carrota actor posts `2 bolsas de hielo a 18 cada una` and resolution is `none`
- **THEN** one free-concept line MUST be persisted and `price_override_reason` MUST be NULL
