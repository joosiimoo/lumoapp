## MODIFIED Requirements

### Requirement: Navigation foundation
The app MUST provide bottom navigation matching the design-system tab bar: Inicio, Hoy, Memoria, and Negocio. Catalog and settings MUST be reachable later from Negocio; they MUST NOT replace the four-tab identity in this change. Onboarding MAY hide the tab bar. Tab roles MUST remain: Inicio is current operational state plus conversation/control plane; Hoy is the structured view of the current operational day; Memoria is factual/persistent business memory; Negocio is the existing business/context surface. Inicio MUST NOT become a KPI dashboard. Hoy MUST NOT become a generic analytics dashboard.

#### Scenario: Four tabs present
- **WHEN** a signed-in placeholder home is shown
- **THEN** the bottom navigation MUST contain Inicio, Hoy, Memoria, and Negocio in that order

#### Scenario: Tab selection styling
- **WHEN** a tab is selected
- **THEN** it MUST use the accent pill and foreground styling from the design system, and unselected tabs MUST use muted styling

#### Scenario: Inicio is not a dashboard
- **WHEN** Inicio is visible with an active operational day
- **THEN** it MUST keep the greeting, current-state region, conversation, and composer, and MUST NOT show an hourly chart or KPI grid

### Requirement: No domain calculations on the client
Flutter MUST NOT calculate monetary totals, daily sales totals, payment-method splits, conversions, expected cash, counted cash, cash differences, cash status, averages, close readiness, or outcome gates. Display formatting of server-provided amounts and dates in the business locale is allowed. Formatting an ISO `business_date` MUST NOT change the calendar day and MUST NOT use the device timezone to choose the day. A `+` prefix on a positive overage amount is display-only and MUST NOT be treated as a computed difference. Flutter MUST NOT choose a payment method, a close request, or a close confirmation except by submitting an action or approved phrase the server already maps, including a silent `request_close` used only to populate the review surface.

#### Scenario: Client formatting only
- **WHEN** the API returns a decimal money string and currency code
- **THEN** the app MAY format it for display and MUST NOT recompute the amount

#### Scenario: Hoy totals stay on the server
- **WHEN** Hoy renders `GET /api/v1/business-stream/today`
- **THEN** the app MUST display `sale_count`, `gross_sales_total`, and tender totals from that payload and MUST NOT add those amounts together

#### Scenario: Review difference stays on the server
- **WHEN** the review surface shows `expected_cash` `22.50`, `counted_cash` `20.00`, `cash_difference` `-2.50`, and `cash_status` `short`
- **THEN** the app MUST display those server values and MUST NOT subtract the amounts or derive the status itself

## ADDED Requirements

### Requirement: Inicio current state is pinned above a scrolling transcript
Inicio MUST compose a compact header region (eyebrow, greeting, current Business Stream panel) that is not an `InicioTurn` and a separate scrolling transcript for merchant messages, Lumo responses, and generated interaction cards. The header MUST show concise current state, relevant totals, and at most one next action. It MUST NOT consume most of the viewport or become a dashboard. The independently scrolling transcript MUST remain the main content region below it. Conversation growth MUST NOT hide the current-state region. Returning to Inicio MUST show current state from a fresh or just-refreshed today GET, not by scrolling to an old card. Conversational sale (`900gr zanahoria` → sale card → totalize → payment) MUST remain on Inicio.

#### Scenario: Sale cards do not bury current state
- **WHEN** the merchant has confirmed two sales on Inicio
- **THEN** the current-state panel MUST remain visible without scrolling the sale cards, and the transcript MUST remain independently scrollable below it

#### Scenario: Header stays compact while transcript scrolls
- **WHEN** the merchant scrolls the Inicio transcript
- **THEN** the compact current-state header MUST remain visible and MUST NOT expand into a dashboard

#### Scenario: Sale flow stays conversational
- **WHEN** the merchant submits `900gr zanahoria` on Inicio
- **THEN** the client MUST keep the existing sale-card path and MUST NOT replace it with a sale form

### Requirement: Daily Close review surface
When `primary_action.kind` is `request_close` and `invocation` is `review_surface`, Flutter MUST acquire a confirmation token by silently posting `POST /api/v1/lumo/messages` with `primary_action.message` (`cerrar el día`) on the existing shell `conversation_id`, then MUST open a dedicated modal bottom sheet populated from server facts (today GET plus that `request_close` response). Flutter MUST NOT render `primary_action.message` as a merchant bubble, visible CTA, or conversational text. Flutter MUST NOT append a duplicate `daily_close_preparation@1` card into the visible transcript and MUST NOT show a second `Confirmar cierre` on Inicio. The surface MUST show sale count, total amount, payment breakdown, expected cash, counted cash, difference, current close status, and the source-coverage limitation when those fields exist. Primary action MUST be `Confirmar cierre` and MUST post existing `closing.confirm@1` with the server-issued confirmation token. Dismiss MUST close the surface without confirming. After successful confirm, the sheet MUST close and Inicio and Hoy MUST reload `GET /api/v1/business-stream/today`; closed UI MUST show `Día cerrado` and MUST omit `Registrar conteo`, `Revisar cierre`, and `Confirmar cierre`. Typed composer `cerrar el día` MAY keep the historical conversational path.

A silent review-surface request MUST NOT later reappear as a visible merchant `cerrar el día` turn after transcript reload. Implementation MUST inspect `/lumo/messages` persistence. If that POST necessarily persists a visible merchant turn, Flutter MUST NOT hide it only in local UI. Implementation MUST stop, report that constraint, and use the smallest existing `POST /api/v1/lumo/actions` `closing.request@1` path that runs `request_close` without creating a merchant turn. It MUST NOT invent a new close workflow or state machine.

#### Scenario: Review opens without a fake bubble
- **WHEN** the merchant taps `Revisar cierre` on Inicio or Hoy
- **THEN** the client MUST silent-post `request_close`, MUST open the review surface, and the Inicio transcript MUST NOT gain a user turn `cerrar el día`

#### Scenario: Operator path does not duplicate the preparation card
- **WHEN** the merchant taps `Revisar cierre`
- **THEN** the visible Inicio transcript MUST NOT gain a new `daily_close_preparation@1` card hosting `Confirmar cierre`

#### Scenario: Transcript reload does not reveal the identifier
- **WHEN** Inicio reloads conversation history after a silent review-surface `request_close`
- **THEN** the transcript MUST NOT show a merchant turn `cerrar el día` created by that tap

#### Scenario: Confirm is the only close CTA on the sheet
- **WHEN** the review surface is open for a counted day
- **THEN** it MUST show exactly one mutating close control labeled `Confirmar cierre` and MUST offer a non-mutating dismiss

#### Scenario: Confirm closes the day
- **WHEN** the merchant taps `Confirmar cierre` with a valid server token
- **THEN** the client MUST post `closing.confirm@1`, MUST close the review surface, and MUST refresh Inicio and Hoy from the today GET so `operator_state` `closed` is shown without stale close CTAs

### Requirement: Operator surfaces refresh after mutations
After a successful sale commit, cash count recording, or close confirmation, Flutter MUST reload `GET /api/v1/business-stream/today` for Inicio current state and for Hoy. Stale local cards MUST NOT be treated as current operational state.

#### Scenario: Cash count refreshes both surfaces
- **WHEN** the merchant records a cash count that matches expected cash
- **THEN** a later view of Inicio current state and of Hoy MUST show `ready_to_close` / `Caja cuadrada` from the new GET
