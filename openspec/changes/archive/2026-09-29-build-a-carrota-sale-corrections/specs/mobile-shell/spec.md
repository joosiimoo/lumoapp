## ADDED Requirements

### Requirement: Renderer wires remove and Memoria void secondary controls
`GenerativeUIRenderer` MUST map remove actions from `sale_item_added@1` and `sale_summary@1` through the existing `POST /api/v1/lumo/actions` client. Inicio `sale_confirmed@1` MUST NOT expose Anular. Memoria MUST map server-authored timeline `sale.void.request@1` actions to the existing void confirmation UX (reason + server before/after impact → `sale.void.confirm@1`) using the action’s server `conversation_id`. Inicio MUST keep conversation primary and MUST NOT add a POS item grid or a separate corrections screen. Hoy MUST NOT add sale-level void actions or an individual sales list in this slice. After remove or void mutations, operator surfaces that already refresh after sale mutations MUST refresh again so Hoy / Business Stream exclude voided sales; Memoria MUST refresh after void so Anular disappears from the original sale entry.

#### Scenario: Remove does not rotate conversation
- **WHEN** the merchant removes an item from the active sale
- **THEN** Inicio MUST keep the same `conversation_id`

#### Scenario: Inicio confirmed card has no void control
- **WHEN** Inicio renders `sale_confirmed@1` with `status=confirmed`
- **THEN** Flutter MUST NOT show Anular on that card

#### Scenario: Void from Memoria refreshes Hoy facts
- **WHEN** a confirmed sale is voided from Memoria
- **THEN** the next Business Stream / Hoy refresh MUST show server totals that exclude that sale
