## ADDED Requirements

### Requirement: Free-concept line uses sale_item_added@1
`sale_item_added@1` MUST stay version `1`. For a free-concept line, `data.product_name` MUST be the persisted snapshot, `data.line_total` MUST be the server total, and `actions` MUST be empty. The payload MUST NOT include a source badge, a "Concepto libre" label, or a save-to-catalog action. `fallback_text` MUST be the server success sentence. For "2 bolsas de hielo a 18 cada una" that sentence MUST be `Agregué 2 bolsas de hielo · $36.00`. Flutter MUST render `product_name` with the existing product row, MUST show that string exactly as supplied, including accents and casing, and MUST NOT multiply quantity by unit price. Flutter MUST NOT invent a badge when the name is not a seeded catalog product.

#### Scenario: Ice bags card
- **WHEN** `sale.add_item@1` has committed the free-concept bags line totaling `36.00` MXN
- **THEN** the agent response `ui` MUST include one `sale_item_added` version `1` payload whose `data.product_name` is `bolsas de hielo` and whose `data.line_total.amount` is `36.00`

#### Scenario: Renderer shows the concept
- **WHEN** Flutter receives that payload
- **THEN** it MUST show `bolsas de hielo` and the server line total, and it MUST NOT show a save-to-catalog control

#### Scenario: Renderer keeps accents
- **WHEN** Flutter receives `product_name` `Café Orgánico`
- **THEN** it MUST show `Café Orgánico` and MUST NOT show `cafe organico`
