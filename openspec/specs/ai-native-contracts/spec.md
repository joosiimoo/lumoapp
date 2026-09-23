## Purpose

AI-native ports for Build A: LLM provider, orchestrator, tool registry, policy engine, outcome engine, and split generative UI (backend compose, Flutter render). Registered product tools are `catalog.resolve_product@1`, `sale.start@1`, `sale.add_item@1`, `sale.totalize@1`, `sale.commit@1`, `operational_day.summary@1`, `closing.submit_cash_count@1`, `closing.prepare@1`, and `closing.confirm@1`. Registered UI contracts are `sale_item_added@1`, `sale_summary@1`, `sale_confirmed@1`, `operational_day_summary@1`, `daily_close_preparation@1`, and `daily_close_confirmed@1`. `closing.reopen`, export, and payment-resolve tools remain unregistered.
## Requirements
### Requirement: LLMProvider port
The system MUST define an `LLMProvider` port with `interpret(message, context, allowed_tools) -> AgentDecision`, `compose(result, ui_contracts) -> AgentResponse`, and `health() -> ProviderStatus`. The port MUST NOT expose database sessions, repositories, or credentials. A fake or null adapter MUST exist for tests and local boot without a vendor SDK.

#### Scenario: Port has no persistence access
- **WHEN** the `LLMProvider` interface is inspected
- **THEN** it MUST NOT accept a database session, repository, or connection string

#### Scenario: Fake provider boots
- **WHEN** the API starts with LLM disabled or unset
- **THEN** `health()` MUST report a non-ready or fake status and the process MUST still serve health and structured APIs

### Requirement: LLM cannot mutate domain state
No `LLMProvider` implementation MUST write to PostgreSQL, invoke repositories, or call unregistered tools. Interpretation output MUST be schema-validated before any other component consumes it. Invalid model output MUST NOT reach domain services.

#### Scenario: Invalid decision discarded
- **WHEN** the provider returns a payload that fails the `AgentDecision` schema
- **THEN** the orchestrator MUST NOT invoke a tool and MUST NOT persist domain state

### Requirement: Single LumoOrchestrator
Build A MUST expose exactly one `LumoOrchestrator` port. The orchestrator MAY load context, request interpretation, select a registered tool, request a policy decision, invoke an application use case, and compose a response. It MUST NOT open business transactions, access the ORM, or bypass `ToolRegistry` and `PolicyEngine`.

#### Scenario: Unregistered tool blocked
- **WHEN** an `AgentDecision` names a tool that is not in `ToolRegistry`
- **THEN** the orchestrator MUST NOT execute it and MUST return a non-mutating clarification or denial

#### Scenario: No second agent runtime
- **WHEN** the source tree is inspected
- **THEN** it MUST contain a single orchestrator composition root and MUST NOT define independent agent runtimes

### Requirement: ToolRegistry contract
`ToolRegistry` MUST be a closed catalog of versioned tools. Each registration MUST declare id, version, input schema, output schema, required permission, policy id, idempotency needs, and side-effect class. The registry MUST include the product tools `catalog.resolve_product@1`, `sale.start@1`, `sale.add_item@1`, `sale.totalize@1`, `sale.commit@1`, `operational_day.summary@1`, `closing.submit_cash_count@1`, `closing.prepare@1`, and `closing.confirm@1`. `operational_day.summary@1` MUST be `side_effect=read`, `requires_idempotency=false`, and permission `sale.create`. `closing.submit_cash_count@1` MUST be `side_effect=write`, `requires_idempotency=true`, permission `closing.submit_cash_count`, policy `CLOSE-001`, and its input schema MUST have `amount` as its only property. `closing.prepare@1` MUST be `side_effect=read`, `requires_idempotency=false`, permission `closing.submit_cash_count`, policy `CLOSE-002`, and an empty input object. `closing.confirm@1` MUST be `side_effect=write`, `requires_idempotency=true`, permission `closing.confirm`, policy `CLOSE-003`, and its input schema MUST have `confirmation_token` as its only property. `closing.reopen`, export, payment-resolve, and `operational_day.get` tools MUST remain unregistered.

#### Scenario: Conversational sale tools registered
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `catalog.resolve_product@1`, `sale.start@1`, `sale.add_item@1`, `sale.totalize@1`, `sale.commit@1`, and `operational_day.summary@1` as registered

#### Scenario: Cash count and preparation tools registered
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `closing.submit_cash_count@1` as a write tool requiring idempotency and `closing.prepare@1` as a read tool that does not require idempotency

