# next-best-action Specification

## Purpose

A pure read of the stored open Daily Close WorkItem. The projection is not a persisted row.

## Requirements
### Requirement: Next Best Action is a projection
The system MUST derive at most one Next Best Action from open Daily Close WorkItems for today's OperationalDay. It MUST NOT persist a `next_best_actions` row. The chosen row MUST be the open item with the best rank: `cash_count_required`, then `cash_difference_review`, then `close_confirmation_required`. The projection MUST include `work_item_id`, `operational_day_id`, `outcome_type` equal to `daily_close_ready`, `outcome_run_id`, `type`, `title`, `reason`, `expected_result`, `priority`, `responsible_party`, `evidence`, `risk`, `reversible`, `expires_at` null, and `status` `open`. `outcome_run_id` MUST equal the chosen WorkItem's `outcome_run_id`, including null when that column is null. `risk` MUST be `blocks_close` for a count item, `visible_difference` for a difference item, and `requires_confirmation` for a close item. `reversible` MUST be true for a count item and a difference item, and false for a close item. No recommendation or insight type MAY outrank these rows. `pending_count` MUST be the number of open WorkItems already stored for that day. The projection MUST NOT insert, update, or resolve a WorkItem and MUST NOT insert or update an OutcomeRun. In the normal Build A flow that count MUST be 1 when today's open day has confirmed sales, and 0 when there is no day, the day has no confirmed sales, or the day is closed. Title, reason, expected result, and actions MUST stay the templates and action ids already required by this capability.

#### Scenario: Short cash selects the difference
- **WHEN** the only open row is `cash_difference_review`
- **THEN** the projection `type` MUST be `cash_difference_review`, `priority` MUST be `high`, `pending_count` MUST be 1, and `outcome_run_id` MUST equal that row's `outcome_run_id`

#### Scenario: Balanced cash selects close
- **WHEN** the only open row is `close_confirmation_required`
- **THEN** the projection `type` MUST be `close_confirmation_required`, `priority` MUST be `normal`, and `pending_count` MUST be 1

#### Scenario: No action
- **WHEN** today has no OperationalDay, the day is `closed`, or the open day has no confirmed sales
- **THEN** the projection MUST be null and `pending_count` MUST be 0

#### Scenario: Copy and actions stay the same
- **WHEN** expected cash is `94.00` and no count exists
- **THEN** `title` MUST be `Cuenta el efectivo para continuar con el cierre.` and `actions` MUST be empty

### Requirement: Merchant copy is templated from server facts
The server MUST build `title`, `reason`, and `expected_result` from the templates below. Amounts MUST use the existing `$` plus decimal-string formatter. Short and over titles MUST use the absolute difference. Evidence MUST keep the signed difference. The reason MUST say `las ventas registradas en Lumo` wherever it cites expected cash from sales. The copy MUST NOT say that all sales are complete. Flutter and the LLM MUST NOT author these sentences.

- Count title: `Cuenta el efectivo para continuar con el cierre.`
- Count reason: `Esperamos $<expected> en efectivo y todavía no hay un conteo.`
- Count expected result: `Un conteo de efectivo queda registrado para esta jornada.`
- Balanced title: `La caja está cuadrada. El siguiente paso es cerrar la jornada.`
- Balanced reason: `El efectivo contado coincide con los $<expected> esperados de las ventas registradas en Lumo.`
- Balanced expected result: `La jornada queda cerrada.`
- Short title: `Hay un faltante de $<absolute difference>. Revisa la diferencia antes de confirmar el cierre.`
- Over title: `Hay un sobrante de $<absolute difference>. Revisa la diferencia antes de confirmar el cierre.`
- Short or over reason: `El conteo es $<counted> y las ventas registradas en Lumo esperan $<expected> en efectivo.`
- Short or over expected result: `Puedes volver a contar o confirmar el cierre con esta diferencia visible.`

#### Scenario: Missing count names the expected cash
- **WHEN** expected cash is `94.00` and no count exists
- **THEN** `title` MUST be `Cuenta el efectivo para continuar con el cierre.` and `reason` MUST be `Esperamos $94.00 en efectivo y todavía no hay un conteo.`

#### Scenario: Shortage uses the server amount
- **WHEN** expected cash is `94.00`, counted cash is `80.00`, and `cash_status` is `short`
- **THEN** `title` MUST be `Hay un faltante de $14.00. Revisa la diferencia antes de confirmar el cierre.` and `reason` MUST contain `las ventas registradas en Lumo` and `$94.00`

