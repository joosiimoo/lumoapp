## MODIFIED Requirements

### Requirement: One primary action reuses the current close path
`primary_action` MUST be null unless `operator_state` is `cash_count_required`, `cash_difference`, or `ready_to_close`. `cash_count_required` MUST be kind `record_cash_count`, label `Registrar conteo`, invocation `composer`, `message` null, and `action_id` null. `cash_difference` and `ready_to_close` MUST be kind `request_close`, label `Revisar cierre`, invocation `review_surface`, `message` exactly `cerrar el día`, and `action_id` null. That `message` is a technical identifier only: Flutter MUST NOT render it as a merchant bubble, a visible CTA label, or conversational text. The visible label MUST be `Revisar cierre` and MUST NOT be `Cerrar el día`. The GET MUST NOT mint `confirmation_token`, MUST NOT include `closing.confirm@1`, and MUST NOT mutate in order to attach an action token. `action_id` MUST remain null unless a valid server-issued action token already exists without mutating this GET. The tap MUST run the silent `request_close` path specified by `mobile-shell` and MUST NOT close or confirm the day. The GET MUST NOT include a Generative UI card. The difference state MUST NOT add a recount control, a reason field, exception acceptance, or a close-with-difference action. `work_item_id` MUST be the open WorkItem of the desired type when that row exists and MUST be null when it does not. `outcome_run_id` MUST be the stored Daily Close run id when that row exists and MUST be null when it does not. The route MUST NOT register a new UI action id and MUST NOT register an inline cash-count action.

#### Scenario: Cash count has no posted action
- **WHEN** the state is `cash_count_required`
- **THEN** `primary_action.invocation` MUST be `composer`, `primary_action.message` MUST be null, `primary_action.action_id` MUST be null, and the body MUST NOT contain `closing.confirm@1`

#### Scenario: Ready exposes review, not a visible phrase
- **WHEN** the state is `ready_to_close` and the open WorkItem is `close_confirmation_required`
- **THEN** `primary_action` MUST be `kind` `request_close`, `label` `Revisar cierre`, `invocation` `review_surface`, `message` `cerrar el día`, `action_id` null, and `work_item_id` MUST equal that row, and the body MUST NOT contain `confirmation_token`

#### Scenario: Short uses the same review control
- **WHEN** the state is `cash_difference`
- **THEN** `primary_action` MUST be `kind` `request_close`, `label` `Revisar cierre`, `invocation` `review_surface`, `message` `cerrar el día`, `action_id` null, and the body MUST NOT include a recount action, a reason field, exception acceptance, `confirmation_token`, or a close-with-difference action

### Requirement: Inicio renders the projection without calculating
Flutter MUST request this GET when Inicio becomes visible and MUST render one current-state panel from the body, outside the conversation transcript. The panel MUST use compact presentation of existing fields: `operator_state` / `cash_status` labels, sale count, gross total, tender totals when `factual_summary` is present, expected/counted/difference when present, and the single `primary_action`. `not_counted` MUST show `Falta contar efectivo`, `balanced` MUST show `Caja cuadrada`, `short` MUST show `Faltante`, `over` MUST show `Sobrante`, and `closed` MUST show `Día cerrado`, taken from server state. Sale count display MUST use `1 venta` when `sale_count` is 1 and `{n} ventas` otherwise. Flutter MUST NOT sum tenders, subtract cash, choose `operator_state`, choose `close_progress`, or invent a second action. It MUST NOT display `work_item_id`, `outcome_run_id`, `limitation_code`, or architecture words. `record_cash_count` MUST only focus the existing composer. `request_close` MUST silent-run existing `request_close` via `POST /api/v1/lumo/messages` with `primary_action.message`, then open the review surface, and MUST NOT insert a merchant bubble `cerrar el día`. After a successful message or action from that Inicio conversation, and after a successful close confirm from the review surface, Flutter MUST request the GET again. A transport failure MUST replace the panel with `No pude consultar el estado de hoy.` and a retry control, and MUST NOT keep the previous factual summary.

#### Scenario: Shortage label is not computed on device
- **WHEN** the panel receives `cash_status` `short` and `cash_difference.amount` `-2.50`
- **THEN** it MUST show `Faltante` and `-2.50` and MUST NOT compute `20.00 − 22.50`

