## ADDED Requirements

### Requirement: Summary rows include free-concept names
`sale_summary@1` MUST stay version `1`. Each item `product_name` MUST be that line's `product_name_snapshot`, including a free-concept snapshot. The row MUST use the existing quantity, unit label, unit price, and server line total. Flutter MUST show `product_name` exactly as supplied, including accents and casing. The payload MUST NOT add a source badge or a save-to-catalog action. `data.total` MUST remain the Decimal sum of persisted line totals. Flutter MUST NOT sum the rows.

#### Scenario: Mixed summary names
- **WHEN** totalize commits a session with Zanahoria `22.50` and `bolsas de hielo` `36.00`
- **THEN** `sale_summary@1` `data.items` MUST include both `product_name` values and `data.total.amount` MUST be `58.50`

#### Scenario: Renderer does not label the concept
- **WHEN** Flutter renders that summary
- **THEN** it MUST show `bolsas de hielo` and MUST NOT show "Concepto libre"

#### Scenario: Renderer keeps an accented summary name
- **WHEN** a summary item has `product_name` `Café Molido`
- **THEN** Flutter MUST show `Café Molido` and MUST NOT show `cafe molido`
