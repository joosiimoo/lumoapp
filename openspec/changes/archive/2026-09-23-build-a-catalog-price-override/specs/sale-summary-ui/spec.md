## ADDED Requirements

### Requirement: Summary rows show an adjusted catalog price
`sale_summary@1` MUST remain version `1`. An override item MUST include `catalog_unit_price` as the snapshot money object and MUST keep `unit_price` as the charged price and `line_total` as the persisted total. A normal catalog item and a free-concept item MUST omit `catalog_unit_price`. The payload MUST NOT include the reason. `data.total` MUST remain the Decimal sum of persisted line totals. Flutter MUST show `Precio ajustado · antes $20.00/kg` on a row only when that item has `catalog_unit_price`, and MUST NOT sum the rows.

#### Scenario: Mixed summary keeps the charged Tomate total
- **WHEN** totalize commits a session with Zanahoria `22.50` and a Tomate override line `27.00`
- **THEN** the Tomate item MUST include `catalog_unit_price.amount` `20.00` and `unit_price.amount` `30.00`, the Zanahoria item MUST omit `catalog_unit_price`, and `data.total.amount` MUST be `49.50`

#### Scenario: Renderer captions only the override row
- **WHEN** Flutter renders that summary
- **THEN** it MUST show `Precio ajustado · antes $20.00/kg` on Tomate and MUST NOT show that caption on Zanahoria
