## Purpose

Flutter application shell: environments, typed API client, four-tab navigation, GenerativeUIRenderer (`sale_item_added@1`, `sale_summary@1`, `sale_confirmed@1`, `operational_day_summary@1`, `daily_close_preparation@1`, `daily_close_confirmed@1`), and a live Inicio conversation stream with a stable `conversation_id`. Hoy, Memoria, and Negocio MAY remain placeholders.
## Requirements
### Requirement: Flutter application shell
The mobile client MUST be a Flutter application with an app bootstrap, environment configuration, and a visual shell that uses a centered content column of max-width 420px on the design-system canvas color. Inicio is the live conversation stream. Hoy, Memoria, and Negocio MAY remain placeholders. The shell MUST exist and MUST NOT introduce a desktop layout or a dark theme.

#### Scenario: App boots against local API
- **WHEN** the app starts with a local environment file
- **THEN** it MUST load the configured API base URL without requiring a rebuild of secret values into source

#### Scenario: Content width
- **WHEN** the app is shown on a viewport wider than 420px
- **THEN** the primary content column MUST remain 420px wide on the warm canvas background

### Requirement: Environment configuration
The app MUST support distinct environments (`local`, `staging`, `production`) for API base URL and non-secret flags. Secrets MUST NOT be committed. The selected environment MUST be readable by the API client at runtime.

#### Scenario: Local environment
- **WHEN** the local flavor is selected
- **THEN** the API client MUST target the local Compose API origin

### Requirement: Typed API client foundation
Views MUST NOT construct URLs, parse raw HTTP, or compute domain totals. A single typed client MUST send JSON `snake_case`, attach `Authorization`, `Idempotency-Key` on mutations, and `X-Correlation-ID`, and decode the public error envelope.

#### Scenario: Mutation headers
- **WHEN** the client sends a mutating request
- **THEN** the request MUST include `Idempotency-Key` and a correlation id

#### Scenario: Error envelope decoded
- **WHEN** the server returns the standard error envelope
- **THEN** the client MUST expose `code`, `message`, `retryable`, and `correlation_id` to callers

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
Flutter MUST NOT calculate monetary totals, daily sales totals, payment-method splits, conversions, expected cash, counted cash, cash differences, cash status, averages, close readiness, or outcome gates. Display formatting of server-provided amounts and dates in the business locale is allowed. Formatting an ISO `business_date` MUST NOT change the calendar day and MUST NOT use the device timezone to choose the day. Formatting an ISO `counted_at` for display is allowed and MUST NOT change the stored instant. A `+` prefix on a positive overage amount is display-only and MUST NOT be treated as a computed difference. Flutter MUST NOT choose a payment method, a close request, or a close confirmation except by submitting an action or approved phrase the server already maps, including a silent `request_close` used only to populate the review surface.

#### Scenario: Client formatting only
- **WHEN** the API returns a decimal money string and currency code
- **THEN** the app MAY format it for display and MUST NOT recompute the amount

#### Scenario: Daily totals stay on the server
- **WHEN** the API returns `operational_day_summary@1`
- **THEN** the app MUST display `sale_count`, `gross_sales_total`, `cash_total`, `card_total`, and `transfer_total` from that payload and MUST NOT add those amounts together

#### Scenario: Cash difference stays on the server
- **WHEN** the API returns `daily_close_preparation@1` with `expected_cash` `22.50`, `counted_cash` `20.00`, `cash_difference` `-2.50`, and `cash_status` `short`
- **THEN** the app MUST display those server values and MUST NOT subtract the amounts or derive the status itself

#### Scenario: Hoy totals stay on the server
- **WHEN** Hoy renders `GET /api/v1/business-stream/today`
- **THEN** the app MUST display `sale_count`, `gross_sales_total`, and tender totals from that payload and MUST NOT add those amounts together

#### Scenario: Review difference stays on the server
- **WHEN** the review surface shows `expected_cash` `22.50`, `counted_cash` `20.00`, `cash_difference` `-2.50`, and `cash_status` `short`
- **THEN** the app MUST display those server values and MUST NOT subtract the amounts or derive the status itself

