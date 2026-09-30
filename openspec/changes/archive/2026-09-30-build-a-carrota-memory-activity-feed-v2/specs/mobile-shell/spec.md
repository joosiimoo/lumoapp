## MODIFIED Requirements

### Requirement: Navigation foundation
The app MUST provide bottom navigation matching the design-system tab bar: Inicio, Hoy, Memoria, and Negocio. Catalog and settings MUST be reachable later from Negocio; they MUST NOT replace the four-tab identity in this change. Onboarding MAY hide the tab bar. Tab roles MUST remain: Inicio is conversation-first control plane with a light operational header; Hoy is the structured day-operations surface including Daily Close entry; Memoria is factual/persistent business memory presented as a compact chronological activity feed (not oversized event-detail cards and not a dashboard); Negocio is the existing business/context surface. Inicio MUST NOT become a KPI dashboard. Hoy MUST NOT become a generic analytics dashboard. Selected-tab visual treatment MUST preserve the existing accent pill and active label styling; unselected tabs MUST keep muted styling. Navigation structure MUST NOT be redesigned.

#### Scenario: Four tabs present
- **WHEN** a signed-in placeholder home is shown
- **THEN** the bottom navigation MUST contain Inicio, Hoy, Memoria, and Negocio in that order

#### Scenario: Tab selection styling
- **WHEN** a tab is selected
- **THEN** it MUST use the accent pill and foreground styling from the design system, and unselected tabs MUST use muted styling

#### Scenario: Inicio is not a dashboard
- **WHEN** Inicio is visible with an active operational day
- **THEN** it MUST keep the greeting, light operational header, conversation, and composer, and MUST NOT show an hourly chart or KPI grid

#### Scenario: Memoria is an activity feed
- **WHEN** the merchant opens Memoria
- **THEN** the tab MUST present confirmed events as a compact chronological activity feed and MUST NOT present a KPI dashboard

### Requirement: Renderer wires remove and Memoria void secondary controls
`GenerativeUIRenderer` MUST map remove actions from `sale_item_added@1` and `sale_summary@1` through the existing `POST /api/v1/lumo/actions` client. Inicio `sale_confirmed@1` MUST NOT expose Anular. Memoria MUST map server-authored feed `sale.void.request@1` actions to the existing void confirmation UX (reason + server before/after impact → `sale.void.confirm@1`) using the action’s server `conversation_id`. Flutter MUST NOT infer void eligibility when `actions` is absent. Inicio MUST keep conversation primary and MUST NOT add a POS item grid or a separate corrections screen. Hoy MUST NOT add sale-level void actions or an individual sales list in this slice. After remove or void mutations, operator surfaces that already refresh after sale mutations MUST refresh again so Hoy / Business Stream exclude voided sales; Memoria MUST refresh after void so Anular disappears from the original sale feed item.

#### Scenario: Remove does not rotate conversation
- **WHEN** the merchant removes an item from the active sale
- **THEN** Inicio MUST keep the same `conversation_id`

#### Scenario: Inicio confirmed card has no void control
- **WHEN** Inicio renders `sale_confirmed@1` with `status=confirmed`
- **THEN** Flutter MUST NOT show Anular on that card

#### Scenario: Void from Memoria refreshes Hoy facts
- **WHEN** a confirmed sale is voided from Memoria
- **THEN** the next Business Stream / Hoy refresh MUST show server totals that exclude that sale

#### Scenario: Memoria Anular requires server action
- **WHEN** a Memoria `sale_confirmed` feed item has no `sale.void.request@1` in `actions`
- **THEN** Flutter MUST NOT show Anular on that item
