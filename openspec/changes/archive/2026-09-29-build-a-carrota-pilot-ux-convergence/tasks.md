## 1. Contract alignment (no domain close logic)

- [x] 1.1 Set today GET `primary_action` for `cash_difference` and `ready_to_close` to `kind` `request_close`, `label` `Revisar cierre`, `invocation` `review_surface`, `message` `cerrar el día`, `action_id` null. Do not mint `confirmation_token` on GET. Keep `cash_count_required` as `invocation` `composer` and `message` null
- [x] 1.2 Do not add tables, Alembic revisions, a second `operator_state` machine, exception acceptance, reopen, RF-009, or Build B. Do not edit onboarding files or the paused onboarding change

## 2. Inicio layout and compact current state

- [x] 2.1 Split Inicio so a compact header (eyebrow, greeting, `BusinessStreamPanel`) sits outside the transcript scroller. Header shows concise state, relevant totals, one next action. It must not fill the viewport. Transcript remains the main scrolling region and must stay independently scrollable
- [x] 2.2 Compact the panel from existing GET fields (idle copy, sales/tender lines, `Falta contar efectivo` / `Caja cuadrada` / `Faltante` / `Sobrante` / `Día cerrado`). Never render `primary_action.message` as copy. No `Confirmar cierre` on the panel. No KPI grid

## 3. Hoy structured day

- [x] 3.1 Load `GET /api/v1/business-stream/today` on Hoy visibility and after the same mutations as Inicio. Title `Así va {business_name} hoy`. Render summary, payment breakdown, closing status, coverage sentence. Reuse existing `operator_state` presentation
- [x] 3.2 Keep `Descargar Excel` and `Descargar CSV` below that summary. Remove Hoy's NBA-primary block and the `Cerrar el día` button. Hoy `Revisar cierre` uses the same silent review path as Inicio. Do not calculate totals on device

## 4. Daily Close review surface

- [x] 4.1 On `Revisar cierre`, inspect `/lumo/messages` persistence. Approved path: silent `POST /api/v1/lumo/messages` with the technical identifier, open the bottom sheet from server facts, do not append a merchant bubble, do not append `daily_close_preparation@1` to the visible transcript. If the message path would persist a visible merchant turn after reload, stop, report it, and use existing `POST /api/v1/lumo/actions` `closing.request@1` instead. Do not local-only hide. Do not invent a close workflow
- [x] 4.2 Sheet `Confirmar cierre` posts `closing.confirm@1` with the server token, closes the sheet, and reloads the today GET on Inicio and Hoy. Dismiss does not close. Preserve short/over confirm rules. Keep `Registrar conteo` as composer focus. Typed composer `cerrar el día` may keep the historical card path

## 5. Refresh and closed state

- [x] 5.1 Reload the today GET after sale commit, cash count, and close confirm. Closed Inicio and Hoy show `Día cerrado`, inspectable totals, and no stale `Registrar conteo` / `Revisar cierre` / `Confirmar cierre`

## 6. Automated tests

- [x] 6.1 Flutter: (A) `Revisar cierre` does not append visible merchant text; (B) does not create a duplicate preparation card in the transcript; (C) review surface receives a valid server confirmation token; (D) transcript reload still does not reveal synthetic `cerrar el día`; (E) `Confirmar cierre` uses `closing.confirm@1`; (F) successful close refreshes Inicio and Hoy; (G) compact current-state header remains visible while the transcript scrolls. Also: Hoy fields/coverage/exports; `Registrar conteo` composer focus; closed CTAs gone
- [x] 6.2 Backend: today GET `review_surface` payload (`message` `cerrar el día`, `action_id` null, no `confirmation_token`). No migration tests

## 7. Manual acceptance (Carrota)

- [x] 7.1 Walk scenarios 1–8: compact pinned stream; two-tender Hoy; matching next action; ready-to-close; review without fake bubble or duplicate card; review figures; confirm; closed state
- [x] 7.2 Confirm conversational sale still works. Confirm typed `cerrar el día` still has the historical path. Confirm Lovable-only mock features were not added. Do not run onboarding acceptance or archive any change
