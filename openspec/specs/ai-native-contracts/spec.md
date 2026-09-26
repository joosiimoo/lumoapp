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
`PolicyEngine` MUST evaluate a proposed action and return `allow`, `deny`, `clarify`, or `confirm` with rule ids, a reason code, and evidence requirements. Evaluation order MUST be security, integrity, tenant and permissions, workflow gates, business rules, catalog and pricing, confidence, then user experience. Registered policies MUST include `SEC-001`, `SEC-002`, `SEC-003`, `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, `SALE-001`, `SALE-002`, `SALE-003`, `SALE-004`, `SALE-005`, `PAY-001`, `DAY-001`, `CLOSE-001`, `CLOSE-002`, and `CLOSE-003`. `SALE-005` MUST allow `sale.add_item@1` with `source_type=free_concept` only when resolution is `none`, the concept is non-empty, quantity is positive, the unit is supported, and `unit_price` is an explicit positive business-currency amount with at most two decimal places grounded in user text. For `gram` and `kilogram`, `SALE-005` MUST also require an explicit per-kilogram basis and MUST clarify with reason `price_basis_required` when that basis is missing. `SALE-005` MUST clarify when that price or quantity is missing and MUST deny a non-positive price. `SALE-005` MUST NOT allow a free concept when resolution is `unique`, `ambiguous`, or an inactive name collision. A unique catalog match whose grounded user amount differs from `Product.current_price` MUST clarify under `CAT-001` with reason `catalog_price_override_reason_required` and MUST NOT be allowed or refused through `SALE-005`. A completed catalog override MUST be allowed under `SALE-001` and `CAT-001` with reason `catalog_price_override` only after the server re-reads `Product.current_price` and accepts a merchant reason. No new policy id is added. `DAY-001` MUST allow `operational_day.summary@1` only as a registered read and MUST NOT treat model-supplied totals or dates as operational truth. `CLOSE-001` MUST allow `closing.submit_cash_count@1` only for a server-parsed non-negative amount when an `OperationalDay` exists for today's business date, MUST clarify with reason `operational_day_not_started` when no such day exists, and MUST NOT treat model-supplied expected cash, counted cash, difference, status, `operational_day_id`, or business date as operational truth. `CLOSE-002` MUST allow `closing.prepare@1` only as a registered read with the same prohibition on model-supplied values. `CLOSE-003` MUST deny `closing.confirm@1` when arguments include `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, `operational_day_id`, `closing_snapshot_id`, `business_date`, `closed_at`, `sale_count`, `gross_sales_total`, `cash_total`, `card_total`, `transfer_total`, `currency`, `actor_id`, or `cash_count_id`. The confirm workflow under the day lock remains the authority for whether the token matches current state.

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

#### Scenario: Catalog price difference asks for a reason
- **WHEN** policy evaluates add-item with resolution `unique` and a grounded price that differs from `Product.current_price` before a merchant reason exists
- **THEN** the decision MUST be `clarify` under `CAT-001` with reason `catalog_price_override_reason_required` and MUST NOT be a `SALE-005` decision

#### Scenario: Completed override is allowed on the add-item tool
- **WHEN** policy evaluates a catalog `sale.add_item@1` whose re-read price differs from the grounded override and whose merchant reason is valid
- **THEN** the decision MUST be `allow` with reason `catalog_price_override` and rule ids including `SALE-001` and `CAT-001`

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
`OutcomeEngine` MUST accept versioned outcome definitions and evaluate gates deterministically from confirmed state. The LLM MUST NOT overwrite a gate result. The engine port MUST register `daily_close_ready@1` as specified by `daily-close-outcome` and MUST NOT register `daily_sales_operations_ready@1`. `evaluate` MUST ignore model text. An unknown outcome id MUST return the evaluation verdict `not_ready` and MUST NOT write. `not_ready` MUST NOT be an `OutcomeRun.status`, a persisted reason, or a value of the `operations.outcome_runs` status check. Persisted statuses MUST remain `in_progress`, `ready`, and `completed`. Evaluating `daily_close_ready@1` MUST return one of those three predicate statuses and MUST NOT insert or update an OutcomeRun. Cash-count, preparation, and close-confirmation activity MUST change an OutcomeRun only through the write hooks in `daily-close-outcome`, not through `evaluate`.

