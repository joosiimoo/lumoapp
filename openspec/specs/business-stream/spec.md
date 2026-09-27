# business-stream Specification

## Purpose

Server-owned read model for Inicio: today's operational responsibility, compact facts, one primary action, and the recorded-operations limitation sentence. `GET /api/v1/business-stream/today` composes from OperationalDay, `desired_open_type`, registered sales, current CashCount, ClosingSnapshot, and existing WorkItem/OutcomeRun ids. No LLM, no writes, no client-side state ranking.

`organizing` is part of the closed contract but is not currently merchant-reachable: the first confirmed sale creates the OperationalDay with `sale_count >= 1`. Do not add a merchant flow to reach `organizing`. `unavailable` is a data-fault state for automated tests, not a pilot walk state.

## Requirements

### Requirement: Today projection is a closed read
The system MUST expose `GET /api/v1/business-stream/today` for the authenticated tenant. Business-local today MUST be resolved on the server from the business IANA timezone. The route MUST NOT accept `business_id`, a date, or any other query parameter. An unknown query parameter MUST be HTTP 422 `VALIDATION_ERROR`. The route MUST NOT require `Idempotency-Key`. The JSON body MUST contain exactly `business_date`, `operator_state`, `close_progress`, `responsibility`, `detail`, `factual_summary`, `attention`, `primary_action`, `coverage`, and `as_of`. `operator_state` MUST be one of `no_active_day`, `organizing`, `cash_count_required`, `cash_difference`, `ready_to_close`, `closed`, or `unavailable`. `primary_action` MUST be null or one object, never an array. The body MUST NOT contain `reason_code`, outcome evidence, a confirmation token, `pending_count`, a WorkItem list, a percentage, or a completeness score. `as_of` MUST be the UTC time of that read.

#### Scenario: No query parameters
- **WHEN** the client calls `GET /api/v1/business-stream/today` with a `business_id` or `date` query parameter
- **THEN** the response MUST be HTTP 422 `VALIDATION_ERROR` and no OperationalDay MUST be created

#### Scenario: Empty today is still 200
- **WHEN** the tenant has no OperationalDay for business-local today
- **THEN** the GET MUST return HTTP 200 and `operator_state` `no_active_day`

### Requirement: Operator state follows the existing Daily Close predicate
The server MUST select `operator_state` from today's OperationalDay, `desired_open_type`, and ClosingSnapshot presence. It MUST NOT add a second priority table and MUST NOT call a model. No OperationalDay MUST yield `no_active_day` and `close_progress` `none`. A `closed` day with its ClosingSnapshot MUST yield `closed` and `close_progress` `completed`. A `closed` day missing that snapshot MUST yield `unavailable` and `close_progress` null. An open day whose desired type is `cash_count_required` MUST yield `cash_count_required` and `close_progress` `waiting`. Desired type `cash_difference_review` MUST yield `cash_difference` and `close_progress` `waiting`. Desired type `close_confirmation_required` MUST yield `ready_to_close` and `close_progress` `ready`. An open day whose desired type is null MUST yield `organizing` and `close_progress` `progressing`. That state is part of the closed contract and MUST be covered by automated tests. The first confirmed sale creates the OperationalDay with `sale_count` at least 1, so a merchant flow MUST NOT be required to produce `organizing`. A confirmed sale with no current CashCount MUST be `cash_count_required`, not `organizing`. Short and over MUST be `cash_difference`, not `ready_to_close`. The GET MUST NOT insert or repair a WorkItem or an OutcomeRun when the stored row is missing. Live day, sales, and cash facts MUST win over a stale stored outcome status.

#### Scenario: Uncounted sales ask for cash
- **WHEN** today is open, at least one sale is confirmed, and no current CashCount exists
- **THEN** `operator_state` MUST be `cash_count_required` and `close_progress` MUST be `waiting`

#### Scenario: A short count is not the confirm-first state
- **WHEN** today is open, expected cash is `22.50`, counted cash is `20.00`, and `cash_status` is `short`
- **THEN** `operator_state` MUST be `cash_difference` and `close_progress` MUST be `waiting`

#### Scenario: Balanced count is ready
- **WHEN** today is open, expected cash and counted cash are both `22.50`, and `cash_status` is `balanced`
- **THEN** `operator_state` MUST be `ready_to_close` and `close_progress` MUST be `ready`

