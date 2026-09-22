## MODIFIED Requirements

### Requirement: ToolRegistry contract
`ToolRegistry` MUST be a closed catalog of versioned tools. Each registration MUST declare id, version, input schema, output schema, required permission, policy id, idempotency needs, and side-effect class. The registry MUST include the product tools `catalog.resolve_product@1`, `sale.start@1`, `sale.add_item@1`, `sale.totalize@1`, `sale.commit@1`, and `operational_day.summary@1`. `operational_day.summary@1` MUST be `side_effect=read`, `requires_idempotency=false`, and permission `sale.create`. Closing, export, payment-resolve, and `operational_day.get` tools MUST remain unregistered.

#### Scenario: Conversational sale tools registered
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `catalog.resolve_product@1`, `sale.start@1`, `sale.add_item@1`, `sale.totalize@1`, `sale.commit@1`, and `operational_day.summary@1` as registered

#### Scenario: Unknown tool lookup
- **WHEN** a caller asks the registry for `closing.confirm@1` or `operational_day.get@1`
- **THEN** the registry MUST report the tool as unregistered

### Requirement: PolicyEngine contract
`PolicyEngine` MUST evaluate a proposed action and return `allow`, `deny`, `clarify`, or `confirm` with rule ids, a reason code, and evidence requirements. Evaluation order MUST be security, integrity, tenant and permissions, workflow gates, business rules, catalog and pricing, confidence, then user experience. Registered policies MUST include `SEC-001`, `SEC-002`, `SEC-003`, `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, `SALE-001`, `SALE-002`, `SALE-003`, `SALE-004`, `PAY-001`, and `DAY-001`. `DAY-001` MUST allow `operational_day.summary@1` only as a registered read and MUST NOT treat model-supplied totals or dates as operational truth.

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

### Requirement: Backend generative UI contracts
The backend MUST expose `GenerativeUIRegistry` and `GenerativeUIComposer` ports. The shared versioned contract is `component`, `version`, `data`, `actions`, and `fallback_text`. Actions MUST carry opaque `action_id`, optional `option_id`, `context_token`, and an idempotency key. `GenerativeUIRegistry` MUST include `sale_item_added@1`, `sale_summary@1`, `sale_confirmed@1`, and `operational_day_summary@1` and MUST NOT include closing cards, `daily_summary_card`, `sale_confirmed_card`, or `sale_completed`. `GenerativeUIComposer` MUST validate against the registry and emit only registered versioned contracts. The backend MUST NOT render widgets.

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
