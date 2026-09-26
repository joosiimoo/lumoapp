## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: MEM-001 guards the factual memory tool
`PolicyEngine` MUST include `MEM-001`. For `memory.business_facts@1`, `MEM-001` MUST allow only the closed argument shapes in `factual-memory-tool` and MUST deny every other shape with reason `factual_memory_arguments_denied`. The policy MUST NOT grant a write, an idempotency reservation, or a tenant chosen by the model.

#### Scenario: Policy allows a resolved day query
- **WHEN** policy evaluates `memory.business_facts@1` with `query_type` `day_summary` and a `business_date`
- **THEN** the decision MUST be `allow` with rule id `MEM-001`

#### Scenario: Policy denies a tenant argument
- **WHEN** policy evaluates `memory.business_facts@1` with a `business_id` argument
- **THEN** the decision MUST be `deny` with reason `factual_memory_arguments_denied`
