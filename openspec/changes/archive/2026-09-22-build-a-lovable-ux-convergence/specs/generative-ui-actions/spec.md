## ADDED Requirements

### Requirement: Closed generative UI action catalog
The backend MUST expose a closed `UiActionRegistry` separate from `ToolRegistry`. The only registered action ids MUST be `sale.pay.cash@1`, `sale.pay.card@1`, `sale.pay.transfer@1`, `closing.request@1`, and `closing.confirm@1`. Each id is versioned inside the string because `GenerativeUIAction` has no version field. `option_id` MUST be null. The registry MUST NOT include `payment.resolve`, a mixed-payment action, an undo action, a reopen action, or an inline cash-count action. `closing.confirm@1` as an action id MUST NOT be registered again as a tool.

#### Scenario: Boot catalog
- **WHEN** the application boots
- **THEN** `UiActionRegistry` MUST contain exactly those five ids and `ToolRegistry` MUST be unchanged

#### Scenario: Unknown action id
- **WHEN** a caller submits `action_id` `sale.pay.cheque@1`
- **THEN** the registry MUST report it as unregistered and no sale or close MUST be mutated

### Requirement: UI action endpoint
The API MUST expose `POST /api/v1/lumo/actions`. The body MUST accept `action_id`, `context_token`, `conversation_id`, and `idempotency_key`, and MAY accept `option_id` only when it is null. A `payload` property MUST be omitted or an empty object. Amounts, payment methods, `sale_session_id`, operational day ids, snapshot ids, and cash figures in the body MUST be rejected. `sale_session_id` for a payment action MUST travel only inside the signed `context_token`. The header `Idempotency-Key` MUST equal `idempotency_key`. The route MUST authenticate, derive `TenantContext` from the session, require the idempotency header, and propagate `X-Correlation-ID`. The handler MUST call the single orchestrator action entry and MUST NOT call `LLMProvider.interpret`. The response shape MUST be `message_id`, `status`, `text`, `ui`, and `correlation_id`. `POST /api/v1/lumo/messages` MUST remain the path for typed phrases.

#### Scenario: Cash tap does not invent a phrase
- **WHEN** Inicio posts `sale.pay.cash@1` with the server token, conversation id, and idempotency key
- **THEN** the orchestrator MUST NOT interpret the message `efectivo` and MUST still invoke `sale.commit@1` with method `cash`

#### Scenario: Business figures in the body are rejected
- **WHEN** the action body includes `total`, `sale_session_id`, or `operational_day_id`
- **THEN** the request MUST fail validation and no `Payment` or `ClosingSnapshot` MUST be written

#### Scenario: Header and body keys differ
- **WHEN** `Idempotency-Key` is not equal to `idempotency_key`
- **THEN** the request MUST fail validation and MUST NOT mutate

### Requirement: Action context tokens
`closing.request@1` MUST carry an HS256 `context_token` with `iss=lumo`, `typ=ui_action`, signed with `DEV_TOKEN_SECRET`, expiring 15 minutes after `iat`. Its claims MUST be `action_id`, `business_id`, `actor_id`, and `conversation_id`, and MUST NOT include amounts, `sale_session_id`, or `operational_day_id`. `sale.pay.cash@1`, `sale.pay.card@1`, and `sale.pay.transfer@1` MUST carry the same token type plus `sale_session_id` of the `ready_to_charge` session that emitted the card. Payment claims MUST NOT include an amount, a total, a payment amount, a payment method, `operational_day_id`, or product rows. The server MUST reject a token whose signature, expiry, type, action id, tenant, actor, or conversation does not match the request, and a payment token that omits `sale_session_id`, and MUST NOT mutate on that rejection. `closing.confirm@1` MUST carry the existing `typ=closing_confirm` token as `context_token` and MUST NOT wrap it in `typ=ui_action`.

#### Scenario: Payment token binds the emitting sale
- **WHEN** `sale_summary@1` is composed for session A
- **THEN** each payment action token MUST contain `sale_session_id` A and MUST NOT contain an amount

#### Scenario: Payment token binds the conversation
- **WHEN** a `sale.pay.card@1` token was issued for conversation A and is posted with conversation B
- **THEN** the server MUST reject it and MUST NOT confirm a sale

#### Scenario: Tampered sale session claim fails closed
- **WHEN** a client alters `sale_session_id` inside a payment `context_token`
- **THEN** signature verification MUST fail and no `Payment` MUST be written

#### Scenario: Confirm action reuses the close token
- **WHEN** `request_close` issues a `closing_confirm` token
- **THEN** the `closing.confirm@1` action `context_token` MUST be that token and `data.confirmation_token` MUST be the same string

