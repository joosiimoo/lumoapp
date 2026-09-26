## Why

Build A already records confirmed sales, cash counts, closes, source coverage, and append-only business events (ADR-025). PRD Build A requires factual memory of each confirmed operation, SRS RF-A-120 requires Event Memory from the source fact, and Architecture §12 allows a factual query without embeddings. None of that is readable yet: Memoria is still a placeholder, and there is no memory tool or memory API. The merchant cannot ask what Lumo has registered.

## What Changes

- Add a non-persisted factual read: a closed query taxonomy, deterministic time scopes, and one typed `FactualMemoryResult`.
- Register one read-only tool, `memory.business_facts@1`. It does not replace `operational_day.summary@1`.
- Add `GET /api/v1/memory/events` and replace the Memoria placeholder with a deterministic timeline of recent business events.
- Keep domain tables authoritative for operational state. `business_events` stay chronology. Closing totals for a closed day stay on the frozen `ClosingSnapshot`.
- An empty result means no matching fact is recorded in Lumo. It does not mean the real-world event did not happen.

## Capabilities

### New Capabilities

- `factual-memory-read`: Query taxonomy, fact shapes, empty reasons, source hierarchy, and the read-only application service.
- `factual-memory-tool`: `memory.business_facts@1`, argument policy, phrase mapping, and grounded reply wording.
- `memoria-timeline`: Timeline API and the Memoria Flutter surface.

### Modified Capabilities

- `ai-native-contracts`: Register the read tool and policy `MEM-001`. Keep `memory.query_events` unregistered and add no memory Generative UI component.
- `factual-event-memory`: Allow bounded day and timeline reads. Still forbid search, semantic query, and natural-language SQL.
- `source-coverage`: Factual reads return the existing recorded-operations declaration and must not write coverage or treat it as confidence.
- `conversational-sale-runtime`: Route a closed Spanish phrase set to the new tool without moving existing day-summary, cash, or close phrases.

## Impact

- Backend: `FactualMemoryService` under `application/queries`, pure fact types under `domain/operations`, a few repository reads, one GET route, tool and policy registration, and scripted phrase routing. No Alembic revision. Head stays `0012_source_coverage_event_memory`.
- Mobile: `MemoriaPage` only. Flutter renders server facts. It does not sum money or invent event text. No new Generative UI schema.
- Docs: ADR-026, status Accepted. ADR-015 through ADR-025 stay unchanged.
- Reads must not write audit, outbox, idempotency, coverage, events, WorkItems, or OutcomeRuns.

## Non-goals

- Embeddings, pgvector, a vector database, semantic search, RAG, free-text memory search, or a generic event-search API.
- Stored model summaries, a `memory` schema, a knowledge graph, inferred memory, predictions, forecasting, anomaly or pattern detection, correlations, or recommendations.
- Inventory, replenishment, suppliers, accounting, bank feeds, ecommerce, or CRM memory.
- Editing or deleting events from the UI, a completeness score, or any "100% captured" claim.
- A new Generative UI component, a second orchestrator, or Build B.
- Migrations, new columns, or new indexes. Arbitrary ranges beyond 30 business days, "last quarter", "this year", and unbounded history.