#### Scenario: Close confirm tool registered
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `closing.confirm@1` as a write tool requiring idempotency, with permission `closing.confirm`, policy `CLOSE-003`, and an input schema whose only property is `confirmation_token`

#### Scenario: Unknown tool lookup
- **WHEN** a caller asks the registry for `closing.reopen@1` or `operational_day.get@1`
- **THEN** the registry MUST report the tool as unregistered

### Requirement: PolicyEngine contract
`PolicyEngine` MUST evaluate a proposed action and return `allow`, `deny`, `clarify`, or `confirm` with rule ids, a reason code, and evidence requirements. Evaluation order MUST be security, integrity, tenant and permissions, workflow gates, business rules, catalog and pricing, confidence, then user experience. Registered policies MUST include `SEC-001`, `SEC-002`, `SEC-003`, `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, `SALE-001`, `SALE-002`, `SALE-003`, `SALE-004`, `SALE-005`, `PAY-001`, `DAY-001`, `CLOSE-001`, `CLOSE-002`, and `CLOSE-003`. `SALE-005` MUST allow `sale.add_item@1` with `source_type=free_concept` only when resolution is `none`, the concept is non-empty, quantity is positive, the unit is supported, and `unit_price` is an explicit positive business-currency amount with at most two decimal places grounded in user text. For `gram` and `kilogram`, `SALE-005` MUST also require an explicit per-kilogram basis and MUST clarify with reason `price_basis_required` when that basis is missing. `SALE-005` MUST clarify when that price or quantity is missing and MUST deny a non-positive price. `SALE-005` MUST NOT allow a free concept when resolution is `unique`, `ambiguous`, or an inactive name collision. A unique catalog match whose grounded user amount differs from `Product.current_price` MUST clarify under `CAT-001` with reason `catalog_price_mismatch` and MUST NOT be allowed or refused through `SALE-005`. `DAY-001` MUST allow `operational_day.summary@1` only as a registered read and MUST NOT treat model-supplied totals or dates as operational truth. `CLOSE-001` MUST allow `closing.submit_cash_count@1` only for a server-parsed non-negative amount when an `OperationalDay` exists for today's business date, MUST clarify with reason `operational_day_not_started` when no such day exists, and MUST NOT treat model-supplied expected cash, counted cash, difference, status, `operational_day_id`, or business date as operational truth. `CLOSE-002` MUST allow `closing.prepare@1` only as a registered read with the same prohibition on model-supplied values. `CLOSE-003` MUST deny `closing.confirm@1` when arguments include `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, `operational_day_id`, `closing_snapshot_id`, `business_date`, `closed_at`, `sale_count`, `gross_sales_total`, `cash_total`, `card_total`, `transfer_total`, `currency`, `actor_id`, or `cash_count_id`. The confirm workflow under the day lock remains the authority for whether the token matches current state.

#### Scenario: Deny unregistered tool
- **WHEN** policy evaluates a request to execute an unregistered tool
- **THEN** the decision MUST be `deny` under `SEC-002`

#### Scenario: Decision is auditable
- **WHEN** the engine returns a decision
- **THEN** the result MUST include rule ids and a reason code suitable for `AuditEvent`

#### Scenario: Catalog product must be active
- **WHEN** policy evaluates add-item for an inactive product
- **THEN** the decision MUST NOT be `allow` under `CAT-001`

#### Scenario: Unresolved concept without a price is not allowed
- **WHEN** policy evaluates add-item and resolution is `none` and unit price is missing
- **THEN** the decision MUST NOT be `allow`

#### Scenario: Complete free concept is allowed
- **WHEN** policy evaluates add-item with resolution `none`, `source_type=free_concept`, quantity `2`, unit `package`, and unit price `18.00` MXN
- **THEN** the decision MUST be `allow` under `SALE-005`

#### Scenario: Mass free concept without a basis is not allowed
- **WHEN** policy evaluates add-item with resolution `none`, unit `gram`, unit price `40.00` MXN, and no per-kilogram basis
- **THEN** the decision MUST be `clarify` with reason `price_basis_required` and MUST NOT be `allow` under `SALE-005`

#### Scenario: Catalog price mismatch stays on CAT-001
- **WHEN** policy evaluates add-item with resolution `unique` and a grounded price that differs from `Product.current_price`
- **THEN** the decision MUST be `clarify` under `CAT-001` with reason `catalog_price_mismatch` and MUST NOT be a `SALE-005` decision

#### Scenario: Ambiguous match is not a free concept
- **WHEN** policy evaluates add-item and resolution is `ambiguous`
- **THEN** the decision MUST NOT be `allow` under `SALE-005`

