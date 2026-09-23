## Purpose

Versioned `sale_item_added@1` contract, backend composition after committed add-item, and Flutter rendering on Inicio.
## Requirements
### Requirement: Register sale_item_added@1
`GenerativeUIRegistry` MUST register component `sale_item_added` version `1`. `GenerativeUIComposer` MUST emit this contract only after a committed `sale.add_item@1` and MUST refuse unknown components. The backend MUST NOT render Flutter widgets or HTML.

The contract MUST be:

```json
{
  "component": "sale_item_added",
  "version": 1,
  "data": {
    "sale_session_id": "<uuid>",
    "sale_item_id": "<uuid>",
    "product_name": "Zanahoria",
    "quantity_input": "900",
    "unit_input": "gram",
    "quantity_normalized": "0.900",
    "unit_normalized": "kilogram",
    "unit_price": {"amount": "25.00", "currency": "MXN"},
    "line_total": {"amount": "22.50", "currency": "MXN"},
    "session_item_count": 1,
    "session_total": {"amount": "22.50", "currency": "MXN"}
  },
  "actions": [],
  "fallback_text": "Agregué 0.900 kg de Zanahoria · $22.50"
}
```

`actions` MUST be empty for this contract. Money MUST be decimal strings plus `MXN`. `fallback_text` MUST be server-provided and MUST contain the confirmed product and line total.

#### Scenario: Composer emits after commit
- **WHEN** `sale.add_item@1` has committed the golden Zanahoria item
- **THEN** the agent response `ui` MUST include exactly one `sale_item_added` version `1` payload whose `data.line_total.amount` is `22.50`

#### Scenario: Unregistered component still refused
- **WHEN** the composer is asked to emit `sale_confirmed_card@1`
- **THEN** the backend MUST refuse to include it

### Requirement: Flutter maps sale_item_added@1
Flutter `GenerativeUIRenderer` MUST register `sale_item_added` version `1`. It MUST render using existing Lumo visual language: `LumoCard` / product-row pattern from the design system (accent thumbnail, name, user-facing quantity and unit price, right-aligned subtotal), wrapped with the Lumo mark gutter. Canonical payload fields `quantity_normalized`, `unit_normalized`, and `unit_price` MUST remain server values. Display labels MUST be `kilogram`→`kg`, `gram`→`g`, `unit`→`unidad`, `package`→`paquete`. The visible golden detail line MUST be `0.900 kg · $25.00/kg`. The card MUST also display server-provided `session_item_count` and `session_total` so the accumulated sale is visible after each add. Flutter MUST format those server strings only and MUST NOT recompute line or session totals. It MUST NOT show payment chips, Registrar, Corregir, or a POS form. Unknown versions MUST show `fallback_text` and MUST NOT run actions. The JSON contract version MUST remain `1`; existing fields MUST keep their meaning.

#### Scenario: Golden card content
- **WHEN** the renderer receives the golden `sale_item_added@1` payload
- **THEN** it MUST show product name Zanahoria, `0.900 kg · $25.00/kg`, and line total $22.50 without recomputing 0.900 × 25

#### Scenario: Accumulated session values
- **WHEN** the payload has `session_item_count` `2` and `session_total.amount` `32.50`
- **THEN** the card MUST show those server values and MUST NOT add line totals on the client

#### Scenario: Unknown version falls back
- **WHEN** the payload is `sale_item_added` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT execute actions

### Requirement: Inicio conversation stream
Inicio MUST keep sticky composer behavior and the four-tab shell. Sending composer text MUST append a right-aligned primary user bubble, call `POST /api/v1/lumo/messages`, then append the Lumo response: unbubbled assistant text with the Lumo mark and any rendered `sale_item_added@1` or `sale_summary@1` card. Clarification MUST appear as unbubbled Lumo text with no sale card. Navigation, canvas, and max-width 420px MUST be unchanged.

#### Scenario: User sends 900gr zanahoria
- **WHEN** the signed-in Carrota user submits `900gr zanahoria` from the Inicio composer
- **THEN** the stream MUST show the user bubble for that text and a Lumo-mark structured `sale_item_added@1` card for Zanahoria `0.900 kg · $25.00/kg` at $22.50

#### Scenario: Clarification has no card
- **WHEN** the backend returns clarification without `sale_item_added@1` or `sale_summary@1`
- **THEN** Inicio MUST show Lumo text with the mark and MUST NOT invent a sale card

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

