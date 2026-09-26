## Why

Build A already confirms sales, cash counts, and Daily Close, and it stores an OutcomeRun, a ClosingSnapshot, audit, and outbox. It still has no durable answer to what Lumo is actually observing, and no factual memory of those confirmed events that is distinct from audit and outbox. PRD v0.11 §9.7 and §23.3–§23.4, Build A §5 and §7.12, and SRS RF-A-066 and RF-A-120 require that distinction. A completed close, a balanced count, or an empty WorkItem list must not be read as “all real-world sales were captured.”

## What Changes

- Persist Source Coverage in `operations.source_coverage_records`: what Lumo has observed for one business and one OperationalDay, from which implemented source, with a structured limitation. It is not a completeness percentage and it is not “100% of the business.”
- Recorded Operations Completeness is a structured declaration derived from those rows: domains represented, sources represented, the limitation, and that Build A has no merchant declaration that a source is complete. It is not a score and it is not inferred missing sales.
- Persist factual Event Memory in `operations.business_events` for three confirmed facts only: `sale_confirmed`, `cash_count_recorded`, and `daily_close_completed`. Writes happen in the same transaction as the parent fact. Replay does not duplicate them.
- Build A source type stays `manual_capture`, the value already stored on `Payment` and `CashCount`. A typed payment phrase and `sale.pay.*@1` are that same source. Daily Close is not a coverage domain.
- Coverage status is only `observed`. Close, balanced cash, a completed OutcomeRun, and zero open WorkItems do not upgrade it.
- No new merchant endpoint, no Memoria timeline, no new audit actions, and no new outbox events. ADR-025 records the decision. ADR-015 through ADR-024 stay unchanged.

## Capabilities

### New Capabilities

- `source-coverage`: Coverage identity, domains, `manual_capture`, status `observed`, limitation `only_lumo_registered_operations`, write hooks, today-only initialization, and the recorded-operations declaration.
- `factual-event-memory`: `business_events` taxonomy, fact schemas, uniqueness, same-transaction writes, and repository reads. Not chat memory, embeddings, or a generic memory platform.

### Modified Capabilities

- `conversational-sale-session`: A confirming `sale.commit@1` ensures sales coverage and one `sale_confirmed` event. `ready_to_charge`, replay, and confirmed read-back do not.
- `daily-close-preparation`: A new CashCount ensures cash-count coverage and one `cash_count_recorded` event. Equal-amount read-back and `closing.prepare@1` do not.
- `daily-close-confirmation`: A successful close writes one `daily_close_completed` event and does not treat coverage as complete.
- `daily-close-outcome`: A completed `daily_close_ready@1` is the Daily Close responsibility for operations represented in Lumo. It does not copy coverage into OutcomeRun evidence.
- `persistence`: Revision `0012_source_coverage_event_memory`, RLS, cleanup order, and downgrade.
- `ai-native-contracts`: Assistant and tool output must not claim unverified completeness. No coverage or memory tool is registered.

## Impact

- Backend: two `operations` tables, hooks inside `sale.commit@1`, a new CashCount insert, and `closing.confirm@1`, plus the existing open-today initializer for coverage only. No Flutter change. The Memoria tab stays the current placeholder.
- Docs: ADR-025 only.
- Sale UX, payment UX, Daily Close UX, WorkItem types, Next Best Action copy, the OutcomeRun state machine, export, the closing token, short/over closability, and `OperationalDay` `open|closed` stay as they are.

## Non-goals

- Build B, inventory, replenishment, suppliers, purchasing, forecasting, accounting, tax, bank reconciliation, POS or ecommerce integrations, and anomaly detection.
- A completeness percentage, inferred missing sales, `declared_complete`, or a claim that balanced cash proves sales completeness.
- Sale lines, price-override memory, WorkItem transitions, export memory, and the rest of PRD §7.12 beyond the three event types above.
- Model-generated memory, preferences, CRM, embeddings, vector search, semantic search, RAG, a knowledge graph, correlations, recommendations, insights, or a memory dashboard.
- A `memory` schema, Redis, Kafka, another agent, push notifications, or a public `/memory/search` endpoint.
- New rendered copy. Existing summary and close sentences stay. The conservative-claim rule is a contract for text this slice does not rewrite.