### Requirement: Safe mutation retry
The client MUST reuse the same `Idempotency-Key` when retrying a mutation that may have been committed. For a UI action, that key MUST be the server-issued `idempotency_key` on the action. Optimistic visual state MUST NOT be treated as business confirmation. A failed action MUST leave the current card in place.

#### Scenario: Retry reuses key
- **WHEN** a mutating request fails after dispatch with an unknown outcome and the user retries
- **THEN** the client MUST resend the original idempotency key

#### Scenario: Action retry reuses the server key
- **WHEN** a tap of `sale.pay.cash@1` fails after dispatch and the user retries that control
- **THEN** the client MUST resend that action's original `idempotency_key` and MUST NOT show a confirmed sale before the successful response

### Requirement: GenerativeUIRenderer owns rendering
Flutter MUST provide a `GenerativeUIRenderer` that renders only backend-emitted generative UI contracts. It MUST register `sale_item_added` version `1`, `sale_summary` version `1`, `sale_confirmed` version `1`, `operational_day_summary` version `1`, `daily_close_preparation` version `1`, `daily_close_confirmed` version `1`, and `next_best_action` version `1`. Unknown components or versions MUST display `fallback_text` and MUST NOT run actions. Unknown action ids MUST NOT run. Flutter MUST NOT compose or register backend UI contracts. Flutter MUST NOT calculate line totals, session totals, summary totals, payment amounts, daily totals, expected cash, counted cash, or cash differences. Flutter MUST NOT display `confirmation_token` or `context_token`.

When the response contains one known version-1 contract and `text.strip()` equals that contract's `fallback_text.strip()`, Flutter MUST render the card as the assistant artifact and MUST NOT also render a visible prose block if the component is `sale_item_added`, `sale_summary`, `sale_confirmed`, `operational_day_summary`, `next_best_action`, or `daily_close_confirmed`, or if it is `daily_close_preparation` and `fallback_text` starts with `Cierre `. In every other case with a known card, Flutter MUST render the response `text` and the card. An empty `ui` MUST render `text` only. The card SHOULD expose `fallback_text` as an accessibility summary when the visible prose is omitted.

#### Scenario: Fallback for unknown component
- **WHEN** the API returns a UI payload whose `component` is unknown to the renderer
- **THEN** the app MUST show that payload's `fallback_text` and MUST NOT invoke any included action

#### Scenario: Sale summary is handled
- **WHEN** the API returns `sale_summary` version `1`
- **THEN** the renderer MUST handle it and MUST display `data.total` without summing item `line_total`s

#### Scenario: Sale confirmed is handled
- **WHEN** the API returns `sale_confirmed` version `1`
- **THEN** the renderer MUST handle it, MUST display every server item, and MUST display `data.total` without calculating money

#### Scenario: Operational day summary is handled
- **WHEN** the API returns `operational_day_summary` version `1`
- **THEN** the renderer MUST handle it and MUST display the server sale count and daily totals without summing payment methods

#### Scenario: Daily close preparation is handled
- **WHEN** the API returns `daily_close_preparation` version `1`
- **THEN** the renderer MUST handle it and MUST display the server expected cash, counted cash, difference, and status without recomputing them

#### Scenario: Daily close confirmed is handled
- **WHEN** the API returns `daily_close_confirmed` version `1`
- **THEN** the renderer MUST handle it and MUST display the server gross, expected cash, counted cash, and difference without recomputing them

#### Scenario: Next best action is handled
- **WHEN** the API returns `next_best_action` version `1`
- **THEN** the renderer MUST handle it and MUST display the server `title` and `reason` without calculating money or choosing another action

#### Scenario: Duplicate preparation prose is omitted
- **WHEN** the response `text` equals the `daily_close_preparation@1` `fallback_text` and that text starts with `Cierre `
- **THEN** the stream MUST show the card and MUST NOT show a second visible copy of that sentence

#### Scenario: Duplicate next-action prose is omitted
- **WHEN** the response `text` equals the `next_best_action@1` `fallback_text`
- **THEN** the stream MUST show the card and MUST NOT show a second visible copy of that sentence

#### Scenario: Request-close prose is kept
- **WHEN** the response `text` starts with `El cierre está preparado`
- **THEN** the stream MUST show that prose and the preparation card

#### Scenario: Clarification stays prose
- **WHEN** the response has an empty `ui` and a clarification `text`
- **THEN** the stream MUST show that prose and MUST NOT invent a card

