## MODIFIED Requirements

### Requirement: Closed generative UI action catalog
The backend MUST expose a closed `UiActionRegistry` separate from `ToolRegistry`. The registered action ids MUST be `sale.pay.cash@1`, `sale.pay.card@1`, `sale.pay.transfer@1`, `sale.remove_item@1`, `sale.void.request@1`, `sale.void.confirm@1`, `closing.request@1`, `closing.confirm@1`, and `closing.submit_cash_count@1`. Each id is versioned inside the string because `GenerativeUIAction` has no version field. `option_id` MUST be null except where a later requirement explicitly allows a null-only option. The registry MUST NOT include `payment.resolve`, a mixed-payment action, an undo-without-void action, or a reopen action. `closing.confirm@1` as an action id MUST NOT be registered again as a tool. `closing.submit_cash_count@1` as an action id MUST invoke the existing `RecordCashCount` / `closing.submit_cash_count@1` tool workflow and MUST NOT invent a second cash-count state machine.

#### Scenario: Boot catalog
- **WHEN** the application boots
- **THEN** `UiActionRegistry` MUST contain exactly those nine ids and `ToolRegistry` MUST remain a separate catalog

#### Scenario: Unknown action id
- **WHEN** a caller submits `action_id` `sale.pay.cheque@1`
- **THEN** the registry MUST report it as unregistered and no sale or close MUST be mutated

### Requirement: UI action endpoint
The API MUST expose `POST /api/v1/lumo/actions`. The body MUST accept `action_id`, `context_token`, `conversation_id`, and `idempotency_key`, and MAY accept `option_id` only when it is null. A `payload` property MUST be omitted or an empty object except: `sale.void.confirm@1` MAY include `{ "void_reason": string }`; `closing.submit_cash_count@1` MUST include `{ "amount": decimal-string }`; `closing.confirm@1` MAY include `{ "close_note": string }`. Amounts for payments, payment methods, `sale_session_id`, operational day ids, and snapshot ids in the body MUST be rejected. `sale_session_id` for a payment action MUST travel only inside the signed `context_token`. Cash count `amount` MUST travel only in the allowed payload for `closing.submit_cash_count@1` and MUST NOT appear in the JWT. The header `Idempotency-Key` MUST equal `idempotency_key`. The route MUST authenticate, derive `TenantContext` from the session, require the idempotency header, and propagate `X-Correlation-ID`. The handler MUST call the single orchestrator action entry and MUST NOT call `LLMProvider.interpret`. The response shape MUST be `message_id`, `status`, `text`, `ui`, and `correlation_id`. `POST /api/v1/lumo/messages` MUST remain the path for typed phrases.

#### Scenario: Cash tap does not invent a phrase
- **WHEN** Inicio posts `sale.pay.cash@1` with the server token, conversation id, and idempotency key
- **THEN** the handler MUST run the payment workflow without interpreting free text as a payment phrase

#### Scenario: Structured cash count payload is accepted
- **WHEN** the workspace posts `closing.submit_cash_count@1` with payload `amount` `20.00`
- **THEN** the route MUST accept that payload shape and MUST NOT require a message phrase

### Requirement: Operator review uses silent request_close then closing.confirm@1
`closing.request@1` and `closing.confirm@1` MUST remain the close request/confirm action ids. The approved operator path MUST mint the confirmation token by silently running existing `request_close` via `POST /api/v1/lumo/messages` with the technical identifier `cerrar el día` (or existing `closing.request@1` fallback if messages would persist a visible merchant turn). The Hoy close workspace MUST then post `closing.confirm@1` with that server-issued token and MAY include optional payload `close_note`. Flutter MUST NOT treat the technical identifier as merchant-visible copy. Typed composer `cerrar el día` and `confirmar cierre` MUST keep working as the historical conversational path. `closing.request@1` MUST still run `request_close` and MUST NOT call `closing.confirm@1`. `closing.confirm@1` MUST still require the server confirmation token.

#### Scenario: Request close from workspace does not require a bubble
- **WHEN** the merchant confirms close from the Hoy workspace for a counted open day
- **THEN** existing `request_close` MUST run to mint the token, the day MUST remain `open` until confirm succeeds, and the client MUST NOT show a merchant bubble `cerrar el día`

#### Scenario: Confirm from the workspace is the same workflow
- **WHEN** the workspace posts `closing.confirm@1` with a matching unexpired token
- **THEN** the confirm MUST follow the existing `closing.confirm@1` workflow and MUST NOT use a second close state machine

## ADDED Requirements

### Requirement: Structured cash count action submits amount payload
`closing.submit_cash_count@1` as a UiAction MUST carry an HS256 `typ=ui_action` `context_token` bound to `action_id`, `business_id`, `actor_id`, and `conversation_id`, and MUST NOT put the counted amount in the JWT. The server MUST validate `payload.amount` with the existing cash-count parser and MUST execute `RecordCashCount` with the same idempotency, audit, outbox, and preparation-output guarantees as the message path. Flutter MUST NOT invent expected cash, difference, or cash status from the submitted amount. The operator workspace MUST NOT require appending a merchant transcript turn for that count.

#### Scenario: Structured count records without a phrase
- **WHEN** the workspace posts `closing.submit_cash_count@1` with payload amount `20.00` for an open day expecting `22.50`
- **THEN** a current CashCount of `20.00` MUST be persisted, the response MUST carry server `cash_difference` and `cash_status` `short`, and no merchant transcript bubble is required for that operator path

#### Scenario: Invalid amount does not write
- **WHEN** the workspace posts `closing.submit_cash_count@1` with an invalid amount string
- **THEN** the server MUST refuse without inserting a CashCount

### Requirement: Confirm payload may include close_note
`closing.confirm@1` MAY accept optional `payload.close_note` as a string. Blank or missing MUST store null. When non-empty after trim, the confirm workflow MUST persist it on the new `ClosingSnapshot.close_note` and MUST include it in audit/event facts as specified by `closing-snapshot-foundation` and `factual-event-memory`. The note MUST NOT alter fingerprint verification or money fields.

#### Scenario: Note persists on close
- **WHEN** confirm succeeds with `close_note` `Faltaron dos billetes de 20`
- **THEN** the ClosingSnapshot MUST store that note and money totals MUST still equal server preparation figures

#### Scenario: Stale token still refused with note
- **WHEN** confirm is posted with a stale token and a note
- **THEN** the day MUST stay open, no snapshot MUST be written, and the note MUST NOT be persisted
