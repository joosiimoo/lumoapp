## ADDED Requirements

### Requirement: Adjusted catalog price on sale_item_added@1
`sale_item_added@1` MUST remain version `1`. For a catalog override, `data.unit_price` MUST be the charged unit price, `data.line_total` MUST be the server total, and `data.catalog_unit_price` MUST be the snapshot money object. For a normal catalog line and for a free-concept line, `catalog_unit_price` MUST be absent. The payload MUST NOT include `price_override_reason`. `fallback_text` MUST remain the server success sentence. Flutter MUST render one caption `Precio ajustado · antes $20.00/kg` only when `catalog_unit_price` is present, using the existing unit label and formatting the server amount. It MUST NOT render that caption when the field is absent, and it MUST NOT multiply quantity by either price.

#### Scenario: Override card shows the previous price
- **WHEN** `sale.add_item@1` has committed 0.900 kg of Tomate at charged `30.00` with snapshot `20.00` and line total `27.00`
- **THEN** the `sale_item_added` version `1` payload MUST include `unit_price.amount` `30.00`, `line_total.amount` `27.00`, and `catalog_unit_price.amount` `20.00`

#### Scenario: Renderer shows a quiet caption
- **WHEN** Flutter receives that payload
- **THEN** it MUST show `Tomate`, `0.900 kg · $30.00/kg`, `$27.00`, and `Precio ajustado · antes $20.00/kg`, and it MUST NOT show the reason

#### Scenario: Normal line has no caption
- **WHEN** Flutter receives a Zanahoria `sale_item_added@1` payload without `catalog_unit_price`
- **THEN** it MUST show `0.900 kg · $25.00/kg` and MUST NOT show `Precio ajustado`
