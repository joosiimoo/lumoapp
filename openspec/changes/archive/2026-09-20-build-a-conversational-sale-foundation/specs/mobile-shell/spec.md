## ADDED Requirements

### Requirement: Inicio composer sends conversation turns
The Inicio feature MUST use the existing sticky `LumoComposer` to send non-empty user text to `POST /api/v1/lumo/messages` through the typed API client. The client MUST attach `Authorization`, `Idempotency-Key`, and `X-Correlation-ID`. Inicio MUST maintain a stable client-generated UUID as `conversation_id` for the current conversational sale context and MUST send it on every message POST, including clarification follow-ups. A new conversational sale context MUST be able to use a new UUID. Views MUST NOT construct URLs or calculate line totals. Hoy, Memoria, and Negocio MAY remain placeholders. The four-tab shell MUST remain.

Enter and the send button MUST invoke the same submit handler. Empty or whitespace-only text MUST NOT send. Retry MUST reuse the same idempotency key for the same in-flight send.

#### Scenario: Composer posts to the agent API
- **WHEN** the user submits `900gr zanahoria` on Inicio
- **THEN** the typed client MUST `POST /api/v1/lumo/messages` with that message, a non-empty `conversation_id`, and an idempotency key

#### Scenario: Clarification reuses conversation id
- **WHEN** the user submits `"900 zanahoria"` and then `"gr"` on the same Inicio instance
- **THEN** both POSTs MUST send the same `conversation_id`

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