### Requirement: Inicio composer sends conversation turns
The Inicio feature MUST use the existing sticky `LumoComposer` to send non-empty user text to `POST /api/v1/lumo/messages` through the typed API client. The client MUST attach `Authorization`, `Idempotency-Key`, and `X-Correlation-ID`. Inicio MUST maintain a stable client-generated UUID as `conversation_id` for the current conversational sale context and MUST send it on every message POST and every action POST, including clarification follow-ups, `totalizar`, payment phrases, payment taps, day-summary phrases, cash-count phrases, close-preparation phrases, request-close phrases, request-close taps, confirm phrases, confirm taps, and the next product utterance after `sale_confirmed@1`. Inicio MUST NOT rotate `conversation_id` after a successful sale confirmation, after a day summary, after a cash count, after a preparation read, or after a daily close confirmation. When the latest confirmable `daily_close_preparation@1` carried a `closing.confirm@1` action, the next typed confirm POST MUST include that action's `context_token` as `client_context.confirmation_token` and MUST NOT put it in the visible message. `data.confirmation_token` MUST match that token when both are present; a mismatch MUST NOT be sent. A response that clears the token or returns `daily_close_confirmed@1` MUST drop it. A new conversational sale context (new Inicio widget / app process) MUST be able to use a new UUID. Views MUST NOT construct URLs or calculate line, session, payment, daily, or cash totals. Hoy, Memoria, and Negocio MAY remain placeholders. The four-tab shell MUST remain.

A recognized action tap MUST `POST /api/v1/lumo/actions` with the emitted `action_id`, null `option_id`, `context_token`, `conversation_id`, and `idempotency_key`. It MUST NOT send `sale_session_id` as its own body field, append a user bubble, or synthesize a phrase. While that card's action is in flight, its actions MUST be disabled and the tapped control MUST show a loading state. A second tap MUST NOT start another request. On transport failure the source card MUST remain and a non-destructive error MUST be shown. On `ui_action_stale` the source card MUST remain, its actions MUST stay disabled, the stream MUST show `Esta acción ya no aplica a la venta en curso.`, and the stream MUST NOT append a user bubble or a `sale_confirmed@1` card. On success the response card MUST be appended and the source card's actions MUST stay disabled. That disabled state is a UX optimization only. The server token binding remains the authority if the widget rebuilds, the stream is restored, or an old card is still able to submit. The composer MUST remain usable.

Enter and the send button MUST invoke the same submit handler. Empty or whitespace-only text MUST NOT send. Retry MUST reuse the same idempotency key for the same in-flight send or the same action.

#### Scenario: Composer posts to the agent API
- **WHEN** the user submits `900gr zanahoria` on Inicio
- **THEN** the typed client MUST `POST /api/v1/lumo/messages` with that message, a non-empty `conversation_id`, and an idempotency key

#### Scenario: Clarification reuses conversation id
- **WHEN** the user submits `"900 zanahoria"` and then `"gr"` on the same Inicio instance
- **THEN** both POSTs MUST send the same `conversation_id`

#### Scenario: Totalizar reuses conversation id
- **WHEN** the user submits a catalog item and then `totalizar` on the same Inicio instance
- **THEN** both POSTs MUST send the same `conversation_id`

#### Scenario: Payment and next sale reuse conversation id
- **WHEN** the user submits `efectivo` after `sale_summary@1` and then `900gr zanahoria` on the same Inicio instance
- **THEN** those POSTs MUST send the same `conversation_id` that was used to build the confirmed sale, and Flutter MUST NOT generate a new UUID after the confirmation card

#### Scenario: Day summary reuses conversation id
- **WHEN** the user submits `ventas de hoy` on the same Inicio instance used to confirm a sale
- **THEN** that POST MUST send the same `conversation_id` and Flutter MUST NOT generate a new UUID

#### Scenario: Cash count reuses conversation id
- **WHEN** the user submits `tengo 20 en caja` and then `preparar el cierre` on the same Inicio instance used to confirm a sale
- **THEN** both POSTs MUST send that same `conversation_id` and Flutter MUST NOT generate a new UUID