#### Scenario: Ready tap does not fake a merchant utterance
- **WHEN** the merchant taps `Revisar cierre` on the panel
- **THEN** the client MUST silent-post `request_close` with `primary_action.message`, MUST open the Daily Close review surface, and MUST NOT append a user turn whose text is `cerrar el día`

#### Scenario: Failed refresh is not success
- **WHEN** the GET fails after Inicio had shown a closed summary
- **THEN** the panel MUST show `No pude consultar el estado de hoy.` and MUST NOT keep that closed summary

#### Scenario: Singular sale count copy
- **WHEN** the panel receives `factual_summary.sale_count` 1
- **THEN** it MUST display `1 venta` and MUST NOT display `1 ventas`

#### Scenario: Closed current state has no close CTA
- **WHEN** the panel receives `operator_state` `closed`
- **THEN** it MUST show `Día cerrado` and MUST NOT show `Registrar conteo`, `Revisar cierre`, or `Confirmar cierre`

### Requirement: The panel is not a second Memoria or a dashboard
The current-state panel MUST sit on Inicio below the existing greeting and above the conversation, in a compact region that is not a chat turn and that remains visible without scrolling the transcript. It MUST expose concise current state, relevant totals, and one next action when `primary_action` is present. It MUST NOT consume most of the viewport, MUST NOT become a dashboard, and MUST keep `Buenos días` and `LumoComposer`. The independently scrolling transcript MUST remain the main content region below it. It MUST NOT add a Generative UI component, a sale list, a chart, a KPI grid, a POS keypad, suggestion chips, or a business-event timeline. Page load MUST NOT emit `operational_day_summary@1`, `daily_close_preparation@1`, `daily_close_confirmed@1`, or `next_best_action@1`. The panel MUST NOT show `Confirmar cierre`. Conversational sale cards remain in the transcript only.

#### Scenario: Open does not emit a conversation card
- **WHEN** the merchant opens Inicio and does not send a message
- **THEN** the client MUST NOT post a message solely to paint the panel, and the conversation MUST NOT gain a summary or close card from that load

#### Scenario: Confirm stays off the current-state panel
- **WHEN** the panel state is `ready_to_close`
- **THEN** the panel MUST NOT render `Confirmar cierre`

#### Scenario: Transcript growth does not hide current state
- **WHEN** the Inicio transcript contains many sale cards and the merchant is on Inicio
- **THEN** the current-state panel MUST remain visible without scrolling through those cards

#### Scenario: Return to Inicio shows current state
- **WHEN** the merchant leaves Inicio and returns
- **THEN** the current-state panel MUST be visible near the top without requiring a scroll through historical messages

## ADDED Requirements

### Requirement: Hoy reads the same today projection
Hoy MUST request `GET /api/v1/business-stream/today` when the tab becomes visible and after the same mutations that refresh Inicio current state. Hoy MUST present a structured daily view titled `Así va {business_name} hoy` using session business name. It MUST show, when present on the body: confirmed `sale_count`, `gross_sales_total`, `cash_total`, `card_total`, `transfer_total`, close state, expected cash, counted cash, difference, `primary_action`, and `coverage` merchant sentence. It MUST keep the existing Excel and CSV export actions. It MUST NOT calculate those amounts. It MUST NOT become a chart dashboard. It MUST reuse `operator_state` values already defined by this capability. `no_active_day` MUST NOT invent `0.00` sales. Closed Hoy MUST keep final totals inspectable and MUST NOT show a stale close CTA.

#### Scenario: Two tenders appear as server splits
- **WHEN** Hoy receives `sale_count` 2, `gross_sales_total.amount` `52.50`, `cash_total.amount` `22.50`, `card_total.amount` `30.00`, and `transfer_total.amount` `0.00`
- **THEN** Hoy MUST display those five server values and MUST NOT add `22.50` and `30.00` to produce `52.50`

#### Scenario: Cash count next action matches Inicio
- **WHEN** the GET `operator_state` is `cash_count_required` and `primary_action.label` is `Registrar conteo`
- **THEN** Hoy MUST communicate that same next action and MUST NOT show `Cerrar el día`

#### Scenario: Coverage limitation is explicit
- **WHEN** the GET includes coverage for an open or closed day
- **THEN** Hoy MUST show `Este cierre considera las operaciones registradas en Lumo.`
