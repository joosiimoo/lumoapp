## ADDED Requirements

### Requirement: Confirmed rows show an adjusted catalog price
`sale_confirmed@1` MUST remain version `1`. `data.items` MUST include every persisted line. An override item MUST include `catalog_unit_price` and the charged `unit_price` and persisted `line_total`. A normal catalog item and a free-concept item MUST omit `catalog_unit_price`. The payload MUST NOT include the reason or a second card component. Flutter MUST show `Precio ajustado · antes $20.00/kg` only on items that have `catalog_unit_price`, and MUST NOT recompute `data.total`.

#### Scenario: Confirmed card keeps the override fact
- **WHEN** `sale.commit@1` confirms a sale whose lines include the Tomate override at `27.00`
- **THEN** that item MUST include `catalog_unit_price.amount` `20.00` and `line_total.amount` `27.00`

#### Scenario: Renderer captions the confirmed override
- **WHEN** Flutter receives that payload
- **THEN** it MUST show `Precio ajustado · antes $20.00/kg` on Tomate and the server total, and it MUST NOT show the reason
