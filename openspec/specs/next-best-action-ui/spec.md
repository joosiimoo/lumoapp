# next-best-action-ui Specification

## Purpose

Hoy shows the current operational day from the business-stream today projection. Inicio renders next_best_action version 1 for a typed qué sigue turn.

## Requirements
### Requirement: Hoy shows one next step and the pending count
Hoy MUST NOT use `GET /api/v1/operational-days/current/next-best-action` as its primary body. Hoy MUST show the Business Stream today projection as specified in `business-stream`, including the single prepare-close entry when present. When that projection has no `primary_action`, Hoy MUST omit closing CTAs. When `pending_count` semantics exist only on the NBA GET, Hoy MUST NOT require a pendientes line or invent a count from the supporting copy `Confirma efectivo y revisa pendientes`. Hoy MUST NOT render a WorkItem list, a chart, a hero analytics metric, a day picker, or a separate closing-flow screen outside the Hoy prepare-close workspace. Memoria and Negocio MUST stay unchanged aside from close-note display rules owned by `memoria-timeline`.

#### Scenario: After close the closing CTA is gone
- **WHEN** today's day is `closed` and the merchant opens Hoy
- **THEN** Hoy MUST show the closed daily summary and MUST NOT show `Preparar el cierre del día`, `Revisar cierre`, `Confirmar cierre`, or `Cerrar el día`

### Requirement: Hoy does not calculate money or priority
Hoy MUST display server strings and server amounts from `GET /api/v1/business-stream/today`. It MUST NOT format evidence amounts into NBA sentences, MUST NOT subtract counted cash from expected cash, MUST NOT choose which WorkItem is next, and MUST NOT invent a priority.

#### Scenario: Shortage copy is server state
- **WHEN** the today GET `cash_status` is `short` and `cash_difference.amount` is `-2.50`
- **THEN** Hoy MUST show `Faltante` and `-2.50` and MUST NOT compute `20.00 − 22.50`

### Requirement: Hoy starts close through the existing phrase
When today `primary_action.kind` is `prepare_daily_close`, Hoy MUST show `Preparar el cierre del día` and MUST open the close workspace (`invocation` `close_workspace`). It MUST NOT show `Cerrar el día` as the Hoy chrome primary label, MUST NOT show `Registrar conteo` or `Revisar cierre` as the operator progression, and MUST NOT append a visible merchant bubble. When `primary_action` is null, Hoy MUST NOT show a close control. Inicio MUST NOT mirror the operator CTA.

#### Scenario: Prepare-close opens workspace
- **WHEN** the merchant taps `Preparar el cierre del día` on Hoy for an open close-eligible day
- **THEN** the client MUST open the close workspace and MUST NOT navigate to Inicio for cash count entry

#### Scenario: Count action is not a separate Hoy CTA
- **WHEN** the today GET state is `cash_count_required`
- **THEN** Hoy MUST show `Preparar el cierre del día` and MUST NOT show a standalone `Registrar conteo` button

### Requirement: Register next_best_action@1
`GenerativeUIRegistry` MUST register component `next_best_action` version `1`. The composer MUST emit it only for a completed `operational_day.next_best_action@1` turn whose projection is not null. `data` MUST carry the projection fields. `fallback_text` MUST be `title`, a space, and `reason`, and MUST NOT contain a token. `actions` MUST be empty for `cash_count_required` and exactly `closing.request@1` for `cash_difference_review` and `close_confirmation_required`. That Inicio action MUST carry the existing `typ=ui_action` `context_token` used by `daily_close_preparation@1`. The GET payload MUST NOT include that token. The card MUST NOT emit `closing.confirm@1`. A null projection MUST emit no component. `closing_ready_card` and `cash_difference_card` MUST stay unregistered.

#### Scenario: Inicio card for a shortage
- **WHEN** the actor posts `qué sigue` and the projection type is `cash_difference_review`
- **THEN** the response `ui` MUST include one `next_best_action` version `1` whose only action is `closing.request@1` and whose `fallback_text` contains the server shortage title

#### Scenario: No action emits no card
- **WHEN** the actor posts `qué sigue` and the projection is null
- **THEN** `ui` MUST be empty and `text` MUST be `No hay un paso pendiente para el cierre de hoy.`

### Requirement: Flutter renders next_best_action@1
`GenerativeUIRenderer` MUST register `next_best_action` version `1`. It MUST show the server `title` and `reason` in the Inicio stream with the existing Lumo-mark gutter and card. It MUST render `Revisar cierre` only for `closing.request@1` on that card and MUST post that action through the existing actions endpoint. It MUST NOT label that control `Cerrar el día`. It MUST NOT render an amount field, a dismiss control, or a WorkItem list. An unknown version MUST show `fallback_text` and MUST NOT run actions. When response `text` equals `fallback_text`, the stream MUST show the card and MUST NOT also show that sentence as a second prose block.

#### Scenario: Renderer does not recompute the shortage
- **WHEN** the renderer receives `next_best_action` version `1` with a short title that already contains `$14.00`
- **THEN** it MUST show that title and MUST NOT derive the amount from `evidence`

#### Scenario: Unknown version
- **WHEN** the payload is `next_best_action` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT run its actions

### Requirement: Conversational NBA on Inicio is unchanged in role
`next_best_action` version `1` on Inicio remains the artifact for a typed `qué sigue` (or equivalent) turn. That card MUST NOT become Hoy's primary layout. If that Inicio card still emits `closing.request@1`, any visible button on a newly rendered card SHOULD use `Revisar cierre` rather than `Cerrar el día`, and MUST NOT be required for the operator review-surface path.

#### Scenario: Qué sigue still has a card path
- **WHEN** the actor posts `qué sigue` and the projection type is `close_confirmation_required`
- **THEN** Inicio MAY show `next_best_action` version `1` in the transcript and Hoy MUST still be the structured daily summary
