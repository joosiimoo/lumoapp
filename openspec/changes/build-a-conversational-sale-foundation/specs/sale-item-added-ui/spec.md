## ADDED Requirements

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

`actions` MUST be empty in this change. Money MUST be decimal strings plus `MXN`. `fallback_text` MUST be server-provided and MUST contain the confirmed product and line total.

#### Scenario: Composer emits after commit
- **WHEN** `sale.add_item@1` has committed the golden Zanahoria item
- **THEN** the agent response `ui` MUST include exactly one `sale_item_added` version `1` payload whose `data.line_total.amount` is `22.50`

#### Scenario: Unregistered component still refused
- **WHEN** the composer is asked to emit `sale_confirmed_card@1`
- **THEN** the backend MUST refuse to include it

### Requirement: Flutter maps sale_item_added@1
Flutter `GenerativeUIRenderer` MUST register `sale_item_added` version `1`. It MUST render using existing Lumo visual language: `LumoCard` / product-row pattern from the design system (accent thumbnail, name, `{qty} × {unit} · unit price`, right-aligned subtotal), wrapped with the Lumo mark gutter. It MUST display server-provided `quantity_normalized`, `unit_normalized`, `unit_price`, and `line_total` with locale formatting only. It MUST NOT show payment chips, Registrar, Corregir, or a POS form. Unknown versions MUST show `fallback_text` and MUST NOT run actions.

#### Scenario: Golden card content
- **WHEN** the renderer receives the golden `sale_item_added@1` payload
- **THEN** it MUST show product name Zanahoria, normalized quantity 0.900 kilogram, unit price $25.00, and line total $22.50 without recomputing 0.900 × 25

#### Scenario: Unknown version falls back
- **WHEN** the payload is `sale_item_added` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT execute actions

### Requirement: Inicio conversation stream
Inicio MUST keep sticky composer behavior and the four-tab shell. Sending composer text MUST append a right-aligned primary user bubble, call `POST /api/v1/lumo/messages`, then append the Lumo response: unbubbled assistant text with the Lumo mark and any rendered `sale_item_added@1` card. Clarification MUST appear as unbubbled Lumo text with no sale card. Navigation, canvas, and max-width 420px MUST be unchanged.

#### Scenario: User sends 900gr zanahoria
- **WHEN** the signed-in Carrota user submits `900gr zanahoria` from the Inicio composer
- **THEN** the stream MUST show the user bubble for that text and a Lumo-mark structured `sale_item_added@1` card for Zanahoria 0.900 kg at $22.50

#### Scenario: Clarification has no card
- **WHEN** the backend returns clarification without `sale_item_added@1`
- **THEN** Inicio MUST show Lumo text with the mark and MUST NOT invent a sale card
