## Context

Inicio is a greeting, a composer, and a conversation. Operational responsibility appears only after a phrase: `ventas de hoy` emits `operational_day_summary@1`, a cash phrase emits `daily_close_preparation@1`, and `qué sigue` emits `next_best_action@1`. Hoy already reads `GET /api/v1/operational-days/current/next-best-action` for one next step. Memoria reads `GET /api/v1/memory/events`.

Those contracts do not answer Inicio on open. The Next Best Action body is null when today has no OperationalDay, the open day has no confirmed sales, or the day is closed. It has no registered-sales total, no tender split, no snapshot, and no source-coverage sentence. `operational_day.summary@1` is a tool, and its missing-day payload is a zero-sales summary, which this surface must not show as the idle state. OutcomeRun has no merchant route. Source coverage has no HTTP route. A client that called the pieces it can reach would still be choosing the state.

PRD v0.11 §8.18, §12.2, §12.6, §17.3, and §17.5 require Build A Inicio to show current responsibility: what Lumo is handling, what needs the merchant, the one next action, and whether the close is progressing, waiting, ready, or completed. §26.1 expects the initial interface to load in under 2 seconds in normal conditions. The current Daily Close model already has the facts: an OperationalDay is created by the first confirmed sale, not by a read; `desired_open_type` ranks `cash_count_required`, then `cash_difference_review`, then `close_confirmation_required`; short and over may close; `closing.confirm@1` writes one ClosingSnapshot.

Product scope for this change is PRD v0.11 only. Current behavior is taken from the archived specs and the code those specs describe.

## Goals / Non-Goals

**Goals:**

- On open or refresh, Inicio shows today's operator state without a merchant question.
- One primary action, or none. Server-owned. Flutter displays it.
- Reuse the cash-count phrase and the existing close request. Do not add a workflow.
- Keep the factual-memory claim boundary, including a single coverage sentence and no percentage.
- One read, no writes, session tenant, business-local today.

**Non-Goals:**

- RF-083, RF-084, RF-085, RF-075, and RF-096.
- Push, schedulers, email, WhatsApp, or a reminder preference.
- Longitudinal comparison, insights, recommendations, forecasting, replenishment, inferred memory, Resolution Memory, AutomationCandidates.
- Build B: mixed payments, corrections, cancellation, reopen, exception acceptance, late data, advanced permissions, offline sync.
- A missing-payment WorkItem. A confirmed sale already has one payment. A `ready_to_charge` session stays on its conversation card.
- A new tool, a new UI action id, a new Generative UI component, a migration, or a change to Hoy or Memoria.

## Decisions

### 1. Dedicated projection, not client assembly, not an NBA extension

`GET /api/v1/business-stream/today` is the Inicio contract. ADR-027 records this and is Accepted.

Alternatives:

- Assemble in Flutter from the NBA GET plus a summary call. Rejected. Coverage and the closed snapshot are not both on those responses, and Flutter would be selecting the state.
- Add fields to the NBA GET. Rejected. Hoy treats null as "omit the block". Closed, idle, and "Lumo is organizing" need a positive body. Extending that route would change Hoy.
- Add `GET /api/v1/operational-days/current/outcome`. Rejected. `daily-close-outcome` forbids an outcome route. This projection may read the run id and must not return the run.

The route takes no `business_id`, no date, and no other query parameter. An unknown query parameter is HTTP 422 `VALIDATION_ERROR`. Today is `business_date_for` in the business IANA timezone, the same clock rule as the NBA query. Tenant comes from `get_tenant`. No `Idempotency-Key`.

Directory: pure types and state selection in `backend/app/domain/operations/business_stream.py`; composition in `backend/app/application/queries/get_business_stream.py`; route in `backend/app/api/routes/business_stream.py`. The domain module does not import FastAPI or SQLAlchemy. The query reuses `OperationsRepository` reads already used by summary, preparation, NBA, and factual memory: day by date, `summarize_day`, current cash count, open WorkItems, `get_daily_close_outcome`, `get_snapshot_for_day`, `list_source_coverage`. No new table, column, or index. Head stays `0012_source_coverage_event_memory`.

### 2. Closed operator state from the existing predicate

Selection uses `desired_open_type` and the presence of the day and snapshot. It does not add a rank table and it does not call the LLM. It does not insert a missing WorkItem or OutcomeRun (ADR-023: reads do not reconcile).

| Condition | `operator_state` | `close_progress` |
|---|---|---|
| No OperationalDay for business-local today | `no_active_day` | `none` |
| Day `closed` and its ClosingSnapshot exists | `closed` | `completed` |
| Day `closed` and the snapshot is missing | `unavailable` | null |
| Open day, `desired_open_type` is `cash_count_required` | `cash_count_required` | `waiting` |
| Open day, desired type is `cash_difference_review` | `cash_difference` | `waiting` |
| Open day, desired type is `close_confirmation_required` | `ready_to_close` | `ready` |
| Open day, desired type is null | `organizing` | `progressing` |

