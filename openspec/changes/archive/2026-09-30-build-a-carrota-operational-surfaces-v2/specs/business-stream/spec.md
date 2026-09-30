## MODIFIED Requirements

### Requirement: Inicio renders the projection without calculating
Flutter MUST request `GET /api/v1/business-stream/today` when Inicio becomes visible and MUST render a light operational header from the body, outside the conversation transcript. The header MUST contain: (1) one short operational sentence, and (2) at most two informative indicator cards when `factual_summary` is present. The short sentence MUST use the display template `Llevas $<gross_sales_total.amount> en ventas.` when `factual_summary` is present, formatting the server amount with the existing `$` plus decimal-string formatter. When `operator_state` is `no_active_day`, the sentence MUST be server `responsibility` and MUST NOT invent `0.00`. Indicator card VENTAS HOY MUST show server `gross_sales_total` and `sale_count`. Indicator card CAJA MUST show server `expected_cash` when present and a concise cash-state label from server `cash_status` / `operator_state`: `not_counted` → `Falta contar`; `balanced` → `Caja cuadrada`; `short` → `Faltante`; `over` → `Sobrante`; `closed` → `Día cerrado`. Sale count display MUST use `1 venta` when `sale_count` is 1 and `{n} ventas` otherwise. Inicio MUST NOT render the large multi-line Business Stream operational card, tender breakdown, expected/counted/difference detail lines, or `primary_action`. Inicio MUST NOT expose `Preparar el cierre del día`, `Registrar conteo`, `Revisar cierre`, `Confirmar cierre`, or `Cerrar el día`. Flutter MUST NOT sum tenders, subtract cash, choose `operator_state`, choose `close_progress`, infer close eligibility, or invent a cash status. It MUST NOT display `work_item_id`, `outcome_run_id`, `limitation_code`, or architecture words. After a successful message or action from the Inicio conversation, and after a successful close confirm from the Hoy close workspace, Flutter MUST request the GET again. A transport failure MUST replace the light header with `No pude consultar el estado de hoy.` and a retry control, and MUST NOT keep the previous factual summary.

#### Scenario: Short sales sentence uses server gross
- **WHEN** Inicio receives `factual_summary.gross_sales_total.amount` `2430.00`
- **THEN** it MUST show `Llevas $2430.00 en ventas.` (or the equivalent formatted server decimal) and MUST NOT recompute the total

#### Scenario: Ventas hoy indicator shows total and count
- **WHEN** Inicio receives `sale_count` 3 and `gross_sales_total.amount` `52.50`
- **THEN** the VENTAS HOY indicator MUST show those server values and MUST display `3 ventas`

#### Scenario: Caja indicator shows server cash state
- **WHEN** Inicio receives `cash_status` `not_counted` and `expected_cash.amount` `22.50`
- **THEN** the CAJA indicator MUST show expected `22.50` and label `Falta contar`, and MUST NOT compute a difference

#### Scenario: Inicio has no close CTA
- **WHEN** Inicio receives `operator_state` `ready_to_close` with a non-null `primary_action`
- **THEN** Inicio MUST NOT show `Preparar el cierre del día`, `Registrar conteo`, `Revisar cierre`, `Confirmar cierre`, or `Cerrar el día`

#### Scenario: Failed refresh is not success
- **WHEN** the GET fails after Inicio had shown a closed summary
- **THEN** the light header MUST show `No pude consultar el estado de hoy.` and MUST NOT keep that closed summary

#### Scenario: Singular sale count copy
- **WHEN** the header receives `factual_summary.sale_count` 1
- **THEN** it MUST display `1 venta` and MUST NOT display `1 ventas`

#### Scenario: Closed current state has no close CTA
- **WHEN** the header receives `operator_state` `closed`
- **THEN** the CAJA indicator MUST show `Día cerrado` and Inicio MUST NOT show close CTAs

### Requirement: The panel is not a second Memoria or a dashboard
The light operational header MUST sit on Inicio below the existing greeting and above the conversation, in a compact region that is not a chat turn and that remains visible without scrolling the transcript. It MUST expose only the short sentence and the two indicator cards when facts exist. It MUST NOT consume most of the viewport, MUST NOT become a dashboard, and MUST keep `Buenos días` and `LumoComposer`. The independently scrolling transcript MUST remain the main content region below it. It MUST NOT add a Generative UI component, a sale list, a chart, a KPI grid, a POS keypad, suggestion chips, inventory, top products, comparisons, forecasting, or a business-event timeline. Page load MUST NOT emit `operational_day_summary@1`, `daily_close_preparation@1`, `daily_close_confirmed@1`, or `next_best_action@1`. Conversational sale cards remain in the transcript only.