#### Scenario: Open day with nothing to ask
- **WHEN** today has an open OperationalDay and `desired_open_type` is null
- **THEN** `operator_state` MUST be `organizing`, `close_progress` MUST be `progressing`, and `primary_action` MUST be null

### Requirement: Idle and unavailable invent no facts
`no_active_day` MUST set `responsibility` to `Cuando empiece la actividad, organizo el día.` and MUST set `detail`, `factual_summary`, `attention`, `primary_action`, and `coverage` to null. It MUST NOT report `sale_count` 0 or any zero money amount. `unavailable` MUST set `responsibility` to `No pude consultar el estado de hoy.` and MUST set those same five fields to null. Reading either state MUST NOT create an OperationalDay.

#### Scenario: Opening Inicio before any sale
- **WHEN** Carrota has no OperationalDay today and the merchant opens Inicio
- **THEN** the body MUST be `no_active_day`, the OperationalDay count for that business MUST be unchanged, and the body MUST NOT contain `0.00`

#### Scenario: A closed day without a snapshot
- **WHEN** today's OperationalDay is `closed` and no ClosingSnapshot exists for it
- **THEN** `operator_state` MUST be `unavailable` and `factual_summary` MUST be null

### Requirement: Open-day facts come from registered sales and the current count
For `organizing`, `cash_count_required`, `cash_difference`, and `ready_to_close`, `factual_summary.basis` MUST be `registered_sales`. `sale_count`, `gross_sales_total`, `cash_total`, `card_total`, and `transfer_total` MUST equal `summarize_day` for that day. `expected_cash` MUST equal that `cash_total`. When no current CashCount exists, `counted_cash` and `cash_difference` MUST be null and `cash_status` MUST be `not_counted`. When a current CashCount exists, `counted_cash`, `cash_difference`, and `cash_status` MUST be the server count, the server difference, and the server status. `closed_at` MUST be null. The gross amount MUST be the registered total, not a recomputation from ClosingSnapshot.

#### Scenario: One cash sale before the count
- **WHEN** the only confirmed sale today is `22.50` cash and no CashCount exists
- **THEN** `factual_summary.sale_count` MUST be 1, `gross_sales_total.amount` MUST be `22.50`, `expected_cash.amount` MUST be `22.50`, and `counted_cash` MUST be null

#### Scenario: Shortage numbers are server numbers
- **WHEN** expected cash is `22.50`, counted cash is `20.00`, and the server difference is `-2.50`
- **THEN** `factual_summary` MUST carry those three amounts and `cash_status` `short`

### Requirement: Closed facts come from the snapshot
For `closed`, `factual_summary.basis` MUST be `closing_snapshot`. Sale count, gross total, tender totals, expected cash, counted cash, difference, `cash_status`, and `closed_at` MUST equal that day's ClosingSnapshot. The GET MUST NOT replace those figures with a later live aggregation.

#### Scenario: Snapshot totals survive a later read
- **WHEN** today's day is `closed` and its ClosingSnapshot gross is `56.50`, expected cash is `22.50`, counted cash is `22.50`, and `cash_status` is `balanced`
- **THEN** `operator_state` MUST be `closed`, `factual_summary` MUST equal those snapshot figures, and `primary_action` MUST be null

### Requirement: Responsibility copy is scripted
The server MUST set `responsibility` and `detail` from the templates in this requirement. Amounts in the cash-count detail MUST use the existing `$` plus decimal-string formatter. Flutter and the LLM MUST NOT author these sentences. The strings MUST NOT contain `OutcomeRun`, `WorkItem`, `reason_code`, `orchestrator`, or `workflow engine`. They MUST NOT contain `Todas tus ventas`, `No falta ninguna venta`, `El día está completo`, `Todo quedó registrado`, or `No hubo más operaciones`.

- `organizing` responsibility: `Lumo está organizando el cierre`
- `organizing` detail: `Con lo registrado hasta ahora.`
- `cash_count_required` responsibility: `Necesito que registres el efectivo contado`
- `cash_count_required` detail: `Espero $<expected> en caja. Cuando termines, registra cuánto tienes para continuar con el cierre.`
- `cash_difference` responsibility: `Esperando tu revisión`
- `cash_difference` detail: null
- `cash_difference` attention why: `La diferencia queda visible. No indica por qué ocurrió.`
- `ready_to_close` responsibility: `Cierre listo para confirmar`
- `ready_to_close` detail: `Puedes revisarlo y confirmar el cierre.`
- `ready_to_close` attention why: `El cierre está listo para tu confirmación.`
- `cash_count_required` attention why: `Hace falta para continuar con el cierre.`
- `closed` responsibility: `Cierre completado`

