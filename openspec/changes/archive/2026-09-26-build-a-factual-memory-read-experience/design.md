## Context

ADR-025 is accepted. `operations.business_events` is append-only. `operations.source_coverage_records` is insert-if-absent. Migration head is `0012_source_coverage_event_memory`. `0012` did not backfill events. Domain state still lives in the existing tables: `OperationalDay`, confirmed `SaleSession` and `Payment`, current `CashCount`, immutable `ClosingSnapshot`, `OutcomeRun`, and `WorkItem`.

`operational_day.summary@1` remains the live "hoy" summary. Its fallback still starts with `Hoy`. `MemoriaPage` is still the placeholder "Lo que Lumo recuerda". There is no public memory route and no memory tool. `list_business_events` already lists one day in chronological order. `summarize_day`, `get_current_cash_count`, `get_snapshot_for_day`, `get_daily_close_outcome`, `list_open_work_items`, and `list_source_coverage` already exist.

Architecture §12 says Build A may query factual memory and must not use embeddings. It also mentions a confidence level. ADR-025 already rejected confidence, prose, and embeddings on the event row. This slice does not add them back. v0.11 memory fields that conflict with ADR-025 stay out.

Constraints that stay in force: one orchestrator (ADR-008), the LLM does not mutate (ADR-006), money is deterministic Decimal on the server (ADR-007), Flutter does not calculate domain amounts (ADR-001), tenant context comes from the session (ADR-010), and reads do not reserve idempotency or write the outbox (ADR-011, as already applied to Next Best Action).

## Goals / Non-Goals

**Goals:**

- Let the merchant, Memoria, and the orchestrator read confirmed Lumo facts through one closed taxonomy.
- Keep "no matching row" distinct from "that did not happen in the real world".
- Answer closed-day money from the frozen `ClosingSnapshot`.
- Ship one read-only tool and one narrow timeline GET. Memoria renders those facts with the existing design system.

**Non-Goals:**

- Embeddings, vector search, RAG, free-text search, generic SQL, inferred memory, forecasting, recommendations, completeness scores, and Build B.
- A new table, column, index, audit action, outbox type, idempotency operation, or Generative UI component.
- Editing or deleting events. Replacing `operational_day.summary@1` or changing its copy.
- A Memoria composer, question chips, search field, or the prototype actions Corregir, Explicar, Olvidar, and Ver evidencia.

## Decisions

### 1. One application read service, no persisted query

`FactualMemoryQuery` and `FactualMemoryResult` are pure values. They are not tables.

- Domain types and argument checks live in `backend/app/domain/operations/factual_memory.py`. No FastAPI, SQLAlchemy, or LLM imports.
- `FactualMemoryService` lives in `backend/app/application/queries/get_factual_memory.py`. It loads facts, events, and coverage, and builds the result. It does not call an LLM, write prose into the result, or mutate workflow state.
- The tool and `GET /api/v1/memory/events` both call application reads. They do not share a generic query builder.
- New repository methods, only these, on the existing operations repository: `list_recent_business_events`, `get_latest_completed_close`, and `list_cash_difference_closes`. Day chronology reuses `list_business_events`.

### 2. Closed taxonomy and time scopes

Query types are exactly `day_summary`, `day_events`, `sales_summary`, `cash_summary`, `close_summary`, `latest_close`, and `recent_cash_differences`.

Scopes are exactly `today`, `yesterday`, an explicit `business_date` (`YYYY-MM-DD`), `latest`, and `recent_days`. The repository never parses "last quarter" or "this year". The conversation layer resolves language into one approved scope before the tool call.

`today` and `yesterday` use `business_date_for` and the business IANA timezone, the same rule as sale commit. Yesterday is that business-local date minus one calendar day, not UTC minus 24 hours. `latest` is valid only for `latest_close`. `recent_days` is an integer from 1 through 30 and is valid only for `recent_cash_differences`. A date after business-local today does not create an `OperationalDay`. The result is empty with `empty_reason=no_operational_day`.

### 3. Domain tables stay authoritative