#### Scenario: Open does not emit a conversation card
- **WHEN** the merchant opens Inicio and does not send a message
- **THEN** the client MUST NOT post a message solely to paint the header, and the conversation MUST NOT gain a summary or close card from that load

#### Scenario: Confirm stays off Inicio
- **WHEN** the today GET state is `ready_to_close`
- **THEN** Inicio MUST NOT render `Cerrar el día` or `Confirmar cierre` as operator chrome

#### Scenario: Transcript growth does not hide current state
- **WHEN** the Inicio transcript contains many sale cards and the merchant is on Inicio
- **THEN** the light operational header MUST remain visible without scrolling through those cards

#### Scenario: Return to Inicio shows current state
- **WHEN** the merchant leaves Inicio and returns
- **THEN** the light operational header MUST be visible near the top without requiring a scroll through historical messages

### Requirement: One primary action reuses the current close path
`primary_action` MUST be null unless `operator_state` is `cash_count_required`, `cash_difference`, or `ready_to_close`. For those three states, `primary_action` MUST be `kind` `prepare_daily_close`, `label` `Preparar el cierre del día`, `invocation` `close_workspace`, `message` null, and `action_id` null. The GET MUST NOT mint `confirmation_token`, MUST NOT include `closing.confirm@1`, and MUST NOT mutate in order to attach an action token. The visible label MUST be `Preparar el cierre del día` and MUST NOT be `Registrar conteo`, `Revisar cierre`, or `Cerrar el día`. The GET MUST NOT include a Generative UI card. The difference state MUST NOT add a recount control, a reason field, exception acceptance, or a close-with-difference action on the GET body. `work_item_id` MUST be the open WorkItem of the desired type when that row exists and MUST be null when it does not. `outcome_run_id` MUST be the stored Daily Close run id when that row exists and MUST be null when it does not.

#### Scenario: Cash count exposes prepare-close workspace
- **WHEN** the state is `cash_count_required`
- **THEN** `primary_action` MUST be `kind` `prepare_daily_close`, `label` `Preparar el cierre del día`, `invocation` `close_workspace`, `message` null, `action_id` null

#### Scenario: Ready exposes prepare-close, not Revisar cierre
- **WHEN** the state is `ready_to_close`
- **THEN** `primary_action.label` MUST be `Preparar el cierre del día` and MUST NOT be `Revisar cierre`

#### Scenario: Short uses the same prepare-close control
- **WHEN** the state is `cash_difference`
- **THEN** `primary_action` MUST be `kind` `prepare_daily_close`, `invocation` `close_workspace`, and the body MUST NOT include a recount action, exception acceptance, or `confirmation_token`

### Requirement: Hoy reads the same today projection
Hoy MUST request `GET /api/v1/business-stream/today` when the tab becomes visible and after the same mutations that refresh Inicio current state. Hoy MUST present a structured daily view titled `Así va {business_name} hoy` using session business name. It MUST show, when present on the body: confirmed `sale_count`, `gross_sales_total`, `cash_total`, `card_total`, `transfer_total`, close state figures, and `coverage` merchant sentence. When `primary_action.kind` is `prepare_daily_close`, Hoy MUST show `Preparar el cierre del día` with supporting copy `Confirma efectivo y revisa pendientes` and MUST open the close workspace on tap. Hoy MUST NOT show `Registrar conteo` or `Revisar cierre` as the operator progression. It MUST keep the existing Excel and CSV export actions below operational/close content. It MUST NOT calculate amounts. It MUST NOT become a chart dashboard. `no_active_day` MUST NOT invent `0.00` sales. Closed Hoy MUST keep final totals inspectable and MUST NOT show a stale close CTA.

#### Scenario: Two tenders appear as server splits
- **WHEN** Hoy receives `sale_count` 2, `gross_sales_total.amount` `52.50`, `cash_total.amount` `22.50`, `card_total.amount` `30.00`, and `transfer_total.amount` `0.00`
- **THEN** Hoy MUST display those five server values and MUST NOT add `22.50` and `30.00` to produce `52.50`

#### Scenario: Prepare-close only from Hoy
- **WHEN** the GET `operator_state` is `cash_count_required` and `primary_action.label` is `Preparar el cierre del día`
- **THEN** Hoy MUST show that action and Inicio MUST NOT show it

#### Scenario: Coverage limitation is explicit
- **WHEN** the GET includes coverage for an open or closed day
- **THEN** Hoy MUST show `Este cierre considera las operaciones registradas en Lumo.`

#### Scenario: Closed state has no CTA
- **WHEN** Hoy receives `operator_state` `closed`
- **THEN** Hoy MUST show `Día cerrado` with final server totals and MUST NOT show `Preparar el cierre del día`, `Registrar conteo`, `Revisar cierre`, or `Cerrar el día`