`attention` MUST be null for `no_active_day`, `organizing`, `closed`, and `unavailable`. Otherwise `attention.actor` MUST be `merchant`. `attention.kind` MUST be `cash_count`, `cash_difference`, or `close_confirmation` for those three states respectively.

#### Scenario: Cash count names the expected amount
- **WHEN** expected cash is `22.50` and the state is `cash_count_required`
- **THEN** `responsibility` MUST be `Necesito que registres el efectivo contado` and `detail` MUST be `Espero $22.50 en caja. Cuando termines, registra cuánto tienes para continuar con el cierre.`

#### Scenario: Difference copy does not name a cause
- **WHEN** the state is `cash_difference`
- **THEN** `attention.why` MUST be `La diferencia queda visible. No indica por qué ocurrió.` and the body MUST NOT contain `robo`, `fraude`, or `venta perdida`

#### Scenario: Ready copy is proactive
- **WHEN** the state is `ready_to_close`
- **THEN** `responsibility` MUST be `Cierre listo para confirmar` and `attention.why` MUST be `El cierre está listo para tu confirmación.`

### Requirement: One primary action reuses the current close path
`primary_action` MUST be null unless `operator_state` is `cash_count_required`, `cash_difference`, or `ready_to_close`. `cash_count_required` MUST be kind `record_cash_count`, label `Registrar conteo`, invocation `composer`, `message` null, and `action_id` null. `cash_difference` and `ready_to_close` MUST be kind `request_close`, label `Revisar cierre`, invocation `message`, `message` `cerrar el día`, and `action_id` null. The label MUST NOT be `Cerrar el día`. The tap posts the message and MUST NOT close or confirm the day. The GET MUST NOT include `closing.request@1` or a `context_token`. `closing.request@1` stays the existing conversation-card action and MUST NOT be copied onto this payload. `closing.confirm@1` MUST remain on the existing Daily Close confirmation card only. The difference state MUST NOT add a recount control, a reason field, exception acceptance, or a close-with-difference action. `work_item_id` MUST be the open WorkItem of the desired type when that row exists and MUST be null when it does not. `outcome_run_id` MUST be the stored Daily Close run id when that row exists and MUST be null when it does not. The route MUST NOT register a new UI action id and MUST NOT register an inline cash-count action.

#### Scenario: Cash count has no posted action
- **WHEN** the state is `cash_count_required`
- **THEN** `primary_action.invocation` MUST be `composer`, `primary_action.action_id` MUST be null, and the body MUST NOT contain `closing.confirm@1`

#### Scenario: Ready exposes the existing request phrase
- **WHEN** the state is `ready_to_close` and the open WorkItem is `close_confirmation_required`
- **THEN** `primary_action.label` MUST be `Revisar cierre`, `primary_action.message` MUST be `cerrar el día`, `primary_action.action_id` MUST be null, and `primary_action.work_item_id` MUST equal that row

#### Scenario: Short uses the same close phrase
- **WHEN** the state is `cash_difference`
- **THEN** `primary_action.label` MUST be `Revisar cierre`, `primary_action.action_id` MUST be null, and the body MUST NOT include a recount action, a reason field, exception acceptance, or a close-with-difference action

### Requirement: Coverage is one limitation sentence
When an OperationalDay exists and `operator_state` is not `unavailable`, `coverage.limitation_code` MUST be `only_lumo_registered_operations` and `coverage.merchant_sentence` MUST be `Este cierre considera las operaciones registradas en Lumo.` The object MUST NOT include domains, sources, a percentage, a health score, or a complete flag. `no_active_day` and `unavailable` MUST set `coverage` to null. The GET MUST NOT insert or update a coverage row.

#### Scenario: A ready day still states the limitation
- **WHEN** the state is `ready_to_close` and sales coverage is `observed`
- **THEN** `coverage.merchant_sentence` MUST be `Este cierre considera las operaciones registradas en Lumo.` and the body MUST NOT contain a percentage

#### Scenario: Idle has no coverage claim
- **WHEN** the state is `no_active_day`
- **THEN** `coverage` MUST be null

### Requirement: The read writes nothing
`GET /api/v1/business-stream/today` MUST NOT insert or update an OperationalDay, WorkItem, OutcomeRun, CashCount, ClosingSnapshot, coverage row, or business event, and MUST NOT write audit, outbox, or idempotency. A second GET MUST return the same `operator_state` and the same `work_item_id` when a WorkItem was already open, and those row counts MUST be unchanged.

