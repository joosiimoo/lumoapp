## 1. Reuse current day, outcome, and next-action contracts

- [x] 1.1 Confirm the projection calls `desired_open_type`, `summarize_day`, `get_current_cash_count`, `list_open_work_items`, `get_daily_close_outcome`, `get_snapshot_for_day`, and `list_source_coverage`. Do not add a rank table, a WorkItem list route, or an outcome route
- [x] 1.2 Leave `GET /api/v1/operational-days/current/next-best-action`, `operational_day.summary@1`, `closing.prepare@1`, and `memory.business_facts@1` unchanged

## 2. Typed projection

- [x] 2.1 Add `backend/app/domain/operations/business_stream.py` with the closed `operator_state` and `close_progress` values, the result types, and a pure selector from day status, `desired_open_type`, and snapshot presence. No I/O and no model call
- [x] 2.2 Add the scripted `responsibility`, `detail`, and `attention.why` templates, including the cash-count expected-cash sentence. Reject the forbidden completeness phrases and the architecture words

## 3. Query composition

- [x] 3.1 Add `GetBusinessStream` in `backend/app/application/queries/get_business_stream.py`. Resolve business-local today from the business timezone. Open-day money comes from `summarize_day` and the current CashCount. Closed money comes only from the ClosingSnapshot
- [x] 3.2 Map `no_active_day` and `unavailable` to null facts, null attention, null action, and null coverage. Do not emit the summary tool's zero-sales payload. Attach `work_item_id` and `outcome_run_id` only when those rows already exist. Do not insert a missing row

## 4. Read API

- [x] 4.1 Add `GET /api/v1/business-stream/today` with session tenant, no `business_id`, and no date parameter. Unknown query parameters return HTTP 422 `VALIDATION_ERROR`. Do not require `Idempotency-Key`
- [x] 4.2 Return the closed JSON body from the query, including `as_of`. Do not return `reason_code`, outcome evidence, a confirmation token, `pending_count`, or a percentage

## 5. Policy and tenant isolation

- [x] 5.1 Keep the route on `get_tenant` and the existing repository tenant filters. Do not add a table, an RLS policy, or a migration
- [x] 5.2 Prove tenant B cannot read Carrota's totals or `work_item_id`, and that two GETs leave OperationalDay, WorkItem, OutcomeRun, coverage, audit, outbox, and idempotency counts unchanged

## 6. Flutter model and API client

- [x] 6.1 Add a typed client method for `GET /api/v1/business-stream/today` and a Dart model that decodes the body without summing money or choosing a state
- [x] 6.2 Map `cash_status` to `Falta contar efectivo`, `Caja cuadrada`, `Faltante`, and `Sobrante`. Format decimal strings for display only

## 7. Inicio operator surface

- [x] 7.1 Render one panel below `Buenos días` and above the conversation, using the existing canvas and card styles. Keep `LumoComposer` and the four tabs
- [x] 7.2 Load the panel when Inicio becomes visible and again after a successful message or action from that conversation. A failed GET replaces the panel with `No pude consultar el estado de hoy.` and a retry control, and drops the previous factual summary

## 8. Existing actions

- [x] 8.1 `Registrar conteo` only focuses the composer. It does not post, insert text, or open an amount field
- [x] 8.2 Label the panel control `Revisar cierre`. The tap posts `cerrar el día` on the existing shell `conversation_id` and does not post `/api/v1/lumo/actions`. Set `primary_action.action_id` to null. Do not put `closing.request@1` on the panel payload. Do not render `Confirmar cierre`, a recount control, a reason field, or a close-with-difference action. Do not register a Generative UI component or a new action id

## 9. Coverage and claim boundary

- [x] 9.1 When a day exists and the state is not `unavailable`, return `limitation_code` `only_lumo_registered_operations` and `Este cierre considera las operaciones registradas en Lumo.` Show that sentence only. Do not show domains, a score, or a percentage
- [x] 9.2 Keep open-day copy on registered sales and closed copy on the snapshot. Do not claim the day is complete, that every sale was captured, or that no further operations occurred

## 10. Automated tests

- [x] 10.1 Cover `no_active_day` without creating a day, an open day with `desired_open_type` null as `organizing` / `progressing` / no primary action, `cash_count_required` with expected cash `22.50`, short and over `cash_difference` with server amounts and label `Revisar cierre`, balanced `ready_to_close`, and `closed` matching the ClosingSnapshot. Do not add a merchant flow to produce `organizing`
- [x] 10.2 Cover a missing snapshot as `unavailable`, a repeated GET that writes nothing, unknown query parameters, tenant isolation, and the absence of an outcome route and a coverage route
- [x] 10.3 Cover Flutter label mapping, composer focus, the `Revisar cierre` tap posting `cerrar el día` with `action_id` null, failed-refresh copy, and that page load does not emit a conversation card. Do not add a migration test

## 11. Manual acceptance

- [x] 11.1 On Carrota, use only current product flows. Walk `no_active_day` before any sale. Confirm one cash sale and see `cash_count_required` with the expected amount and `Registrar conteo`. Record a count that does not match and see `cash_difference` with server expected, counted, and difference, `Faltante` or `Sobrante`, `Esperando tu revisión`, and `Revisar cierre`. Where practical, record a count that matches expected cash and see `ready_to_close`, then confirm on the existing card and see `closed` facts match the snapshot. Do not walk `organizing` or `unavailable`, and do not insert rows by hand to reach them
- [x] 11.2 Repeat the today GET and confirm it writes nothing. Confirm another tenant cannot see Carrota's panel. Confirm the surface reads as Lumo organizing the day rather than as a cash register, a POS grid, a report dashboard, or a transaction list. Do not invent a perception score

### Manual acceptance record (2026-09-26)

**11.1 PASS:** `no_active_day`; `cash_count_required`; `cash_difference`; `ready_to_close`; `Revisar cierre` reused existing conversation flow; `closing.confirm@1` remained card-only; `closed` with snapshot-aligned facts; copy defect `1 ventas` corrected to `1 venta`.

**11.2 PASS:** Three repeated Carrota `GET /api/v1/business-stream/today` returned HTTP 200 `closed` with unchanged snapshot facts and no row writes; tenant B (`no_active_day`, no Carrota leakage); qualitative anti-POS PASS; historical `Cerrar el día` conversation card below panel is expected history and does not change operator state.

## 12. ADR

- [x] 12.1 Keep `docs/adr/ADR-027-business-stream-read-model.md` at Accepted. Do not edit ADR-016 through ADR-026 and do not add Alembic `0013`