`business_events` are chronology. They do not replace a snapshot or a current count.

| Query | Authoritative facts | Events on the result |
|---|---|---|
| `day_summary` | Open: `summarize_day`, current `CashCount`, open WorkItem count. Closed: `ClosingSnapshot` only for money and sale counts | That day's events, `occurred_at` ASC, `id` ASC |
| `day_events` | None (`facts` null) | That day's events, same order |
| `sales_summary` | Open: `summarize_day`. Closed: snapshot sale and tender totals | Empty. Optional `sale_event_refs` inside facts |
| `cash_summary` | Open: current `CashCount` plus `cash_difference` / `cash_status_for` on `summarize_day.cash_total`. Closed: snapshot money | Empty |
| `close_summary` | `ClosingSnapshot` plus `get_daily_close_outcome` | The matching `daily_close_completed` event when it exists |
| `latest_close` | Same shape as close summary, for one snapshot | That close event when it exists |
| `recent_cash_differences` | `ClosingSnapshot` rows only | Empty |

Open-day sales reuse `summarize_day` so this slice does not add a second aggregation SQL path. `operational_day.summary@1` is not called and its copy does not change. Closed-day totals are copied from the snapshot. A later read must not recompute them from payments or from event JSON.

`sale_event_refs` are `{event_id, sale_session_id}` in event order. Migration `0012` inserted no historical events, so a closed day can have `sale_count > 0` and an empty ref list. Counts and money come from facts, never from `len(events)` or `len(sale_event_refs)`.

`pending_work_count` is the number of open WorkItems on that day. It is not a recommendation.

`day_status` is the `OperationalDay` status. `close_status` is `completed` only when a snapshot exists, and `not_completed` otherwise. An open day is never presented as a final close.

### 4. Result contract and empty reasons

`FactualMemoryResult` fields are `query_type`, `business_id`, `business_date`, `period_start`, `period_end`, `facts`, `events`, `source_coverage`, `limitation_code`, and `empty_reason`. `business_id` is the tenant. Money values are decimal strings with two fraction digits. There is no narrative field.

`limitation_code` is `only_lumo_registered_operations` on every result, including empty ones. It is not a confidence score.

`source_coverage` is the existing recorded-operations declaration (`basis=recorded_operations`, sorted domains, sorted sources, the same limitation, `merchant_source_declaration=null`) when the query resolved one `OperationalDay`. It is null when no day row exists and null for `recent_cash_differences`, which is a window rather than one day. Empty coverage is still that declaration with empty domains and sources.

Empty reasons, and only these:

| Reason | When |
|---|---|
| `no_operational_day` | A day-scoped query has no `OperationalDay`, including a future date |
| `no_confirmed_sales` | `sales_summary` and the day exists with `sale_count` 0 |
| `no_cash_count` | `cash_summary` on an open day with no current `CashCount` |
| `no_completed_close` | `close_summary` without a snapshot, or `latest_close` with no snapshot for the tenant |
| `no_matching_facts` | `day_events` when the day exists and has no events, or `recent_cash_differences` when the window has no qualifying `ClosingSnapshot` |

`day_summary` of an existing day keeps `empty_reason` null and returns partial facts, including `sale_count` 0. `facts` is null when `empty_reason` is set. No reason may be `nothing_happened`, `no_sales_occurred`, `fully_empty_day`, or `no_matching_events`. `no_matching_facts` names a missing factual result. It does not name the table that was read. A day with no business events and a window with no short or over snapshot both use it.

Single-day queries set `business_date`, `period_start`, and `period_end` to the requested business date even when the day row is missing. `latest_close` sets those date fields only when a snapshot exists. `recent_cash_differences` leaves `business_date` null and sets `period_start` and `period_end` to the inclusive window.

### 5. Latest close and recent cash differences

`get_latest_completed_close` is tenant-scoped, read-only, and returns one row. Order is `business_date DESC`, `closed_at DESC`, `id DESC`. Business date is primary because "último cierre" means the latest closed business day. `closed_at` and `id` only break ties. A missing row is `no_completed_close`.