#### Scenario: Overage uses the server amount
- **WHEN** expected cash is `94.00`, counted cash is `104.00`, and `cash_status` is `over`
- **THEN** `title` MUST be `Hay un sobrante de $10.00. Revisa la diferencia antes de confirmar el cierre.`

#### Scenario: Balanced asks to close
- **WHEN** expected cash and counted cash are both `94.00`
- **THEN** `title` MUST be `La caja está cuadrada. El siguiente paso es cerrar la jornada.`

### Requirement: Current Next Best Action read
The API MUST expose `GET /api/v1/operational-days/current/next-best-action` for the authenticated tenant. The body MUST be `operational_day_id`, `day_status`, `pending_count`, and `next_best_action`. A missing day MUST return `200` with `operational_day_id` null, `day_status` null, `pending_count` 0, and `next_best_action` null. It MUST NOT return `404` for that empty case. The route MUST NOT require `Idempotency-Key`. It MUST NOT insert, update, or resolve a WorkItem, MUST NOT insert or update an OutcomeRun, and MUST NOT write audit, outbox, or idempotency. When the action is a difference or close item, `actions` MUST be exactly one object `{ "action_id": "closing.request@1" }` and MUST NOT include a `context_token`. A count item MUST have empty `actions`. The route MUST NOT mint a closing confirmation token. A second read MUST return the same `work_item_id` and MUST leave every WorkItem column and every OutcomeRun column unchanged.

#### Scenario: Hoy can read the count action
- **WHEN** the tenant has confirmed sales today and no cash count
- **THEN** `GET /api/v1/operational-days/current/next-best-action` MUST return `200`, `type` `cash_count_required`, and empty `actions`

#### Scenario: Empty today is not a missing resource
- **WHEN** the tenant has no OperationalDay today
- **THEN** the GET MUST return `200` and `next_best_action` null

#### Scenario: Two GETs write nothing
- **WHEN** the GET runs twice for an open day that already has one WorkItem and one OutcomeRun
- **THEN** both responses MUST return that same `work_item_id` and `outcome_run_id`, and WorkItem, OutcomeRun, and audit row counts MUST be unchanged

#### Scenario: Short and over each count as one job
- **WHEN** the only open row is `cash_difference_review` for a short day, and later for an over day
- **THEN** each response MUST have `pending_count` 1

### Requirement: Read tool operational_day.next_best_action@1
`ToolRegistry` MUST register `operational_day.next_best_action@1` with empty input, permission `sale.create`, policy `NBA-001`, `side_effect=read`, and `requires_idempotency=false`. The message path MUST NOT insert an idempotency row for it and MUST NOT write a WorkItem, an OutcomeRun, or an audit row. `NBA-001` MUST allow only an empty argument object and MUST deny a model-supplied work item id, outcome run id, type, priority, amount, or operational day id. The tool MUST call the same pure query as the GET. Assistant `text` MUST equal the projection `fallback_text` when an action exists, and that text MUST be the `title`, a space, and the `reason`. When the projection is null, `text` MUST be `No hay un paso pendiente para el cierre de hoy.` and `ui` MUST be empty. The orchestrator MUST NOT replace the title, reason, amounts, or priority with model output.

#### Scenario: Model amounts are rejected
- **WHEN** policy evaluates `operational_day.next_best_action@1` with a model argument `expected_cash` or `priority`
- **THEN** the decision MUST be `deny` under `NBA-001` and no WorkItem or OutcomeRun MUST be written from those arguments

#### Scenario: Server copy wins
- **WHEN** the tool runs for a day with expected cash `94.00` and no count
- **THEN** the assistant text MUST contain `Esperamos $94.00` and MUST NOT contain an amount supplied only by the model

#### Scenario: Two tool reads write nothing
- **WHEN** `operational_day.next_best_action@1` runs twice for the same open WorkItem
- **THEN** both responses MUST return that `work_item_id`, and WorkItem, OutcomeRun, audit, and idempotency row counts MUST be unchanged

### Requirement: No WorkItem collection API
This slice MUST NOT add `GET /api/v1/operational-days/current/work-items` or any other merchant WorkItem list or history route. Resolved rows MUST remain readable to the owning tenant through the database.

#### Scenario: List route is absent
- **WHEN** the API route table is inspected
- **THEN** it MUST NOT contain a work-items collection route
