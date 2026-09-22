## MODIFIED Requirements

### Requirement: No domain calculations on the client
Flutter MUST NOT calculate monetary totals, daily sales totals, payment-method splits, conversions, expected cash, counted cash, cash differences, cash status, averages, or outcome gates. Display formatting of server-provided amounts and dates in the business locale is allowed. Formatting an ISO `business_date` MUST NOT change the calendar day and MUST NOT use the device timezone to choose the day. Formatting an ISO `counted_at` for display is allowed and MUST NOT change the stored instant.

#### Scenario: Client formatting only
- **WHEN** the API returns a decimal money string and currency code
- **THEN** the app MAY format it for display and MUST NOT recompute the amount

#### Scenario: Daily totals stay on the server
- **WHEN** the API returns `operational_day_summary@1`
- **THEN** the app MUST display `sale_count`, `gross_sales_total`, `cash_total`, `card_total`, and `transfer_total` from that payload and MUST NOT add those amounts together

#### Scenario: Cash difference stays on the server
- **WHEN** the API returns `daily_close_preparation@1` with `expected_cash` `22.50`, `counted_cash` `20.00`, `cash_difference` `-2.50`, and `cash_status` `short`
- **THEN** the app MUST display those server values and MUST NOT subtract the amounts or derive the status itself

### Requirement: GenerativeUIRenderer owns rendering
Flutter MUST provide a `GenerativeUIRenderer` that renders only backend-emitted generative UI contracts. It MUST register `sale_item_added` version `1`, `sale_summary` version `1`, `sale_confirmed` version `1`, `operational_day_summary` version `1`, and `daily_close_preparation` version `1`. Unknown components, versions, fields, or actions MUST display `fallback_text` and MUST NOT run actions. Flutter MUST NOT compose or register backend UI contracts. Flutter MUST NOT calculate line totals, session totals, summary totals, payment amounts, daily totals, expected cash, or cash differences.

#### Scenario: Fallback for unknown component
- **WHEN** the API returns a UI payload whose `component` is unknown to the renderer
- **THEN** the app MUST show that payload's `fallback_text` and MUST NOT invoke any included action

#### Scenario: Sale summary is handled
- **WHEN** the API returns `sale_summary` version `1`
- **THEN** the renderer MUST handle it and MUST display `data.total` without summing item `line_total`s

#### Scenario: Sale confirmed is handled
- **WHEN** the API returns `sale_confirmed` version `1`
- **THEN** the renderer MUST handle it and MUST display `data.total` and `data.payment` without calculating money

#### Scenario: Operational day summary is handled
- **WHEN** the API returns `operational_day_summary` version `1`
- **THEN** the renderer MUST handle it and MUST display the server sale count and daily totals without summing payment methods

#### Scenario: Daily close preparation is handled
- **WHEN** the API returns `daily_close_preparation` version `1`
- **THEN** the renderer MUST handle it and MUST display the server expected cash, counted cash, difference, and status without recomputing them

### Requirement: Inicio composer sends conversation turns
The Inicio feature MUST use the existing sticky `LumoComposer` to send non-empty user text to `POST /api/v1/lumo/messages` through the typed API client. The client MUST attach `Authorization`, `Idempotency-Key`, and `X-Correlation-ID`. Inicio MUST maintain a stable client-generated UUID as `conversation_id` for the current conversational sale context and MUST send it on every message POST, including clarification follow-ups, `totalizar`, payment phrases, day-summary phrases, cash-count phrases, close-preparation phrases, and the next product utterance after `sale_confirmed@1`. Inicio MUST NOT rotate `conversation_id` after a successful confirmation, after a day summary, after a cash count, or after a preparation read. A new conversational sale context (new Inicio widget / app process) MUST be able to use a new UUID. Views MUST NOT construct URLs or calculate line, session, payment, daily, or cash totals. Hoy, Memoria, and Negocio MAY remain placeholders. The four-tab shell MUST remain.

Enter and the send button MUST invoke the same submit handler. Empty or whitespace-only text MUST NOT send. Retry MUST reuse the same idempotency key for the same in-flight send.

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

#### Scenario: Retry reuses key
- **WHEN** the mutating message request fails after dispatch with an unknown outcome and the user retries the same send
- **THEN** the client MUST resend the original idempotency key

#### Scenario: Enter submits
- **WHEN** the composer has non-empty text and the user presses Enter
- **THEN** the same submit path as the send button MUST run

#### Scenario: Whitespace does not send
- **WHEN** the composer text is empty or only whitespace and the user presses Enter or taps send
- **THEN** the client MUST NOT POST a message