`recent_cash_differences` reads `ClosingSnapshot` only. The window is the inclusive business-local range from `today - (recent_days - 1)` through `today`. A row qualifies only when `cash_status` is `short` or `over`. Order is `business_date DESC`. One row per closed day. `closed_at` is always present on these rows because every snapshot has it; the field stays nullable on the shared fact shape and this query does not emit null. Open-day counts and superseded `cash_count_recorded` events are excluded. Today's open difference is `cash_summary` for today, not this query. There is no severe, suspicious, unusual, or recurring label.

### 6. Event read DTO

The read DTO fields are `event_id`, `event_type`, `business_date`, `occurred_at`, `source_type`, `source_entity_type`, `source_entity_id`, and `facts`. `business_date` comes from the linked `OperationalDay`, not from the UTC calendar date of `occurred_at`. No title, description, sentiment, score, confidence, or embedding is stored or added.

Day-scoped conversational queries are not paginated. The bound is one operational day. The timeline is the only paginated read.

### 7. Tool `memory.business_facts@1`

Registration: version `1`, `side_effect=read`, `requires_idempotency=false`, permission `sale.create`, policy `MEM-001`.

`sale.create` is temporarily reused as the existing operational-access permission, the same permission already used by `operational_day.summary@1` and `operational_day.next_best_action@1`. It does not imply that `memory.business_facts@1` can create a sale. The tool remains `side_effect=read` and `requires_idempotency=false`. `MEM-001` remains mandatory. The tool performs no mutation. This slice does not introduce a granular read permission.

Input is a closed object. Required: `query_type`. Optional: `business_date`, `recent_days`. No other properties. Forbidden: `query`, `sql`, `filters`, `event_type`, and `business_id`.

- Day-scoped types require `business_date` and forbid `recent_days`. The orchestrator resolves today and yesterday before the call.
- `latest_close` forbids both `business_date` and `recent_days`.
- `recent_cash_differences` requires `recent_days` from 1 to 30 and forbids `business_date`.

`MEM-001` denies any other shape with reason `factual_memory_arguments_denied` and does not invoke the service. The LLM chooses when to ask for an approved query. It does not choose SQL, the tenant, the source table, or extra filters.

The tool must not mutate, reserve idempotency, audit, enqueue outbox, insert a business event, or update coverage. It runs under the request tenant and existing RLS. No `BYPASSRLS`.

No new Generative UI component and no new UI action. Replies are ordinary assistant text. Existing structured UI is unchanged.

### 8. Phrase mapping and safe failure

Normalization matches the other closed phrases: accent folding, case folding, collapsed whitespace, and one stripped layer of `¿?¡!`.

These exact strings select `memory.business_facts@1` and must not select `operational_day.summary@1`:

| Normalized phrase | Call |
|---|---|
| `que paso hoy` | `day_summary` for today |
| `que paso ayer` | `day_summary` for yesterday |
| `cuanto vendi hoy`, `cuantas ventas tuve hoy` | `sales_summary` for today |
| `cuanto vendi ayer`, `cuantas ventas tuve ayer` | `sales_summary` for yesterday |
| `como cerre hoy` | `close_summary` for today |
| `como cerre ayer` | `close_summary` for yesterday |
| `cual fue mi ultimo cierre`, `que paso en el ultimo cierre` | `latest_close` |
| `hubo diferencia de caja`, `hay diferencia de caja` | `cash_summary` for today |
| `he tenido diferencias de caja ultimamente` | `recent_cash_differences` with `recent_days=7` |
| `que eventos hubo hoy` | `day_events` for today |
| `que eventos hubo ayer` | `day_events` for yesterday |

`que paso el YYYY-MM-DD` and `que paso el <day> de <spanish-month>` with an optional `de <year>` map only to `day_summary`. A missing year uses the year of business-local today. The interpreter does not roll a future date back to the previous year. A future or invalid date does not call the tool and does not create a day.

`como vamos hoy`, `ventas de hoy`, and `cuanto vendimos hoy` stay on `operational_day.summary@1`.