### Requirement: Payment action targets only its bound session
Payment handling MUST follow this order: validate the envelope, verify the JWT, hash `action_id|conversation_id|commit|payment_method|sale_session_id`, peek idempotency, return a completed same-key body immediately, load the token-bound session, inspect newer active sessions, then choose commit, confirmed read-back, or `ui_action_stale`. Only the commit path may call `idempotency.begin`. A completed same key and hash MUST return the stored body and MUST NOT be classified as `ui_action_stale`, even when a newer active session exists. That stored body is an exact replay, not a fresh current-state read-back. The handler MUST NOT choose the conversation's newest active session as the target. When the bound row is the conversation's locked `ready_to_charge` session, it MUST call `CommitSaleSession` for that id only. When the bound row is `confirmed` and no newer `open` or `ready_to_charge` session exists, it MUST return that session's `sale_confirmed@1` and MUST NOT insert a payment, audit, outbox, or idempotency row. When the bound row is `confirmed` and a newer `open` or `ready_to_charge` session exists, it MUST return reason `ui_action_stale`, text `Esta acción ya no aplica a la venta en curso.`, and empty `ui`, and MUST NOT compose the bound session's `sale_confirmed@1`. The same stale result MUST be returned when the token session is missing, is `open` but is not the locked actionable sale, is `ready_to_charge` but is not the locked actionable sale, or is any other signed state that is not an exact replay, the current `ready_to_charge` target, or a confirmed read-back with no newer active sale. A stale result MUST NOT insert a `Payment`, transition audit, outbox row, or idempotency reservation, and MUST NOT interpret a phrase or retarget the action.

#### Scenario: Current payment action commits its own sale
- **WHEN** `sale.pay.cash@1` is posted and its token `sale_session_id` is the conversation's `ready_to_charge` session
- **THEN** that session MUST become `confirmed` with one cash `Payment` and the response MUST include `sale_confirmed@1`

#### Scenario: Unused old action is stale once a newer sale exists
- **WHEN** session A was confirmed by `efectivo`, session B is `ready_to_charge` in the same conversation, and the unused `sale.pay.cash@1` token bound to A is submitted
- **THEN** the response MUST have reason `ui_action_stale`, text `Esta acción ya no aplica a la venta en curso.`, and empty `ui`, session B MUST stay `ready_to_charge`, and no `Payment`, audit, outbox, or idempotency row MUST be written

#### Scenario: Same-key replay precedes the stale check
- **WHEN** `sale.pay.cash@1` for session A already completed under a key and the same key, token, and action id are posted again after session B is `ready_to_charge`
- **THEN** the stored session A body MUST be returned, including its `sale_confirmed@1`, and session B MUST NOT be confirmed

#### Scenario: Confirmed action read-back needs no newer sale
- **WHEN** the token-bound session is `confirmed`, no newer `open` or `ready_to_charge` session exists, and a new payment-action key is submitted
- **THEN** the response `ui` MUST include that session's `sale_confirmed@1` and no new `Payment` or idempotency row MUST be written

#### Scenario: Mismatched unbound session writes nothing
- **WHEN** a payment token's `sale_session_id` is not the locked `ready_to_charge` session and that id is not a `confirmed` session with no newer active sale
- **THEN** the reason MUST be `ui_action_stale` and no `Payment`, transition audit, outbox row, or idempotency reservation MUST be written

### Requirement: Action idempotency matches the typed mutation
A payment action MUST use operation type `lumo.message.commit_sale` and a request hash of `action_id|conversation_id|commit|payment_method|sale_session_id`. A confirm action MUST use `lumo.message.confirm_close` and a request hash of `action_id|conversation_id|token`. The same key and hash MUST replay the stored body before any stale-session check. A different key whose bound session is already `confirmed` MUST read back that session only when no newer `open` or `ready_to_charge` session exists, and otherwise MUST return `ui_action_stale` without composing that historical card. Either fresh outcome MUST NOT insert a second payment, transition audit, or outbox event. A different key after a successful close MUST follow the existing close read-back and MUST NOT insert a second snapshot. `closing.request@1` MUST NOT insert an idempotency row. The server MUST issue the action `idempotency_key` when it composes the action. Flutter MUST echo it and MUST NOT replace it on retry.

#### Scenario: Double tap uses one key
- **WHEN** `sale.pay.cash@1` is submitted twice with the same idempotency key and hash against a `ready_to_charge` session
- **THEN** exactly one `Payment` MUST exist and the second response MUST be the stored replay

#### Scenario: Retry after a lost response
- **WHEN** a confirm action fails after dispatch with an unknown outcome and is retried with the same key and hash
- **THEN** the client key MUST be unchanged and the server MUST NOT create a second snapshot

### Requirement: Typed and tapped paths share the workflow
A tapped payment and the approved phrase for that method MUST both call `CommitSaleSession` and produce the same session status, payment method, audit action `sale.commit@1`, and outbox events. `closing.request@1` and `cerrar el día` MUST both run `request_close` and MUST NOT call `closing.confirm@1`. `closing.confirm@1` and `confirmar cierre` MUST both call the confirm workflow with the server token. The action path MAY record `ui_action_id` in the existing audit JSON and MUST NOT add an audit table or a new outbox event name.

#### Scenario: Tap and phrase leave the same sale
- **WHEN** one ready-to-charge session is confirmed by `efectivo` and another by `sale.pay.cash@1`
- **THEN** both sessions MUST be `confirmed` with one cash `Payment` each and both audits MUST use action `sale.commit@1`

#### Scenario: Request action does not close
- **WHEN** a counted open day receives `closing.request@1`
- **THEN** the day MUST stay `open`, no snapshot MUST exist, and the response MUST include `closing.confirm@1` rather than a closed card