#### Scenario: Close confirmation reuses conversation id and echoes the token
- **WHEN** the user submits `cerrar el día` and then `confirmar cierre` on the same Inicio instance after a counted open day
- **THEN** both POSTs MUST send that same `conversation_id`, the second POST MUST include the server confirmation token in `client_context`, and Flutter MUST NOT generate a new UUID

#### Scenario: Payment tap posts the action
- **WHEN** the user taps Efectivo on `sale_summary@1`
- **THEN** the client MUST `POST /api/v1/lumo/actions` with `sale.pay.cash@1` and that card's idempotency key, the body MUST NOT contain `sale_session_id`, and the stream MUST NOT gain a user bubble whose text is `efectivo`

#### Scenario: Disabled buttons are not the safety check
- **WHEN** an old `sale_summary@1` card is still able to submit its original payment action after a later sale exists
- **THEN** Flutter MUST submit that original token unchanged and MUST NOT rewrite it toward the later sale

#### Scenario: Stale action shows clarification without a confirmed card
- **WHEN** a payment action response has empty `ui` and text `Esta acción ya no aplica a la venta en curso.`
- **THEN** the stream MUST show that text, MUST keep the source card, MUST leave its actions disabled, and MUST NOT append `sale_confirmed@1`

#### Scenario: Retry reuses key
- **WHEN** the mutating message request fails after dispatch with an unknown outcome and the user retries the same send
- **THEN** the client MUST resend the original idempotency key

#### Scenario: Enter submits
- **WHEN** the composer has non-empty text and the user presses Enter
- **THEN** the same submit path as the send button MUST run

#### Scenario: Whitespace does not send
- **WHEN** the composer text is empty or only whitespace and the user presses Enter or taps send
- **THEN** the client MUST NOT POST a message

### Requirement: Inicio header shows the active business
The Inicio eyebrow MUST be `LUMO · {business name}` in uppercase, where `{business name}` is the authenticated session business (Carrota for the local seed). It MUST NOT hardcode `NEGOCIO` or use the current navigation tab as the second label.

#### Scenario: Seeded Carrota header
- **WHEN** the signed-in local Carrota session is shown on Inicio
- **THEN** the eyebrow MUST display `LUMO · CARROTA`

### Requirement: Inicio greeting uses the design-system accent
The Inicio greeting copy MUST be `Buenos días` (including the acute accent). It MUST use the Design System display greeting (Instrument Serif italic) with the Lumo text gradient. The screen MUST NOT be redesigned.

#### Scenario: Greeting treatment
- **WHEN** Inicio renders
- **THEN** `Buenos días` MUST be visible with the display-greeting style and Lumo gradient

### Requirement: Inicio hosts the business stream above the conversation
Inicio MUST show the Business Stream panel when the tab becomes visible, in a compact header below the existing `Buenos días` greeting and outside the scrolling transcript. It MUST keep `LumoComposer`, the four-tab shell, and the conversation-card renderer for typed turns. The panel MUST NOT replace Hoy, Memoria, or Negocio. A `record_cash_count` control MUST only focus that composer. A `request_close` control with `invocation` `review_surface` MUST silent-post `primary_action.message` on the shell `conversation_id` and open the Daily Close review surface. It MUST NOT append a merchant bubble `cerrar el día` or a transcript `daily_close_preparation@1` card. Typed composer `cerrar el día` MAY keep the historical conversational path. After a successful message or action from that conversation, and after a successful close confirm from the review surface, Inicio MUST reload the panel. Transport failure MUST show `No pude consultar el estado de hoy.` and MUST NOT present the last successful totals as current. Hoy MUST use the same today GET as its structured daily summary and MUST NOT use the next-best-action GET as its primary body.

#### Scenario: Greeting and composer stay
- **WHEN** Inicio renders with a business stream panel
- **THEN** `Buenos días` MUST remain visible and the existing composer MUST remain usable

#### Scenario: Close from the panel opens review
- **WHEN** the merchant taps `Revisar cierre` on the Inicio panel
- **THEN** the client MUST silent-post `request_close` on the shell `conversation_id`, MUST open the review surface, and MUST NOT append a user turn `cerrar el día`

#### Scenario: Other tabs stay distinct
- **WHEN** the merchant opens Hoy or Memoria after this panel exists
- **THEN** Hoy MUST show the structured daily summary from the today GET and Memoria MUST still load its event timeline

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

