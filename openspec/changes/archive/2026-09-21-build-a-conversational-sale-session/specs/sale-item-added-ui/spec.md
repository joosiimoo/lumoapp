## MODIFIED Requirements

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