#### Scenario: Ready_to_charge blocks add-item
- **WHEN** policy evaluates add-item for a session whose status is `ready_to_charge`
- **THEN** the decision MUST NOT be `allow` under `SALE-002`

#### Scenario: SALE-003 gates the transition only
- **WHEN** policy evaluates totalize for an `open` session with no items
- **THEN** the decision MUST NOT be `allow` under `SALE-003`

#### Scenario: SALE-003 allows ready_to_charge read-back
- **WHEN** policy evaluates totalize for a session whose status is already `ready_to_charge`
- **THEN** the decision MUST NOT treat that request as a forbidden transition under `SALE-003`

#### Scenario: SALE-004 gates commit to ready_to_charge
- **WHEN** policy evaluates commit for an `open` session
- **THEN** the decision MUST NOT be `allow` under `SALE-004`

#### Scenario: PAY-001 requires an explicit method
- **WHEN** policy evaluates commit without a closed-enum `payment_method`
- **THEN** the decision MUST NOT be `allow` under `PAY-001` and MUST NOT infer `cash`

#### Scenario: DAY-001 does not accept client totals
- **WHEN** policy evaluates `operational_day.summary@1` and the model arguments include a sale count or a total
- **THEN** the decision MUST NOT persist those arguments and the summary MUST still be computed from confirmed rows under `DAY-001`

#### Scenario: CLOSE-001 clarifies when the day has not started
- **WHEN** policy evaluates `closing.submit_cash_count@1` and no `OperationalDay` exists for today's business date
- **THEN** the decision MUST NOT be `allow`, the reason code MUST be `operational_day_not_started`, and no cash count or operational day MUST be persisted

#### Scenario: CLOSE-001 rejects model-supplied cash figures
- **WHEN** policy evaluates `closing.submit_cash_count@1` with model arguments carrying `expected_cash`, `cash_difference`, or `operational_day_id`
- **THEN** those arguments MUST NOT be persisted and the backend MUST still compute expected cash and the difference from persisted rows under `CLOSE-001`

#### Scenario: CLOSE-002 keeps preparation a read
- **WHEN** policy evaluates `closing.prepare@1`
- **THEN** the decision MUST allow it only as a registered read and MUST NOT authorize any write, status change, or close confirmation

#### Scenario: CLOSE-003 rejects model-supplied close figures
- **WHEN** policy evaluates `closing.confirm@1` with model arguments carrying `counted_cash`, `closing_snapshot_id`, or `closed_at`
- **THEN** the decision MUST be `deny` under `CLOSE-003` and no snapshot MUST be written

### Requirement: OutcomeEngine contract
`OutcomeEngine` MUST accept versioned outcome definitions and evaluate gates deterministically from confirmed state. The LLM MUST NOT overwrite a gate result. The engine port MUST exist with an empty definition registry. This change MUST NOT register `daily_sales_operations_ready@1` or `daily_close_ready@1`, and cash-count, preparation, or close-confirmation activity MUST NOT mark any outcome ready.

#### Scenario: Unknown outcome fails closed
- **WHEN** a caller evaluates `daily_close_ready@1` before it is registered
- **THEN** the engine MUST NOT mark the outcome ready

#### Scenario: Model text cannot complete a gate
- **WHEN** a model response claims an outcome is complete
- **THEN** the engine MUST ignore that claim and use only registered gate functions

#### Scenario: Balanced cash does not complete an outcome
- **WHEN** a balanced cash count is recorded for today's OperationalDay
- **THEN** the definition registry MUST remain empty, no OutcomeRun MUST be created, and no gate MUST report ready

#### Scenario: Confirmed close does not create an outcome
- **WHEN** `closing.confirm@1` commits a snapshot
- **THEN** no OutcomeRun MUST be created and `daily_close_ready@1` MUST remain unregistered