#### Scenario: Two opens write nothing
- **WHEN** the GET runs twice for an open day that already has one WorkItem and one OutcomeRun
- **THEN** both responses MUST return that `work_item_id`, and OperationalDay, WorkItem, OutcomeRun, audit, outbox, and idempotency counts MUST be unchanged

### Requirement: Another tenant cannot see this business
The GET MUST use the session tenant only. A caller for another business MUST NOT receive this business's `business_date` facts, totals, cash figures, or work item id.

#### Scenario: Tenant B does not see Carrota
- **WHEN** tenant B calls the GET while Carrota has a confirmed sale today
- **THEN** tenant B's body MUST NOT contain Carrota's gross total or Carrota's `work_item_id`

### Requirement: Inicio renders the projection without calculating
Flutter MUST request this GET when Inicio becomes visible and MUST render one panel from the body. The panel MUST show `responsibility` and, when present, `detail`, the factual amounts, one cash-status label, `attention.why`, `coverage.merchant_sentence`, and the single `primary_action`. `not_counted` MUST show `Falta contar efectivo`, `balanced` MUST show `Caja cuadrada`, `short` MUST show `Faltante`, and `over` MUST show `Sobrante`, taken from `cash_status`. Sale count display MUST use `1 venta` when `sale_count` is 1 and `{n} ventas` otherwise. Flutter MUST NOT sum tenders, subtract cash, choose `operator_state`, choose `close_progress`, or invent a second action. It MUST NOT display `work_item_id`, `outcome_run_id`, `limitation_code`, or the forbidden architecture words. `record_cash_count` MUST only focus the existing composer. `request_close` MUST `POST /api/v1/lumo/messages` with `cerrar el día` on the existing shell `conversation_id` and MUST NOT `POST /api/v1/lumo/actions` from the panel. After a successful message or action POST from that Inicio conversation, Flutter MUST request the GET again. A transport failure MUST replace the panel with `No pude consultar el estado de hoy.` and a retry control, and MUST NOT keep the previous factual summary.

#### Scenario: Shortage label is not computed on device
- **WHEN** the panel receives `cash_status` `short` and `cash_difference.amount` `-2.50`
- **THEN** it MUST show `Faltante` and `-2.50` and MUST NOT compute `20.00 − 22.50`

#### Scenario: Ready tap reuses the phrase
- **WHEN** the merchant taps `Revisar cierre` on the panel
- **THEN** the client MUST post `cerrar el día` on the existing shell `conversation_id` and MUST NOT post `/api/v1/lumo/actions` from the panel

#### Scenario: Failed refresh is not success
- **WHEN** the GET fails after Inicio had shown a closed summary
- **THEN** the panel MUST show `No pude consultar el estado de hoy.` and MUST NOT keep that closed summary

#### Scenario: Singular sale count copy
- **WHEN** the panel receives `factual_summary.sale_count` 1
- **THEN** it MUST display `1 venta` and MUST NOT display `1 ventas`

### Requirement: The panel is not a second Memoria or a dashboard
The panel MUST sit on Inicio below the existing greeting and above the conversation, and MUST keep `Buenos días` and `LumoComposer`. It MUST NOT add a Generative UI component, a sale list, a chart, a KPI grid, a POS keypad, suggestion chips, or a business-event timeline. Page load MUST NOT emit `operational_day_summary@1`, `daily_close_preparation@1`, `daily_close_confirmed@1`, or `next_best_action@1`. Hoy and Memoria MUST stay unchanged. The panel MUST NOT show `Confirmar cierre`.

#### Scenario: Open does not emit a conversation card
- **WHEN** the merchant opens Inicio and does not send a message
- **THEN** the client MUST NOT post a message solely to paint the panel, and the conversation MUST NOT gain a summary or close card from that load

#### Scenario: Confirm stays on the existing card
- **WHEN** the panel state is `ready_to_close`
- **THEN** the panel MUST NOT render `Confirmar cierre`

### Requirement: No background proactivity
This capability MUST NOT add push notifications, a scheduler, a background job, email, or WhatsApp. Proactivity MUST be limited to the panel returned when Inicio is opened or refreshed.

#### Scenario: No reminder worker
- **WHEN** the application process list and route table are inspected
- **THEN** this change MUST NOT add a reminder scheduler or a notification route
