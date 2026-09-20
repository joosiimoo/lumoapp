## ADDED Requirements

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
`ToolRegistry` MUST be a closed catalog of versioned tools. Each registration MUST declare id, version, input schema, output schema, required permission, policy id, idempotency needs, and side-effect class. This change MUST ship the registry structure with zero product tools.

#### Scenario: Empty catalog is valid
- **WHEN** the foundation boots
- **THEN** `ToolRegistry` MUST start with no sales, catalog, closing, or export tools

#### Scenario: Unknown tool lookup
- **WHEN** a caller asks the registry for `sale.commit@1`
- **THEN** the registry MUST report the tool as unregistered

### Requirement: PolicyEngine contract
`PolicyEngine` MUST evaluate a proposed action and return `allow`, `deny`, `clarify`, or `confirm` with rule ids, a reason code, and evidence requirements. Evaluation order MUST be security, integrity, tenant and permissions, workflow gates, business rules, catalog and pricing, confidence, then user experience. This change MUST register only architectural policies `SEC-001` (LLM does not mutate), `SEC-002` (only registered tools/actions/widgets), and `SEC-003` (server revalidates arguments).

#### Scenario: Deny unregistered tool
- **WHEN** policy evaluates a request to execute an unregistered tool
- **THEN** the decision MUST be `deny` under `SEC-002`

#### Scenario: Decision is auditable
- **WHEN** the engine returns a decision
- **THEN** the result MUST include rule ids and a reason code suitable for `AuditEvent`

### Requirement: OutcomeEngine contract
`OutcomeEngine` MUST accept versioned outcome definitions and evaluate gates deterministically from confirmed state. The LLM MUST NOT overwrite a gate result. This change MUST provide the engine port and an empty definition registry.

#### Scenario: Unknown outcome fails closed
- **WHEN** a caller evaluates `daily_close_ready@1` before it is registered
- **THEN** the engine MUST NOT mark the outcome ready

#### Scenario: Model text cannot complete a gate
- **WHEN** a model response claims an outcome is complete
- **THEN** the engine MUST ignore that claim and use only registered gate functions

### Requirement: Backend generative UI contracts
The backend MUST expose `GenerativeUIRegistry` and `GenerativeUIComposer` ports. The shared versioned contract is `component`, `version`, `data`, `actions`, and `fallback_text`. Actions MUST carry opaque `action_id`, optional `option_id`, `context_token`, and an idempotency key. `GenerativeUIRegistry` MUST start empty (no product cards). `GenerativeUIComposer` MUST validate against the registry and emit only registered versioned contracts. The backend MUST NOT render widgets.

#### Scenario: Closed registry on backend
- **WHEN** the composer is asked to emit an unregistered component
- **THEN** the backend MUST refuse to include it in the response

#### Scenario: Backend does not render
- **WHEN** a registered contract is composed
- **THEN** the API MUST return the declarative payload and MUST NOT return HTML, Flutter widgets, or executable UI code

### Requirement: Flutter GenerativeUIRenderer
Flutter MUST own `GenerativeUIRenderer`. It is solely responsible for rendering backend-emitted contracts. The renderer MUST reject unknown component names, versions, fields, or actions and show `fallback_text`. It MUST NOT execute actions from an unknown payload.

#### Scenario: Unknown component rejected
- **WHEN** a payload names a component that is not registered in the Flutter renderer
- **THEN** Flutter MUST render `fallback_text` and MUST NOT execute any action from that payload