### Requirement: Backend generative UI contracts
The backend MUST expose `GenerativeUIRegistry` and `GenerativeUIComposer` ports. The shared versioned contract is `component`, `version`, `data`, `actions`, and `fallback_text`. Actions MUST carry opaque `action_id`, optional `option_id`, `context_token`, and an idempotency key. `GenerativeUIRegistry` MUST include `sale_item_added@1`, `sale_summary@1`, `sale_confirmed@1`, `operational_day_summary@1`, `daily_close_preparation@1`, and `daily_close_confirmed@1`, and MUST NOT include `closing_ready_card`, `cash_difference_card`, `daily_summary_card`, `sale_confirmed_card`, or `sale_completed`. `GenerativeUIComposer` MUST validate against the registry and emit only registered versioned contracts. The backend MUST NOT render widgets. Component versions MUST remain `1`. `actions` MUST remain optional: an empty array is valid. `sale_summary@1` MUST emit `sale.pay.cash@1`, `sale.pay.card@1`, and `sale.pay.transfer@1` only while the session is `ready_to_charge`. `sale_confirmed@1`, `sale_item_added@1`, `operational_day_summary@1`, and `daily_close_confirmed@1` MUST keep `actions` empty. `daily_close_preparation@1` MUST emit `closing.request@1` only for a counted open day with `cash_status` `balanced`, `short`, or `over` and a null confirmation token, and MUST emit only `closing.confirm@1` after `request_close` issues a token. It MUST emit no actions when `cash_status` is `not_counted`, when no day exists, or when no current cash count exists. The close confirmation token MUST be the `closing.confirm@1` action `context_token` and MUST also be copied to `data.confirmation_token`. Those two strings MUST be equal. `fallback_text` MUST remain present and MUST NOT contain the token.

#### Scenario: Closed registry on backend
- **WHEN** the composer is asked to emit an unregistered component
- **THEN** the backend MUST refuse to include it in the response

#### Scenario: Backend does not render
- **WHEN** a registered contract is composed
- **THEN** the API MUST return the declarative payload and MUST NOT return HTML, Flutter widgets, or executable UI code

#### Scenario: sale_item_added registered
- **WHEN** the registry is queried for component `sale_item_added` version `1`
- **THEN** it MUST be present and its `actions` MUST be empty

#### Scenario: sale_summary registered
- **WHEN** the registry is queried for component `sale_summary` version `1` composed for `ready_to_charge`
- **THEN** it MUST be present at version `1` and its `actions` MUST be the three payment action ids

#### Scenario: sale_confirmed registered
- **WHEN** the registry is queried for component `sale_confirmed` version `1`
- **THEN** it MUST be present and its `actions` MUST be empty

#### Scenario: operational_day_summary registered
- **WHEN** the registry is queried for component `operational_day_summary` version `1`
- **THEN** it MUST be present and its `actions` MUST be empty

#### Scenario: daily_close_preparation registered
- **WHEN** the registry is queried for component `daily_close_preparation` version `1`
- **THEN** it MUST be present, and `closing_ready_card` and `cash_difference_card` MUST be absent

#### Scenario: daily_close_confirmed registered
- **WHEN** the registry is queried for component `daily_close_confirmed` version `1`
- **THEN** it MUST be present and its `actions` MUST be empty

#### Scenario: Confirm token is not duplicated as a second authority
- **WHEN** a confirmable preparation contract is composed
- **THEN** `data.confirmation_token` and the `closing.confirm@1` `context_token` MUST be the same server-issued JWT

### Requirement: Flutter GenerativeUIRenderer
Flutter MUST own `GenerativeUIRenderer`. It is solely responsible for rendering backend-emitted contracts. The renderer MUST reject unknown component names or versions and show `fallback_text`. It MUST NOT execute an action whose id is not in the closed five-id catalog. An unknown action id on a known component MUST NOT replace that component with `fallback_text` and MUST NOT render a button. Flutter MUST NOT decide that a payment or close action is legal when the server omitted it.

#### Scenario: Unknown component rejected
- **WHEN** a payload names a component that is not registered in the Flutter renderer
- **THEN** Flutter MUST render `fallback_text` and MUST NOT execute any action from that payload

#### Scenario: Unknown action is ignored
- **WHEN** `sale_summary` version `1` includes an action id outside the closed catalog
- **THEN** Flutter MUST still render the summary card and MUST NOT execute that action

### Requirement: sale.add_item source mode
`sale.add_item@1` MUST remain the only add-item tool. Its input schema MUST require `source_type`. `catalog` MUST require `product_id` and MUST NOT accept a client unit price as the stored price. `free_concept` MUST require `concept_name` and `unit_price` and MUST NOT require `product_id`. `sale.add_free_item@1` MUST remain unregistered. Generative UI actions MUST NOT gain a save-to-catalog action.

#### Scenario: Free-item tool stays unregistered
- **WHEN** a caller asks the registry for `sale.add_free_item@1`
- **THEN** the registry MUST report the tool as unregistered

#### Scenario: No catalog-save action
- **WHEN** `sale_item_added@1` is emitted for a free-concept line
- **THEN** `actions` MUST be empty