#### Scenario: Unknown outcome fails closed
- **WHEN** a caller evaluates `daily_sales_operations_ready@1`
- **THEN** the engine MUST return the evaluation verdict `not_ready`, MUST NOT write an OutcomeRun, and MUST NOT store `not_ready` as a status or reason

#### Scenario: Model text cannot complete a gate
- **WHEN** a model response claims an outcome is complete
- **THEN** the engine MUST ignore that claim and use only the registered gate function

#### Scenario: Balanced cash is ready only through the write hook
- **WHEN** a balanced cash count is recorded for today's OperationalDay
- **THEN** the persisted OutcomeRun MUST be `ready` because the cash-count transaction ran the write hook, and a later `evaluate` call MUST NOT insert a second row

#### Scenario: Confirmed close completes the registered outcome
- **WHEN** `closing.confirm@1` commits a snapshot
- **THEN** the persisted OutcomeRun MUST be `completed` and `daily_close_ready.execute@1` MUST remain unregistered

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
`sale.add_item@1` MUST remain the only add-item tool and MUST remain version `1`. Its input schema MUST require `source_type`. `catalog` MUST require `product_id`. Without `price_override`, catalog mode MUST NOT accept a client unit price as the stored price. With `price_override`, the object MUST contain `unit_price` `{amount, currency}` and `reason`. The server MUST re-read `Product.current_price` and MUST persist that client amount only when `catalog-price-override` accepts it. `free_concept` MUST require `concept_name` and `unit_price` and MUST NOT require `product_id`. `sale.override_price@1`, `sale.add_override_item@1`, and `sale.add_free_item@1` MUST remain unregistered. `sale_item_added@1`, `sale_summary@1`, and `sale_confirmed@1` MUST remain version `1`. Generative UI actions MUST NOT gain a save-to-catalog action.

#### Scenario: Free-item tool stays unregistered
- **WHEN** a caller asks the registry for `sale.add_free_item@1`
- **THEN** the registry MUST report the tool as unregistered

#### Scenario: Override tools stay unregistered
- **WHEN** a caller asks the registry for `sale.override_price@1` or `sale.add_override_item@1`
- **THEN** the registry MUST report each tool as unregistered

#### Scenario: No catalog-save action
- **WHEN** `sale_item_added@1` is emitted for a free-concept line or a catalog override
- **THEN** `actions` MUST be empty

### Requirement: Override caption stays on version 1
`GenerativeUIRegistry` MUST NOT register version `2` of `sale_item_added`, `sale_summary`, or `sale_confirmed` for this change. An override payload MAY include `catalog_unit_price` on version `1`. Existing required fields MUST keep their meaning. The composer MUST still refuse an unregistered component or version.

#### Scenario: Version 2 is not registered
- **WHEN** the registry is queried for `sale_item_added` version `2`
- **THEN** the component version MUST be absent

### Requirement: Daily sales export is not a tool or a model artifact
The daily sales file MUST be produced only by the deterministic HTTP read in `daily-sales-export`. `ToolRegistry` MUST NOT register `operational_day.export_sales@1` or any other export tool. `UiActionRegistry` MUST NOT register a download action. `GenerativeUIRegistry` MUST NOT register `export_ready_card`. No `LLMProvider` MUST generate export bytes, column names, product names, prices, reasons, quantities, or totals. The export query MUST NOT run inside the orchestrator.

#### Scenario: Export tool stays unregistered
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `operational_day.export_sales@1` as unregistered and the existing tool list MUST be unchanged

