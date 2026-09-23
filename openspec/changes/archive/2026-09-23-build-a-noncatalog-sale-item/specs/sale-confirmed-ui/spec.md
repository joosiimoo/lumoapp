## ADDED Requirements

### Requirement: Confirmed rows include free-concept names
`sale_confirmed@1` MUST stay version `1`. `data.items` MUST include every persisted line. A free-concept line MUST use its snapshot as `product_name` and its persisted `line_total`. The payload MUST NOT add a source badge, a save-to-catalog action, or a second card component. Flutter MUST render `product_name` exactly as supplied, including accents and casing, and MUST NOT recompute the total.

#### Scenario: Confirmed card shows the concept
- **WHEN** `sale.commit@1` confirms a sale whose lines include `bolsas de hielo`
- **THEN** `sale_confirmed@1` `data.items` MUST include `product_name` `bolsas de hielo`

#### Scenario: Renderer shows the confirmed concept
- **WHEN** Flutter receives that payload
- **THEN** it MUST show `bolsas de hielo` and the server total, and it MUST NOT show "Concepto libre"

#### Scenario: Renderer keeps an accented confirmed name
- **WHEN** a confirmed item has `product_name` `Café Orgánico`
- **THEN** Flutter MUST show `Café Orgánico` and MUST NOT show `cafe organico`
