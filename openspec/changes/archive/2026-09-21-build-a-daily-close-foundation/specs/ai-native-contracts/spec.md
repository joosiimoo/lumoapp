## MODIFIED Requirements

### Requirement: ToolRegistry contract
`ToolRegistry` MUST be a closed catalog of versioned tools. Each registration MUST declare id, version, input schema, output schema, required permission, policy id, idempotency needs, and side-effect class. The registry MUST include the product tools `catalog.resolve_product@1`, `sale.start@1`, `sale.add_item@1`, `sale.totalize@1`, `sale.commit@1`, `operational_day.summary@1`, `closing.submit_cash_count@1`, and `closing.prepare@1`. `operational_day.summary@1` MUST be `side_effect=read`, `requires_idempotency=false`, and permission `sale.create`. `closing.submit_cash_count@1` MUST be `side_effect=write`, `requires_idempotency=true`, permission `closing.submit_cash_count`, policy `CLOSE-001`, and its input schema MUST have `amount` as its only property. `closing.prepare@1` MUST be `side_effect=read`, `requires_idempotency=false`, permission `closing.submit_cash_count`, policy `CLOSE-002`, and an empty input object. `closing.confirm`, `closing.reopen`, export, payment-resolve, and `operational_day.get` tools MUST remain unregistered.

#### Scenario: Conversational sale tools registered
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `catalog.resolve_product@1`, `sale.start@1`, `sale.add_item@1`, `sale.totalize@1`, `sale.commit@1`, and `operational_day.summary@1` as registered

#### Scenario: Cash count and preparation tools registered
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `closing.submit_cash_count@1` as a write tool requiring idempotency and `closing.prepare@1` as a read tool that does not require idempotency

#### Scenario: Unknown tool lookup
- **WHEN** a caller asks the registry for `closing.confirm@1`, `closing.reopen@1`, or `operational_day.get@1`
- **THEN** the registry MUST report the tool as unregistered

### Requirement: PolicyEngine contract
`PolicyEngine` MUST evaluate a proposed action and return `allow`, `deny`, `clarify`, or `confirm` with rule ids, a reason code, and evidence requirements. Evaluation order MUST be security, integrity, tenant and permissions, workflow gates, business rules, catalog and pricing, confidence, then user experience. Registered policies MUST include `SEC-001`, `SEC-002`, `SEC-003`, `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, `SALE-001`, `SALE-002`, `SALE-003`, `SALE-004`, `PAY-001`, `DAY-001`, `CLOSE-001`, and `CLOSE-002`. `DAY-001` MUST allow `operational_day.summary@1` only as a registered read and MUST NOT treat model-supplied totals or dates as operational truth. `CLOSE-001` MUST allow `closing.submit_cash_count@1` only for a server-parsed non-negative amount when an `OperationalDay` exists for today's business date, MUST clarify with reason `operational_day_not_started` when no such day exists, and MUST NOT treat model-supplied expected cash, counted cash, difference, status, `operational_day_id`, or business date as operational truth. `CLOSE-002` MUST allow `closing.prepare@1` only as a registered read with the same prohibition on model-supplied values.

#### Scenario: Deny unregistered tool
- **WHEN** policy evaluates a request to execute an unregistered tool
- **THEN** the decision MUST be `deny` under `SEC-002`

#### Scenario: Decision is auditable
- **WHEN** the engine returns a decision
- **THEN** the result MUST include rule ids and a reason code suitable for `AuditEvent`

#### Scenario: Catalog product must be active
- **WHEN** policy evaluates add-item for an inactive or unresolved product
- **THEN** the decision MUST NOT be `allow` under `CAT-001`

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

### Requirement: Backend generative UI contracts
The backend MUST expose `GenerativeUIRegistry` and `GenerativeUIComposer` ports. The shared versioned contract is `component`, `version`, `data`, `actions`, and `fallback_text`. Actions MUST carry opaque `action_id`, optional `option_id`, `context_token`, and an idempotency key. `GenerativeUIRegistry` MUST include `sale_item_added@1`, `sale_summary@1`, `sale_confirmed@1`, `operational_day_summary@1`, and `daily_close_preparation@1`, and MUST NOT include `closing_ready_card`, `cash_difference_card`, `daily_summary_card`, `sale_confirmed_card`, or `sale_completed`. `GenerativeUIComposer` MUST validate against the registry and emit only registered versioned contracts. The backend MUST NOT render widgets.

#### Scenario: Closed registry on backend
- **WHEN** the composer is asked to emit an unregistered component
- **THEN** the backend MUST refuse to include it in the response

#### Scenario: Backend does not render
- **WHEN** a registered contract is composed
- **THEN** the API MUST return the declarative payload and MUST NOT return HTML, Flutter widgets, or executable UI code

#### Scenario: sale_item_added registered
- **WHEN** the registry is queried for component `sale_item_added` version `1`
- **THEN** it MUST be present

#### Scenario: sale_summary registered
- **WHEN** the registry is queried for component `sale_summary` version `1`
- **THEN** it MUST be present

#### Scenario: sale_confirmed registered
- **WHEN** the registry is queried for component `sale_confirmed` version `1`
- **THEN** it MUST be present

#### Scenario: operational_day_summary registered
- **WHEN** the registry is queried for component `operational_day_summary` version `1`
- **THEN** it MUST be present

#### Scenario: daily_close_preparation registered
- **WHEN** the registry is queried for component `daily_close_preparation` version `1`
- **THEN** it MUST be present, and `closing_ready_card` and `cash_difference_card` MUST be absent

### Requirement: OutcomeEngine contract
`OutcomeEngine` MUST accept versioned outcome definitions and evaluate gates deterministically from confirmed state. The LLM MUST NOT overwrite a gate result. The engine port MUST exist with an empty definition registry. This change MUST NOT register `daily_sales_operations_ready@1` or `daily_close_ready@1`, and cash-count or preparation activity MUST NOT mark any outcome ready.

#### Scenario: Unknown outcome fails closed
- **WHEN** a caller evaluates `daily_close_ready@1` before it is registered
- **THEN** the engine MUST NOT mark the outcome ready

#### Scenario: Model text cannot complete a gate
- **WHEN** a model response claims an outcome is complete
- **THEN** the engine MUST ignore that claim and use only registered gate functions

#### Scenario: Balanced cash does not complete an outcome
- **WHEN** a balanced cash count is recorded for today's OperationalDay
- **THEN** the definition registry MUST remain empty, no OutcomeRun MUST be created, and no gate MUST report ready