`desired_open_type` is null when the day is missing, closed, or `sale_count` is under 1. A normal confirmed sale with no count is `cash_count_required`, not `organizing`. `organizing` stays in the closed state set for an open day with no merchant step, and the read must not invent a button there.

No current merchant flow reaches `organizing`. `operational-day-foundation` creates today's OperationalDay on the first confirmed `sale.commit@1`, and that sale is attached to the day. Build A has no cancellation that would drop `sale_count` back under 1. An open day a merchant can produce therefore always has a desired type: cash count, cash difference, or close confirmation. Do not add a product flow, a Carrota script, or a hand-built row just to show `organizing`. Automated tests cover the predicate. Carrota walks only the states the current sale, count, and close flow can reach. `unavailable` is the same kind of case: a closed day with no snapshot is a data fault, covered by tests, not by a pilot script.

Live facts win over a stale OutcomeRun row. `derive_daily_close_outcome` uses the same inputs as the write path; the stored `reason_code` is not copied out and is not repaired. `work_item_id` is the open row of the desired type when that row exists, otherwise null. `outcome_run_id` is the stored run id when the row exists, otherwise null.

`close_progress` is the merchant-facing progress. It is not an OutcomeRun status and it is not a `reason_code`.

There is no seventh product state for missing payment, theft, fraud, or an exception policy. The only current blocking condition is an uncounted open day with at least one confirmed sale, which is already `cash_count_required`.

### 3. Smallest response

`BusinessStreamToday` is exactly:

- `business_date`
- `operator_state`
- `close_progress`
- `responsibility`
- `detail` (string or null)
- `factual_summary` (object or null)
- `attention` (object or null)
- `primary_action` (object or null, never an array)
- `coverage` (object or null)
- `as_of` (UTC timestamp of this read)

`factual_summary`, when present: `basis`, `sale_count`, `gross_sales_total`, `cash_total`, `card_total`, `transfer_total`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, `closed_at`. Money is `{ "amount", "currency" }` decimal strings. `basis` is `registered_sales` or `closing_snapshot`.

`attention`, when present: `kind` (`cash_count`, `cash_difference`, or `close_confirmation`), `why`, `actor` (`merchant`).

`primary_action`, when present: `kind`, `label`, `invocation`, `message`, `action_id`, `work_item_id`, `outcome_run_id`.

`coverage`, when a day exists: `limitation_code` `only_lumo_registered_operations` and `merchant_sentence` `Este cierre considera las operaciones registradas en Lumo.` Domains, sources, and `merchant_source_declaration` stay off this payload so the client cannot render a coverage panel.

No `pending_count`, no WorkItem list, no outcome evidence, no `reason_code`, no confirmation token, no percentage.

Authoritative fields:

| Visible fact | Source |
|---|---|
| Business date | Business timezone clock. Not the device. |
| Idle vs day | `OperationalDay` for that date. Absence is `no_active_day`. |
| Operator state | `desired_open_type` plus day status and snapshot presence, as in the table above. |
| Open-day sale count, gross, tenders, expected cash | `summarize_day`. Expected cash is `cash_total`. |
| Counted cash, difference, short/over/balanced | Current `CashCount` and the existing server difference. `not_counted` leaves counted and difference null. |
| Closed sale count, money, cash, `closed_at` | That day's `ClosingSnapshot` only. |
| `work_item_id` | Open WorkItem of the desired type, if the row is already there. |
| `outcome_run_id` | Stored Daily Close OutcomeRun for that day, if the row is already there. |
| Coverage sentence | Existing recorded-operations limitation. The sentence is fixed. |
| Headlines | Server templates below. |

`no_active_day` and `unavailable` set `factual_summary`, `attention`, `primary_action`, and `coverage` to null. They must not use the summary tool's zero payload.

### 4. Scripted responsibility, one action

Flutter displays `responsibility`, `detail`, and `attention.why` as given. It does not author them.

| State | `responsibility` | `detail` | Action |
|---|---|---|---|
| `no_active_day` | `Cuando empiece la actividad, organizo el día.` | null | null |
| `organizing` | `Lumo está organizando el cierre` | `Con lo registrado hasta ahora.` | null |
| `cash_count_required` | `Necesito que registres el efectivo contado` | `Espero $<expected> en caja. Cuando termines, registra cuánto tienes para continuar con el cierre.` | `record_cash_count` |
| `cash_difference` | `Esperando tu revisión` | null | `request_close` |
| `ready_to_close` | `Cierre listo para confirmar` | `Puedes revisarlo y confirmar el cierre.` | `request_close` |
| `closed` | `Cierre completado` | null | null |
| `unavailable` | `No pude consultar el estado de hoy.` | null | null |

Cash-count `detail` uses the existing `$` plus decimal-string formatter on server expected cash. Difference `why` is `La diferencia queda visible. No indica por qué ocurrió.` Ready `why` is `El cierre está listo para tu confirmación.` Cash-count `why` is `Hace falta para continuar con el cierre.`

`record_cash_count`: `label` `Registrar conteo`, `invocation` `composer`, `message` null, `action_id` null. The control focuses the existing composer. It does not insert text, change the placeholder, open an amount field, or post.

