## MODIFIED Requirements

### Requirement: Navigation foundation
The app MUST provide bottom navigation matching the design-system tab bar: Inicio, Hoy, Memoria, and Negocio. Catalog and settings MUST be reachable later from Negocio; they MUST NOT replace the four-tab identity in this change. Onboarding MAY hide the tab bar. Tab roles MUST remain: Inicio is conversation-first control plane with a light operational header; Hoy is the structured day-operations surface including Daily Close entry; Memoria is factual/persistent business memory; Negocio is the existing business/context surface. Inicio MUST NOT become a KPI dashboard. Hoy MUST NOT become a generic analytics dashboard. Selected-tab visual treatment MUST preserve the existing accent pill and active label styling; unselected tabs MUST keep muted styling. Navigation structure MUST NOT be redesigned.

#### Scenario: Four tabs present
- **WHEN** a signed-in placeholder home is shown
- **THEN** the bottom navigation MUST contain Inicio, Hoy, Memoria, and Negocio in that order

#### Scenario: Tab selection styling
- **WHEN** a tab is selected
- **THEN** it MUST use the accent pill and foreground styling from the design system, and unselected tabs MUST use muted styling

#### Scenario: Inicio is not a dashboard
- **WHEN** Inicio is visible with an active operational day
- **THEN** it MUST keep the greeting, light operational header, conversation, and composer, and MUST NOT show an hourly chart or KPI grid

### Requirement: Inicio hosts the business stream above the conversation
Inicio MUST show a light operational header from `GET /api/v1/business-stream/today` when the tab becomes visible, below the existing `Buenos días` greeting and outside the scrolling transcript. The header MUST be the short operational sentence plus at most two indicator cards as specified by `business-stream`. It MUST keep `LumoComposer`, the four-tab shell, and the conversation-card renderer for typed turns. The header MUST NOT replace Hoy, Memoria, or Negocio. Inicio MUST NOT render operator Daily Close CTAs. Typed composer `cerrar el día` MAY keep the historical conversational path. After a successful message or action from that conversation, and after a successful close confirm from the Hoy close workspace, Inicio MUST reload the header. Transport failure MUST show `No pude consultar el estado de hoy.` and MUST NOT present the last successful totals as current. Hoy MUST use the same today GET as its structured daily summary and MUST NOT use the next-best-action GET as its primary body.

#### Scenario: Greeting and composer stay
- **WHEN** Inicio renders with the light operational header
- **THEN** `Buenos días` MUST remain visible and the existing composer MUST remain usable

#### Scenario: Inicio does not open operator close workspace
- **WHEN** the today GET has `primary_action.kind` `prepare_daily_close`
- **THEN** Inicio MUST NOT show `Preparar el cierre del día` and MUST NOT open the close workspace from Inicio chrome

#### Scenario: Other tabs stay distinct
- **WHEN** the merchant opens Hoy or Memoria after this header exists
- **THEN** Hoy MUST show the structured daily summary from the today GET and Memoria MUST still load its event timeline

### Requirement: Inicio current state is pinned above a scrolling transcript
Inicio MUST compose a compact header region (eyebrow, greeting, light operational header) that is not an `InicioTurn` and a separate scrolling transcript for merchant messages, Lumo responses, and generated interaction cards. The header MUST show the short sentence and informative indicators only. It MUST NOT consume most of the viewport or become a dashboard. The independently scrolling transcript MUST remain the main content region below it. Conversation growth MUST NOT hide the current-state region. Returning to Inicio MUST show current state from a fresh or just-refreshed today GET, not by scrolling to an old card. Conversational sale (`900gr zanahoria` → sale card → totalize → payment) MUST remain on Inicio.

#### Scenario: Sale cards do not bury current state
- **WHEN** the merchant has confirmed two sales on Inicio
- **THEN** the light operational header MUST remain visible without scrolling the sale cards, and the transcript MUST remain independently scrollable below it

#### Scenario: Header stays compact while transcript scrolls
- **WHEN** the merchant scrolls the Inicio transcript
- **THEN** the compact light header MUST remain visible and MUST NOT expand into a dashboard

#### Scenario: Sale flow stays conversational
- **WHEN** the merchant submits `900gr zanahoria` on Inicio
- **THEN** the client MUST keep the existing sale-card path and MUST NOT replace it with a sale form