Matching runs with the other closed operational phrases, after the existing day-summary phrases, and before product parsing.

These exact unsupported history phrases do not call the tool and do not become a sale: `el trimestre pasado`, `este ano`, `el ano pasado`, `que paso el trimestre pasado`, `que paso este ano`, `que vendi este ano`, `que vendi el ano pasado`. The server text is: "Puedo consultar hechos registrados en Lumo para hoy, ayer, una fecha ya transcurrida, el último cierre, o las diferencias de caja de los últimos días. No encuentro esa consulta entre esos hechos."

Any other utterance keeps its current sale, close, or clarification path. The model must not answer an unsupported history question from its own knowledge.

Scripted replies are composed in the application response path from the typed result. They are not stored and they are not part of `FactualMemoryResult`. Preferred forms start with "Según las ventas registradas en Lumo", "En las operaciones registradas en Lumo", "El cierre registrado", or "El último cierre registrado en Lumo". Missing facts use "No encuentro … registrado en Lumo". The reply must not say "No vendiste", "No hubo ninguna operación", "No te faltó ninguna venta", "Todo quedó registrado", or "El día estuvo completo".

### 9. Timeline API and Memoria

`GET /api/v1/memory/events` is the only new HTTP route, in `backend/app/api/routes/memory.py`. Tenant comes from the authenticated context. Query parameters are `limit` (default 20, minimum 1, maximum 50) and optional opaque `before`. There is no `event_type`, `business_id`, `q`, or SQL parameter. A bad limit or a malformed cursor is HTTP 422 `VALIDATION_ERROR`. The handler does not write.

The server window is the last 7 business-local dates, including today. That window is not a client parameter. Order is `occurred_at DESC`, `id DESC`. The cursor is the last returned `(occurred_at, id)` and cannot be used to read older than the window. A well-formed cursor outside the window returns an empty list and `next_cursor` null. Default page size 20. Maximum 50.