`request_close`: `label` `Revisar cierre`, `invocation` `message`, `message` `cerrar el día`, `action_id` null. The label and the message stay separate. The tap does not close or confirm the day. It posts that phrase to `POST /api/v1/lumo/messages` on the shell `conversation_id`. It does not post `/api/v1/lumo/actions` and does not send a token.

`closing.request@1` already exists. `UiActionRegistry` in `backend/app/agent/ui_actions.py` registers it with the payment actions and `closing.confirm@1`. `openspec/specs/generative-ui-actions/spec.md` requires that catalog. Counted `daily_close_preparation@1` and the Inicio `next_best_action@1` card already post that id through `/api/v1/lumo/actions`. This panel does not. Putting the id on a message-only control would be metadata for an invocation the panel does not make, so `primary_action.action_id` is null. The phrase is what already runs `request_close`. The existing turn then emits `daily_close_preparation@1`, and `closing.confirm@1` stays on that card. Short and over use the same `Revisar cierre` control. No recount form, no "agregar motivo", no "cerrar con diferencia", and no exception acceptance.

The panel never shows `closing.confirm@1`. The GET never mints a token.

User-visible copy must not contain `OutcomeRun`, `WorkItem`, `reason_code`, `orchestrator`, or `workflow engine`. It must not say `Todas tus ventas`, `No falta ninguna venta`, `El día está completo`, `Todo quedó registrado`, or `No hubo más operaciones`. Open-day gross is "ventas registradas", not a claim that every real-world sale was captured. A completed close is `Cierre completado` for operations registered in Lumo, and the coverage sentence stays.

Cash labels stay the existing closed map: `not_counted` → `Falta contar efectivo`, `balanced` → `Caja cuadrada`, `short` → `Faltante`, `over` → `Sobrante`. Flutter must take the word from `cash_status`, not from comparing amounts. A positive over difference may show a display `+`, the same formatting rule as `daily_close_preparation@1`.

### 5. Inicio is a Flutter surface, not a new card

The panel is ordinary Flutter above the conversation and below the greeting, inside the current max-width column, using the existing canvas, type, and card styles. No new `GenerativeUIRegistry` entry. `operational_day_summary@1`, `daily_close_preparation@1`, `daily_close_confirmed@1`, and `next_best_action@1` stay conversation artifacts and are not emitted on page load.

The greeting remains `Buenos días`. The composer remains `LumoComposer`. Navigation stays four tabs. Hoy's NBA block and export stay. Memoria stays the event timeline. The panel is not a sale list, a chart, a KPI grid, a POS keypad, or a second timeline.

Refresh: when Inicio becomes visible, and after a successful `POST /api/v1/lumo/messages` or `POST /api/v1/lumo/actions` from that Inicio conversation. Retry is explicit. No timer, no push, no background job.

A failed GET, or HTTP `unavailable` in the body, replaces the panel with `No pude consultar el estado de hoy.` and a retry control. It must not keep the previous factual summary, and it must not fall back to "todo está bien".

### 6. No-write, RLS, and one round trip

The query is read-only. Repeated GETs leave OperationalDay, WorkItem, OutcomeRun, CashCount, ClosingSnapshot, coverage, business events, audit, outbox, and idempotency counts unchanged. Opening Inicio does not create a day.

RLS is unchanged: no new table. Repository calls take the session tenant. Another tenant's GET returns that tenant's own today, which is `no_active_day` when they have no day, and never Carrota's totals.

The first paint is this one GET. It does not load `business_events`, does not page history, and does not call the model. That is what keeps the panel inside the PRD v0.11 initial-interface budget under normal conditions.

## Risks / Trade-offs

- [A skipped WorkItem initializer hides the row] → The projection still follows `desired_open_type` and does not insert the row. The action does not need the row id: cash count is the composer, and close is the existing phrase.
- [A stale OutcomeRun disagrees with live cash] → Live facts select the state. The read does not repair the run. The stored id is only an identifier.
- [The panel and a later conversation card both talk about the close] → The panel holds the current responsibility. The card appears only after the existing phrase or tool and remains the confirm step. The panel does not render `Confirmar cierre`.
- [`cerrar el día` from the panel depends on the shell `conversation_id`] → Same rule as Hoy and as typed close phrases. The panel must not start a second conversation.
- [Closed day without a snapshot] → `unavailable`, no invented totals. This is a data fault, not a calm success.
- [Merchant still asks "¿cómo vamos?" in chat] → Existing summary and NBA tools stay. This slice does not register a stream tool and does not retarget those phrases.

## Migration Plan

No schema change and no backfill. Deploy the API and the Inicio panel together. Rollback removes the route and the panel. Stored days, counts, runs, and snapshots are untouched. ADR-027 is Accepted. ADR-016 through ADR-026 stay as they are.

## Open Questions

None. The brief's seven questions are decided above: the payload in decision 3, a new GET in decision 1, idle copy in decision 4, NBA actor/reason/action reused as `merchant` plus the existing phrase or composer, coverage as one sentence, ready-to-close as the phrase that already produces `daily_close_preparation@1` rather than a new card, and refresh on visibility and after a successful mutation.
