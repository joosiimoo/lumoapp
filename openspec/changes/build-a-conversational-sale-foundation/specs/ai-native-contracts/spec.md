## MODIFIED Requirements

### Requirement: ToolRegistry contract
`ToolRegistry` MUST be a closed catalog of versioned tools. Each registration MUST declare id, version, input schema, output schema, required permission, policy id, idempotency needs, and side-effect class. This change MUST register exactly the product tools `catalog.resolve_product@1`, `sale.start@1`, and `sale.add_item@1`. Closing, export, payment, and `sale.commit` tools MUST remain unregistered.

#### Scenario: Conversational sale tools registered
- **WHEN** the application boots after this change
- **THEN** `ToolRegistry` MUST report `catalog.resolve_product@1`, `sale.start@1`, and `sale.add_item@1` as registered

#### Scenario: Unknown tool lookup
- **WHEN** a caller asks the registry for `sale.commit@1`
- **THEN** the registry MUST report the tool as unregistered

### Requirement: PolicyEngine contract
`PolicyEngine` MUST evaluate a proposed action and return `allow`, `deny`, `clarify`, or `confirm` with rule ids, a reason code, and evidence requirements. Evaluation order MUST be security, integrity, tenant and permissions, workflow gates, business rules, catalog and pricing, confidence, then user experience. This change MUST keep `SEC-001`, `SEC-002`, and `SEC-003`, and MUST additionally register `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, and `SALE-001`.

#### Scenario: Deny unregistered tool
- **WHEN** policy evaluates a request to execute an unregistered tool
- **THEN** the decision MUST be `deny` under `SEC-002`

#### Scenario: Decision is auditable
- **WHEN** the engine returns a decision
- **THEN** the result MUST include rule ids and a reason code suitable for `AuditEvent`

#### Scenario: Catalog product must be active
- **WHEN** policy evaluates add-item for an inactive or unresolved product
- **THEN** the decision MUST NOT be `allow` under `CAT-001`

### Requirement: Backend generative UI contracts
The backend MUST expose `GenerativeUIRegistry` and `GenerativeUIComposer` ports. The shared versioned contract is `component`, `version`, `data`, `actions`, and `fallback_text`. Actions MUST carry opaque `action_id`, optional `option_id`, `context_token`, and an idempotency key. `GenerativeUIRegistry` MUST include `sale_item_added@1` and MUST NOT include payment, closing, or confirmed-sale cards in this change. `GenerativeUIComposer` MUST validate against the registry and emit only registered versioned contracts. The backend MUST NOT render widgets.

#### Scenario: Closed registry on backend
- **WHEN** the composer is asked to emit an unregistered component
- **THEN** the backend MUST refuse to include it in the response

#### Scenario: Backend does not render
- **WHEN** a registered contract is composed
- **THEN** the API MUST return the declarative payload and MUST NOT return HTML, Flutter widgets, or executable UI code

#### Scenario: sale_item_added registered
- **WHEN** the registry is queried for component `sale_item_added` version `1`
- **THEN** it MUST be present