### Requirement: Closed day keeps transcript read-only for sale mutations
When today GET `operator_state` is `closed`, Inicio MUST keep historical transcript turns visible, including prior `sale_item_added`, `sale_summary`, and `sale_confirmed` cards. It MUST NOT render actionable sale-mutation controls from those cards: no `Quitar`, no payment method buttons, no `Lista para cobrar` active-sale chrome, and no Inicio `Anular` control. Flutter MUST derive this gate from the authoritative today GET `operator_state` and MUST NOT infer closure from local clocks or card timestamps. The composer MUST remain available for conversation. Backend refusal of writes against a closed day MUST remain defense-in-depth. Sale corrections on an open day MUST be unchanged.

#### Scenario: Closed day hides sale mutation controls
- **WHEN** today GET `operator_state` is `closed` and the Inicio transcript still contains a `sale_summary@1` card with payment actions
- **THEN** Inicio MUST show the historical card content and MUST NOT show `Quitar`, `Lista para cobrar`, `¿Cómo pagó?`, or Efectivo/Tarjeta/Transferencia controls

#### Scenario: Open day sale actions unchanged
- **WHEN** today GET `operator_state` is not `closed` and a `sale_summary@1` card has payment actions
- **THEN** Inicio MUST still show `Lista para cobrar` and the server payment actions

### Requirement: Daily Close review surface
Operator Daily Close MUST be initiated only from Hoy when `primary_action.kind` is `prepare_daily_close` and `invocation` is `close_workspace`. Flutter MUST open a dedicated close workspace bottom sheet/modal titled `Cierre del día`, populated from server facts (today GET and subsequent count/prepare responses). The workspace MUST let the merchant enter counted cash numerically without navigating to Inicio and without requiring conversational phrase entry. After a successful structured cash count, the workspace MUST refresh server-authored expected/counted/difference/cash_status and MUST NOT compute those values on device. The workspace MUST offer optional `Agregar nota` before final close. Primary close action MUST be labeled `Cerrar el día`, MUST mint a confirmation token via silent `request_close` (messages technical identifier or existing `closing.request@1` fallback if messages would persist a visible merchant turn), and MUST post `closing.confirm@1` with that token and optional `close_note`. Flutter MUST NOT append a merchant bubble `cerrar el día` or a transcript `daily_close_preparation@1` card for the operator workspace path. Dismiss MUST leave the day open. After successful confirm, the workspace MUST show a short completion state and `Listo` MUST return to Hoy closed state without close CTAs. Typed composer `cerrar el día` MAY keep the historical conversational path.

#### Scenario: Prepare-close opens workspace without Inicio navigation
- **WHEN** the merchant taps `Preparar el cierre del día` on Hoy
- **THEN** the client MUST open the close workspace sheet/modal and MUST NOT switch to Inicio to collect the cash count

#### Scenario: Count stays in the workspace
- **WHEN** the merchant submits a counted amount in the workspace
- **THEN** the client MUST call the structured cash-count action path, MUST refresh server facts in the workspace, and MUST NOT append a user turn for a constructed count phrase

#### Scenario: Cancel leaves the day open
- **WHEN** the merchant dismisses the workspace before confirm
- **THEN** the OperationalDay MUST remain `open` and no `closing.confirm@1` MUST be posted

#### Scenario: Confirm closes the day
- **WHEN** the merchant taps `Cerrar el día` with a valid server token
- **THEN** the client MUST post `closing.confirm@1`, MUST show completion, and after `Listo` Hoy MUST show `operator_state` `closed` without stale close CTAs

#### Scenario: Active tab styling preserved
- **WHEN** the merchant switches from Inicio to Hoy
- **THEN** Hoy MUST show the accent pill and active label styling and Inicio MUST use muted unselected styling

### Requirement: Operator surfaces refresh after mutations
After a successful sale commit, cash count recording, or close confirmation, Flutter MUST reload `GET /api/v1/business-stream/today` for Inicio current state and for Hoy. Stale local cards MUST NOT be treated as current operational state.

#### Scenario: Cash count refreshes both surfaces
- **WHEN** the merchant records a cash count that matches expected cash
- **THEN** a later view of Inicio indicators and of Hoy MUST show `ready_to_close` / `Caja cuadrada` from the new GET
