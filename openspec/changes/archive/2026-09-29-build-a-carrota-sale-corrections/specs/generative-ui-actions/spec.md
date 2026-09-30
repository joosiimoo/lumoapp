## MODIFIED Requirements

### Requirement: Closed generative UI action catalog
The backend MUST expose a closed `UiActionRegistry` separate from `ToolRegistry`. The registered action ids MUST be `sale.pay.cash@1`, `sale.pay.card@1`, `sale.pay.transfer@1`, `sale.remove_item@1`, `sale.void.request@1`, `sale.void.confirm@1`, `closing.request@1`, and `closing.confirm@1`. Each id is versioned inside the string because `GenerativeUIAction` has no version field. `option_id` MUST be null except where a later requirement explicitly allows a null-only option. The registry MUST NOT include `payment.resolve`, a mixed-payment action, an undo-without-void action, a reopen action, or an inline cash-count action. `closing.confirm@1` as an action id MUST NOT be registered again as a tool.

#### Scenario: Boot catalog
- **WHEN** the application boots
- **THEN** `UiActionRegistry` MUST contain exactly those eight ids and `ToolRegistry` MUST remain a separate catalog

#### Scenario: Unknown action id
- **WHEN** a caller submits `action_id` `sale.pay.cheque@1`
- **THEN** the registry MUST report it as unregistered and no sale or close MUST be mutated

## ADDED Requirements

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
