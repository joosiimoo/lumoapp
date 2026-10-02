## MODIFIED Requirements

### Requirement: Display snapshot is not the resolution query
`product_name_snapshot` for a free concept MUST be built from the raw concept span. Deterministic cleanup MUST be limited to trimming, collapsing repeated internal whitespace, removing the leading quantity, removing the trailing price clause, removing a trailing inline `por {motivo}` that is not a kilogram basis phrase, and removing mass or count tokens that the unit grammar already excludes, including a following `de` where that grammar removes it. That motivo MUST be removed before catalog resolution. `bolsa`, `bolsas`, `paquete`, and `paquetes` MUST remain in the snapshot and MUST still set `unit_normalized` to `package`. The snapshot MUST preserve accents and the merchant's casing. It MUST NOT be lowercased, accent-stripped, title-cased, spell-corrected, translated, or rewritten. Catalog resolution MUST use `normalize_product_name` of that display span as a transient `resolution_query` and MUST NOT persist that query on `SaleItem`. There MUST be no second display column and no normalized-name column. A direct `sale.add_item@1` with `concept_name` MUST store that display value after trim and whitespace collapse and MUST resolve `normalize_product_name(concept_name)` before it may persist `free_concept`. Unique or ambiguous resolution MUST still refuse that write. Cards MUST receive `product_name` equal to the snapshot. Flutter MUST render that string as supplied and MUST NOT lowercase it or strip accents. A free-concept row MUST keep `price_override_reason` NULL even when the utterance contained `por {motivo}`.

#### Scenario: Lowercase bags keep both strings
- **WHEN** the actor posts "2 bolsas de hielo a 18" and resolution of normalized "bolsas de hielo" is `none`
- **THEN** `product_name_snapshot` MUST be `bolsas de hielo` and `unit_normalized` MUST be `package`

#### Scenario: Accented coffee keeps its casing
- **WHEN** the actor posts "1 Café Orgánico 50" and normalized "cafe organico" matches no catalog product
- **THEN** `product_name_snapshot` MUST be `Café Orgánico` and `sale_item_added@1` `data.product_name` MUST be `Café Orgánico`

#### Scenario: Mass coffee drops the unit token only
- **WHEN** the actor posts "500g de Café Molido a 240 por kilo" and normalized "cafe molido" matches nothing
- **THEN** `product_name_snapshot` MUST be `Café Molido`, `quantity_normalized` MUST be `0.500`, and `unit_normalized` MUST be `kilogram`

#### Scenario: Normalized coffee still hits the catalog
- **WHEN** normalized "cafe organico" uniquely matches an active catalog product and the actor posts "1 Café Orgánico 50"
- **THEN** the line MUST be `source_type=catalog` and no free-concept row MUST be written

#### Scenario: Flutter shows the snapshot unchanged
- **WHEN** Flutter receives `product_name` `Café Orgánico`
- **THEN** it MUST show `Café Orgánico` and MUST NOT show `cafe organico`

#### Scenario: Promotion tail is not the free-concept name
- **WHEN** the actor posts `1 hielo suelto a 10 por promoción` and normalized `hielo suelto` matches nothing
- **THEN** `product_name_snapshot` MUST be `hielo suelto`, `price_override_reason` MUST be NULL, and the snapshot MUST NOT be `1 hielo suelto a 10 por promoción` or `hielo suelto a 10 por promoción`

### Requirement: Catalog match wins
A unique active catalog match with no grounded price, or with a grounded price `Decimal`-equal to `Product.current_price`, MUST stay on the catalog path and MUST store `Product.current_price` as both `unit_price` and `catalog_unit_price_snapshot`, with `price_override_reason` NULL. A grounded price that differs and has no valid inline reason MUST ask for an override reason under `catalog-price-override`, MUST NOT persist a `SaleItem` on that first turn, MUST NOT create a `SaleSession`, MUST NOT reserve idempotency, and MUST NOT create a free concept or a `Product`. The first-turn copy MUST be `Tomate está registrado a $20.00 por kg. ¿Por qué lo vendiste a $30.00?` for that Tomate case, and the same sentence with `por unidad` or `por paquete` for those sale units. A grounded price that differs and has a valid inline `por {motivo}` MUST complete the catalog override in that same turn under `catalog-price-override` and MUST NOT create a free concept. An ambiguous match MUST keep the current clarification and MUST NOT become a free concept even when a price or an inline reason was uttered. An inactive product or alias with the same normalized name MUST NOT become a free concept. A free-concept price MUST NOT ask for `price_override_reason`.

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

#### Scenario: Inline promotion stays on the catalog product
- **WHEN** a Carrota actor posts `1 galleta A a 10 por promoción` and Galleta A is an active unit product at `12.00`
- **THEN** the line MUST be `source_type=catalog` for Galleta A and no free-concept row MUST be written
