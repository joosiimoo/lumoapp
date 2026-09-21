## MODIFIED Requirements

### Requirement: GenerativeUIRenderer owns rendering
Flutter MUST provide a `GenerativeUIRenderer` that renders only backend-emitted generative UI contracts. It MUST register `sale_item_added` version `1`, `sale_summary` version `1`, and `sale_confirmed` version `1`. Unknown components, versions, fields, or actions MUST display `fallback_text` and MUST NOT run actions. Flutter MUST NOT compose or register backend UI contracts. Flutter MUST NOT calculate line totals, session totals, summary totals, or payment amounts.

#### Scenario: Fallback for unknown component
- **WHEN** the API returns a UI payload whose `component` is unknown to the renderer
- **THEN** the app MUST show that payload's `fallback_text` and MUST NOT invoke any included action

#### Scenario: Sale summary is handled
- **WHEN** the API returns `sale_summary` version `1`
- **THEN** the renderer MUST handle it and MUST display `data.total` without summing item `line_total`s

#### Scenario: Sale confirmed is handled
- **WHEN** the API returns `sale_confirmed` version `1`
- **THEN** the renderer MUST handle it and MUST display `data.total` and `data.payment` without calculating money

### Requirement: Inicio composer sends conversation turns
The Inicio feature MUST use the existing sticky `LumoComposer` to send non-empty user text to `POST /api/v1/lumo/messages` through the typed API client. The client MUST attach `Authorization`, `Idempotency-Key`, and `X-Correlation-ID`. Inicio MUST maintain a stable client-generated UUID as `conversation_id` for the current conversational sale context and MUST send it on every message POST, including clarification follow-ups, `totalizar`, payment phrases, and the next product utterance after `sale_confirmed@1`. Inicio MUST NOT rotate `conversation_id` after a successful confirmation. A new conversational sale context (new Inicio widget / app process) MUST be able to use a new UUID. Views MUST NOT construct URLs or calculate line, session, or payment totals. Hoy, Memoria, and Negocio MAY remain placeholders. The four-tab shell MUST remain.

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

#### Scenario: Retry reuses key
- **WHEN** the mutating message request fails after dispatch with an unknown outcome and the user retries the same send
- **THEN** the client MUST resend the original idempotency key

#### Scenario: Enter submits
- **WHEN** the composer has non-empty text and the user presses Enter
- **THEN** the same submit path as the send button MUST run

#### Scenario: Whitespace does not send
- **WHEN** the composer text is empty or only whitespace and the user presses Enter or taps send
- **THEN** the client MUST NOT POST a message
