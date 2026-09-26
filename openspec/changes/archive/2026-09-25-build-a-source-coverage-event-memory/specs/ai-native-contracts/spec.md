## ADDED Requirements

### Requirement: Assistant output must not claim unverified completeness
The server MUST NOT emit new or changed assistant text, UI fallback text, or tool output that states that all of today's sales were captured, that no sale is missing, that 100% of the operation was registered, or that the day's operation is complete, unless a source-coverage status of `declared_complete` exists. Build A MUST NOT produce `declared_complete`. Existing day-summary text and confirmed-close text MUST stay unchanged. Wording that remains allowed for a later slice is limited to operations registered in Lumo, including "Según las ventas registradas en Lumo…", "En las operaciones registradas hoy…", and "El cierre registrado en Lumo…". `ToolRegistry` MUST NOT register `memory.query_events` or a source-coverage tool. `GenerativeUIRegistry` MUST NOT register a memory or coverage component. `UiActionRegistry` MUST keep exactly its current action ids.

#### Scenario: Summary and close copy stay factual
- **WHEN** a day summary and a confirmed close are rendered after this change
- **THEN** the summary fallback MUST still begin with `Hoy` and the close fallback MUST still begin with `Cierre confirmado`, and neither string MUST claim that every real-world sale was captured

#### Scenario: No memory or coverage tool is registered
- **WHEN** `ToolRegistry` is queried for `memory.query_events` and for a source-coverage tool
- **THEN** both MUST be unregistered, and the existing tool list MUST be unchanged
