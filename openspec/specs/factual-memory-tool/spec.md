# factual-memory-tool Specification

## Purpose

`memory.business_facts@1` is the only factual memory tool. It is a read. Permission `sale.create` is reused as existing operational access and does not grant the tool a write. This slice adds no new read permission.

## Requirements

### Requirement: memory.business_facts@1 is the only factual memory tool
`ToolRegistry` MUST register `memory.business_facts@1` with version 1, `side_effect=read`, `requires_idempotency=false`, permission `sale.create`, and policy `MEM-001`. The input object MUST allow only `query_type`, `business_date`, and `recent_days`. `query_type` MUST be one of `day_summary`, `day_events`, `sales_summary`, `cash_summary`, `close_summary`, `latest_close`, and `recent_cash_differences`. Additional properties MUST be rejected, including `query`, `sql`, `filters`, `event_type`, and `business_id`. A day-scoped query MUST require `business_date` and MUST reject `recent_days`. `latest_close` MUST reject both `business_date` and `recent_days`. `recent_cash_differences` MUST require `recent_days` from 1 to 30 and MUST reject `business_date`. `business_id` MUST come from the trusted tenant context. `PolicyEngine` MUST deny every other argument shape with `MEM-001` and reason `factual_memory_arguments_denied` before the query runs. The tool MUST NOT be `memory.query_events`. The system MUST NOT register a coverage tool, a generic memory search, semantic search, a free-text memory query, embeddings, a vector store, RAG, a generic memory table, a knowledge graph, forecasting, anomaly detection, pattern detection, recommendations, or Build B functionality.

#### Scenario: A day query without a date is denied
- **WHEN** the model calls `memory.business_facts@1` with `query_type` `sales_summary` and no `business_date`
- **THEN** policy MUST deny the call and the factual query MUST NOT run

#### Scenario: Latest close rejects a date and a window
- **WHEN** the model calls `latest_close` with `business_date` or `recent_days` set
- **THEN** policy MUST deny the call

#### Scenario: Free text is not an argument
- **WHEN** the model calls the tool with a `query` string or a `business_id`
- **THEN** policy MUST deny the call and no tenant MUST be taken from the arguments

### Requirement: The tool is read-only
Invoking `memory.business_facts@1` MUST return the `FactualMemoryResult` for that query and MUST NOT mutate domain state. It MUST NOT reserve idempotency, write audit, enqueue an outbox row, insert a business event, or update source coverage. It MUST run under existing tenant RLS. It MUST NOT use `BYPASSRLS`.

#### Scenario: A successful tool call writes nothing
- **WHEN** the orchestrator invokes `memory.business_facts@1` for today's `sales_summary`
- **THEN** the response MUST contain the typed result and the business event count, coverage count, audit count, outbox count, and idempotency count MUST be unchanged

### Requirement: Assistant text is grounded in the tool result
Scripted replies for this tool MUST be composed from the typed result and MUST NOT be stored on the result. A sales answer that has totals MUST be able to start with "Según las ventas registradas en Lumo". A cash or day answer MUST be able to start with "En las operaciones registradas en Lumo". A close answer MUST be able to start with "El cierre registrado". A latest-close answer MUST be able to start with "El último cierre registrado en Lumo". When no fact exists, the reply MUST use "No encuentro" and "registrado en Lumo". The reply MUST NOT say "No vendiste", "No hubo ninguna operación", "No te faltó ninguna venta", "Todo quedó registrado", "El día estuvo completo", or "Todas las ventas fueron registradas". Amounts MUST come from `facts` and MUST NOT be recomputed by summing `events`. `operational_day.summary@1` fallback text MUST remain unchanged.

#### Scenario: Missing sales use the registered-fact wording
- **WHEN** `sales_summary` returns `empty_reason` `no_confirmed_sales`
- **THEN** the scripted reply MUST say "No encuentro ventas registradas en Lumo para ese día." and MUST NOT say "No vendiste"

#### Scenario: A close answer uses the snapshot total
- **WHEN** `close_summary` returns a gross total of `1240.00`
- **THEN** the scripted reply MUST include that amount and MUST NOT claim that every real-world sale was captured

### Requirement: No memory Generative UI is added
`GenerativeUIRegistry` MUST NOT register a memory or coverage component for this tool. `UiActionRegistry` MUST NOT gain an action id. The conversational response MUST use ordinary assistant text or an already registered UI contract.

#### Scenario: The registry gains no memory card
- **WHEN** the application boots after this tool is registered
- **THEN** `GenerativeUIRegistry` MUST NOT contain a memory component and `UiActionRegistry` MUST still contain exactly its previous action ids