The response adds two server dates, `business_today` and `business_yesterday`, plus `local_time` (`HH:MM` in that operational day's timezone) on each event. Those display fields are not columns. Flutter groups by `business_date`, labels `Hoy` and `Ayer` by equality with the server dates, and otherwise formats the calendar date with a fixed Spanish month name. It must not derive the group from `occurred_at`, from the device timezone, or from UTC.

`MemoriaPage` replaces the placeholder. Canvas `#FCFAF4`, soft white cards, 24px radius, no hard border, the existing soft shadow, Inter for body, Instrument Serif for the screen title already used by Memoria. Groups follow design-system §4.17: typographic date headers, 24px between groups, 10px between cards, no vertical rail. Header stays the Memoria eyebrow and the serif title "Lo que Lumo recuerda". This slice does not add the prototype composer, question chips, or memory action links.

Rendering is a fixed map, not an LLM:

- `sale_confirmed`: title "Venta registrada"; body `{amount} · {Efectivo|Tarjeta|Transferencia}`.
- `cash_count_recorded`: title "Conteo de efectivo"; lines for esperado, contado, and diferencia; chip Cuadrado, Faltante, or Sobrante.
- `daily_close_completed`: title "Cierre completado"; ventas registradas, caja status, and diferencia.

The client does not show event ids, source ids, or the limitation code. An unknown event type is omitted. Amounts are the server strings. Flutter does not add, subtract, or count a day total.

One footer, not on every card: "Memoria muestra operaciones confirmadas registradas en Lumo."

Empty state title: "Todavía no hay actividad registrada". Body: "Las ventas, conteos y cierres confirmados aparecerán aquí." A "Ver anteriores" control loads `next_cursor` and stops when it is null. That is not an infinite scroll of full history.

Each confirmed sale remains its own card. A day with more than 50 sales fills the first page with the latest events. Older events inside the 7-day window are reached only through the cursor, still at most 50 per request. No aggregation event is created. "¿Cuánto vendí?" stays a `sales_summary` question, not a timeline sum.

### 10. Indexes, RLS, and observability

No migration and no new index. Day reads use `ix_business_events_business_day` after the day id is known. The timeline resolves at most 7 days through the unique `(business_id, business_date)` key, then that event index, with `LIMIT` 50. Latest close and cash-difference reads filter `closing_snapshots` by the existing `business_id` index inside a 30-day or one-row bound. If a later measurement shows a sequential scan problem, an index is a separate change. This design does not add `0013`.

Every query sets the existing tenant GUC and relies on `FORCE` RLS. The client and the tool cannot pass `business_id`.

Technical logs may include `query_type`, duration, result count, and the correlation id. They must not include full fact payloads, merchant amounts, or the composed reply. No new business audit.

### 11. ADR-026

`docs/adr/ADR-026-factual-memory-read-model.md` records this read model. Status is Accepted. ADR-015 through ADR-025 are not edited.

### 12. Resolved questions

1. **Where day-summary numbers come from.** Open days reuse `summarize_day` inside `FactualMemoryService`. Closed days use the snapshot. There is no second sales SQL path and no new stored projection. The existing summary tool stays the "hoy" conversation.
2. **Latest-close order.** `business_date DESC`, then `closed_at DESC`, then `id DESC`.
3. **Recent cash differences.** `ClosingSnapshot` only, short or over, inside the business-date window. Open counts stay on `cash_summary`.
4. **Many sales on Memoria.** One card per `sale_confirmed`. No rollup card.
5. **More than 50 sales in a day.** The timeline pages inside a 7-day window, 50 events per request. It does not create an aggregation event. Totals stay on `sales_summary`.
6. **Events on `day_summary`.** The result includes typed facts and that day's event DTOs. Facts are authoritative. `sales_summary` does not embed event bodies; it may include id refs only.
7. **Unsupported history.** Exact out-of-scope phrases and future or invalid dates return the scope sentence, call no tool, and write nothing. The repository still has no natural-language query.

## Risks / Trade-offs

- [Days closed before event memory have snapshots and no `daily_close_completed` row] → Close and sales answers use the snapshot. Empty events must not be spoken as "no sales" when `sale_count` is greater than zero.
- [An open `day_summary` changes when a new sale or count commits] → `day_status=open` and `close_status=not_completed` stay on the result. Repeated reads are stable only while the underlying rows are unchanged.
- [The timeline index is the day index, not `(business_id, occurred_at)`] → The 7-day and 50-row bounds keep the read small for the pilot. No index is added on speculation.
- [A live model could pass `recent_days` other than 7] → The tool allows 1..30, which is the product cap. The scripted phrase always sends 7. Values outside 1..30 are denied.
- [Design-system Memoria includes a composer and action links] → Those affordances imply edit, forget, and questions this slice does not answer. They stay off Memoria. Questions stay on Inicio.

## Manual acceptance

Run these one at a time. After each conversation, confirm the relevant row counts are unchanged: `business_events`, `source_coverage_records`, audit, outbox, and idempotency.

1. Open day, one confirmed sale. Ask "¿Cuánto vendí hoy?". The answer uses the registered Lumo total and the conservative wording.
2. Same day, a short `CashCount`. Ask "¿Hubo diferencia de caja?". The answer states expected, counted, difference, and status.
3. Close that short day. Ask "¿Cómo cerré hoy?". The answer matches the `ClosingSnapshot`. Coverage stays `observed` and is not described as complete.
4. On the next business day, ask "¿Cuál fue mi último cierre?". The answer is the previous closed day.
5. Open Memoria. The timeline shows `sale_confirmed`, `cash_count_recorded`, and `daily_close_completed` in order, grouped by the local business date.
6. Ask for a date or a period with no matching fact. The answer says "No encuentro … registrado en Lumo" and does not say that the event did not occur.

## Migration Plan

No schema change and no data backfill. Deploy is application code and the Flutter timeline only. Rollback removes the route, the tool registration, and the Memoria screen. Existing events, coverage, snapshots, and `operational_day.summary@1` stay as they are. Head remains `0012_source_coverage_event_memory`.

## Open Questions

None. The seven product questions in the change brief are decided in section 12.
