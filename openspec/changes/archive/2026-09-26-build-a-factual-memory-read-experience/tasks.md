## 1. Domain read model

- [x] 1.1 Add `backend/app/domain/operations/factual_memory.py` with the seven query types, the five empty reasons, the fact shapes, the event read DTO, and pure checks for `recent_days` 1..30 and a future business date. No I/O, prose, score, or embedding

## 2. Repository reads

- [x] 2.1 Add `list_recent_business_events`, `get_latest_completed_close`, and `list_cash_difference_closes` on the operations repository. Reuse `list_business_events`, `summarize_day`, `get_current_cash_count`, `get_snapshot_for_day`, `get_daily_close_outcome`, `list_open_work_items`, and `list_source_coverage`. No generic query builder and no new index

## 3. Factual memory service

- [x] 3.1 Add `FactualMemoryService` in `backend/app/application/queries/get_factual_memory.py`. Open-day sales use `summarize_day`. Closed-day money and counts come from `ClosingSnapshot`. Compose `FactualMemoryResult` with the recorded-operations declaration when one day was resolved
- [x] 3.2 Map empty reasons exactly: `no_operational_day`, `no_confirmed_sales`, `no_cash_count`, `no_completed_close`, and `no_matching_facts`. Leave `day_summary` `empty_reason` null when the day exists. Do not create a day for a future date

## 4. Read-only tool and policy

- [x] 4.1 Register `memory.business_facts@1` as a read tool with the existing permission `sale.create`, `side_effect=read`, and `requires_idempotency=false`, plus the closed input object. Reuse `sale.create` as operational access only. Do not add a new permission and do not treat the tool as able to create a sale. Add `MEM-001` so any extra argument, including `business_id`, `query`, and `sql`, is denied before the service runs
- [x] 4.2 Do not register `memory.query_events`, a coverage tool, a memory Generative UI component, or a new UI action. Leave `operational_day.summary@1` and its `Hoy` fallback unchanged

## 5. Conversation routing

- [x] 5.1 Map the closed Spanish phrases in `conversational-sale-runtime` to the tool, resolving today and yesterday in the business timezone before the call. Keep `como vamos hoy`, `ventas de hoy`, and `cuanto vendimos hoy` on `operational_day.summary@1`
- [x] 5.2 Return the scope sentence for the unsupported history phrases and for an invalid or future `que paso el …` date. Compose scripted replies from the typed result, including "No encuentro … registrado en Lumo", and do not store that prose

## 6. Timeline API

- [x] 6.1 Add `GET /api/v1/memory/events` with tenant context, `limit` default 20 and max 50, an opaque `before` cursor, the last 7 business dates, and order `occurred_at DESC`, `id DESC`. Include `business_today`, `business_yesterday`, and `local_time`. Invalid input is HTTP 422 `VALIDATION_ERROR`
- [x] 6.2 The route and the tool MUST NOT write events, coverage, audit, outbox, or idempotency

## 7. Memoria screen

- [x] 7.1 Replace `MemoriaPage` with the design-system timeline: canvas `#FCFAF4`, soft cards, date groups, and the three deterministic card templates. Group by server `business_date`. Show the empty state and the single footer sentence
- [x] 7.2 Do not add a composer, search, question chips, coverage percentage, or edit and delete actions. Flutter MUST NOT calculate totals. "Ver anteriores" stops at a null `next_cursor`

## 8. Tests

- [x] 8.1 Cover open and closed `day_summary`, `sales_summary` with sales and with none, short `cash_summary`, `cash_summary` with no count, `close_summary` for a closed day and for no close, `latest_close`, and `recent_cash_differences` excluding balanced and open days
- [x] 8.2 Cover day-event chronology, timeline order descending, business-date grouping across a UTC boundary, source coverage without a completeness flag, stable repeated reads, tenant isolation, and empty-reason wording
- [x] 8.3 Cover tool argument denial, API limit and cursor validation, deterministic Memoria rendering, no Flutter domain calculation, and unchanged audit, outbox, and idempotency counts. Do not add a migration test

## 9. ADR

- [x] 9.1 Keep `docs/adr/ADR-026-factual-memory-read-model.md` at status Accepted. Do not edit ADR-015 through ADR-025 and do not add Alembic `0013`

## 10. Manual acceptance

- [x] 10.1 Walk the six scenarios in design.md, one at a time, and confirm each conversation and the Memoria timeline leave the database unchanged
