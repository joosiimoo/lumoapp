# generative-ui-actions Specification

## Purpose
TBD - created by archiving change build-a-lovable-ux-convergence. Update Purpose after archive.
## Requirements
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

### Requirement: Operator review uses silent request_close then closing.confirm@1
`closing.request@1` and `closing.confirm@1` MUST remain the close request/confirm action ids. The approved operator path MUST mint the confirmation token by silently running existing `request_close` via `POST /api/v1/lumo/messages` with the technical identifier `cerrar el día` (or existing `closing.request@1` fallback if messages would persist a visible merchant turn). The Hoy close workspace MUST then post `closing.confirm@1` with that server-issued token and MAY include optional payload `close_note`. Flutter MUST NOT treat the technical identifier as merchant-visible copy. Typed composer `cerrar el día` and `confirmar cierre` MUST keep working as the historical conversational path. `closing.request@1` MUST still run `request_close` and MUST NOT call `closing.confirm@1`. `closing.confirm@1` MUST still require the server confirmation token.

#### Scenario: Request close from workspace does not require a bubble
- **WHEN** the merchant confirms close from the Hoy workspace for a counted open day
- **THEN** existing `request_close` MUST run to mint the token, the day MUST remain `open` until confirm succeeds, and the client MUST NOT show a merchant bubble `cerrar el día`

#### Scenario: Confirm from the workspace is the same workflow
- **WHEN** the workspace posts `closing.confirm@1` with a matching unexpired token
- **THEN** the confirm MUST follow the existing `closing.confirm@1` workflow and MUST NOT use a second close state machine

### Requirement: Remove and void action tokens bind ids only
`sale.remove_item@1` tokens MUST be `typ=ui_action` and MUST bind `sale_session_id` and `sale_item_id` without amounts. `sale.void.request@1` MUST bind `sale_session_id` and MUST return server before/after impact without mutating when the session is still `confirmed` on an open day. When the bound session is already `voided`, `sale.void.request@1` and `sale.void.confirm@1` MUST follow the voided read-back rules in `sale-corrections` and MUST NOT mutate. `sale.void.confirm@1` MUST bind `sale_session_id` and MUST accept `void_reason` only on the mutate path through the validated action path defined by the API (not free client totals). Amounts, expected cash, and day totals MUST remain server-authored in responses.

#### Scenario: Remove token binds item
- **WHEN** `sale_item_added@1` or `sale_summary@1` emits remove
- **THEN** the token MUST include that line's `sale_item_id` and MUST NOT include a line total

#### Scenario: Void request does not mutate
- **WHEN** `sale.void.request@1` is posted for a confirmed open-day sale
- **THEN** the session MUST stay `confirmed` and the response MUST include server before/after impact

#### Scenario: Void confirm on already voided is read-back
- **WHEN** `sale.void.confirm@1` is posted for a session that is already `voided`
- **THEN** the response MUST present the voided sale and MUST NOT write a second void audit, outbox event, or `sale_voided` memory row

### Requirement: Memoria may emit sale.void.request@1 with the same token rules
Memoria timeline responses MAY include `sale.void.request@1` using the same `typ=ui_action` token rules as generative UI actions (`sale_session_id` bound; no amounts). The action MUST also carry a server-authored `conversation_id` equal to the JWT claim for posting through `POST /api/v1/lumo/actions`. Inicio `sale_confirmed@1` MUST NOT emit this action. Eligibility for attaching the action is defined by `memoria-timeline` and MUST be evaluated on the server at read time.

#### Scenario: Memoria void request token binds the session
- **WHEN** an eligible Memoria `sale_confirmed` event includes `sale.void.request@1`
- **THEN** the token MUST include that sale’s `sale_session_id` and MUST NOT include amounts or a client-invented status

### Requirement: Payment action tokens bind sale_revision and go stale after remove
`sale.pay.cash@1`, `sale.pay.card@1`, and `sale.pay.transfer@1` tokens composed for a `ready_to_charge` session MUST include an integer `sale_revision` JWT claim equal to the session's persisted `sales.sale_sessions.sale_revision` in addition to `sale_session_id`, and MUST still omit payment amounts from the token. After `sale.remove_item@1` persists an advanced `sale_revision` on that session, posting a payment action whose token `sale_revision` does not match the locked session column MUST return reason `ui_action_stale`, text `Esta acción ya no aplica a la venta en curso.`, and empty `ui`, and MUST NOT call `CommitSaleSession`, insert a `Payment`, or write transition audit/outbox/idempotency for that attempt. Exact same-key replay of a previously completed commit MUST still return the stored body before revision checks. Fresh payment actions from a post-remove `sale_summary@1` MUST carry the new persisted `sale_revision`. Clients MUST NOT mint or override this claim.

#### Scenario: Pre-remove cash tap is stale
- **WHEN** pay tokens were composed for a two-item ready_to_charge sale, one item is removed, and the old `sale.pay.cash@1` token is posted with a new idempotency key
- **THEN** the reason MUST be `ui_action_stale`, no `Payment` MUST be written, and the session MUST remain `ready_to_charge` with the post-remove total

#### Scenario: Post-remove cash tap with fresh token commits
- **WHEN** the merchant posts a newly composed `sale.pay.cash@1` whose `sale_revision` matches the session after remove
- **THEN** `CommitSaleSession` MUST run for that session and MUST charge the server-derived remaining total

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