#### Scenario: Model output is not a file
- **WHEN** an interpreter returns text that looks like CSV or a workbook
- **THEN** that text MUST NOT be stored or returned as the sales export

### Requirement: Next Best Action tool and component are registered
`ToolRegistry` MUST include `operational_day.next_best_action@1` as specified by `next-best-action`. `PolicyEngine` MUST include `NBA-001`. `GenerativeUIRegistry` MUST include `next_best_action` version `1`. `UiActionRegistry` MUST NOT gain an action id. `closing.reopen@1`, `operational_day.export_sales@1`, `payment.resolve`, and `daily_close_ready.execute@1` MUST remain unregistered. The outcome definition registry MUST contain `daily_close_ready@1`. Projecting `outcome_type=daily_close_ready` MUST NOT by itself insert an OutcomeRun.

#### Scenario: Boot catalog gains the read tool and the card
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `operational_day.next_best_action@1`, `GenerativeUIRegistry` MUST report `next_best_action` version `1`, the outcome registry MUST report `daily_close_ready@1`, and `UiActionRegistry` MUST still contain exactly `sale.pay.cash@1`, `sale.pay.card@1`, `sale.pay.transfer@1`, `closing.request@1`, and `closing.confirm@1`

#### Scenario: A projection does not create an outcome
- **WHEN** a Next Best Action is projected for an open day that already has an OutcomeRun
- **THEN** no additional OutcomeRun row MUST be created

### Requirement: Assistant output must not claim unverified completeness
The server MUST NOT emit new or changed assistant text, UI fallback text, or tool output that states that all of today's sales were captured, that no sale is missing, that 100% of the operation was registered, or that the day's operation is complete, unless a source-coverage status of `declared_complete` exists. Build A MUST NOT produce `declared_complete`. Existing day-summary text and confirmed-close text MUST stay unchanged. Wording that remains allowed is limited to operations registered in Lumo, including "Según las ventas registradas en Lumo…", "En las operaciones registradas hoy…", "En las operaciones registradas en Lumo…", and "El cierre registrado en Lumo…". `ToolRegistry` MUST NOT register `memory.query_events` or a source-coverage tool. `ToolRegistry` MUST register `memory.business_facts@1` as specified by `factual-memory-tool`. `GenerativeUIRegistry` MUST NOT register a memory or coverage component. `UiActionRegistry` MUST keep exactly its current action ids.

#### Scenario: Summary and close copy stay factual
- **WHEN** a day summary and a confirmed close are rendered after this change
- **THEN** the summary fallback MUST still begin with `Hoy` and the close fallback MUST still begin with `Cierre confirmado`, and neither string MUST claim that every real-world sale was captured

#### Scenario: No memory search or coverage tool is registered
- **WHEN** `ToolRegistry` is queried for `memory.query_events` and for a source-coverage tool
- **THEN** both MUST be unregistered

#### Scenario: The factual read tool is registered without a memory card
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `memory.business_facts@1` as a read tool that does not require idempotency, and `GenerativeUIRegistry` MUST NOT contain a memory component

### Requirement: MEM-001 guards the factual memory tool
`PolicyEngine` MUST include `MEM-001`. For `memory.business_facts@1`, `MEM-001` MUST allow only the closed argument shapes in `factual-memory-tool` and MUST deny every other shape with reason `factual_memory_arguments_denied`. The policy MUST NOT grant a write, an idempotency reservation, or a tenant chosen by the model.

#### Scenario: Policy allows a resolved day query
- **WHEN** policy evaluates `memory.business_facts@1` with `query_type` `day_summary` and a `business_date`
- **THEN** the decision MUST be `allow` with rule id `MEM-001`

#### Scenario: Policy denies a tenant argument
- **WHEN** policy evaluates `memory.business_facts@1` with a `business_id` argument
- **THEN** the decision MUST be `deny` with reason `factual_memory_arguments_denied`
