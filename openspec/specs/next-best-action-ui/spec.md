# next-best-action-ui Specification

## Purpose

Hoy shows the server next step above the export panel. Inicio renders next_best_action version 1.

## Requirements
### Requirement: Hoy shows one next step and the pending count
Hoy MUST request `GET /api/v1/operational-days/current/next-best-action` when the tab becomes visible. When `next_best_action` is not null, Hoy MUST show the label `Próximo paso`, the server `title`, and the server `reason` inside the existing max-width 420px column and an existing card style. When `pending_count` is 1, it MUST show `1 pendiente`. It MUST NOT show `2 pendientes` for a short or over day. When `next_best_action` is null, it MUST omit the próximo-paso block. When `pending_count` is 0, it MUST omit the pendientes line. Hoy MUST NOT render a WorkItem list, a chart, a hero metric, a day picker, or a closing-flow screen. Memoria and Negocio MUST stay unchanged. The block MUST refetch after the merchant returns to Hoy.

#### Scenario: Cash count is visible without preparing the close
- **WHEN** the merchant has confirmed sales, has not counted cash, and opens Hoy without sending `preparar el cierre`
- **THEN** Hoy MUST show `Cuenta el efectivo para continuar con el cierre.` and the server reason that contains the expected amount

#### Scenario: After close the block is gone
- **WHEN** today's day is `closed` and the merchant opens Hoy
- **THEN** Hoy MUST NOT show `Próximo paso` and MUST NOT show a pendientes line

### Requirement: Hoy does not calculate money or priority
Hoy MUST display the server `title` and `reason` strings. It MUST NOT format evidence amounts into those sentences, MUST NOT subtract counted cash from expected cash, MUST NOT choose which WorkItem is next, and MUST NOT invent a priority. Unknown or missing action data MUST omit the action control.

#### Scenario: Shortage copy is server text
- **WHEN** the GET `title` is `Hay un faltante de $14.00. Revisa la diferencia antes de confirmar el cierre.`
- **THEN** Hoy MUST show that string and MUST NOT compute `80.00 − 94.00`

### Requirement: Hoy starts close through the existing phrase
When `next_best_action.actions` contains `closing.request@1`, Hoy MUST show a button labeled `Cerrar el día`. The tap MUST switch to Inicio and MUST `POST /api/v1/lumo/messages` with message `cerrar el día` and the shell `conversation_id`. It MUST NOT `POST /api/v1/lumo/actions` and MUST NOT send a confirmation token. When `actions` is empty, Hoy MUST NOT show that button, an amount field, or a cash-count button.

#### Scenario: Count action has no button
- **WHEN** the GET action type is `cash_count_required` and `actions` is empty
- **THEN** Hoy MUST NOT show `Cerrar el día` or an amount input

#### Scenario: Close action reuses the phrase
- **WHEN** the merchant taps `Cerrar el día` on Hoy for a counted open day
- **THEN** the client MUST post `cerrar el día` on the existing shell `conversation_id` and MUST NOT post `/api/v1/lumo/actions` from Hoy

### Requirement: Register next_best_action@1
`GenerativeUIRegistry` MUST register component `next_best_action` version `1`. The composer MUST emit it only for a completed `operational_day.next_best_action@1` turn whose projection is not null. `data` MUST carry the projection fields. `fallback_text` MUST be `title`, a space, and `reason`, and MUST NOT contain a token. `actions` MUST be empty for `cash_count_required` and exactly `closing.request@1` for `cash_difference_review` and `close_confirmation_required`. That Inicio action MUST carry the existing `typ=ui_action` `context_token` used by `daily_close_preparation@1`. The GET payload MUST NOT include that token. The card MUST NOT emit `closing.confirm@1`. A null projection MUST emit no component. `closing_ready_card` and `cash_difference_card` MUST stay unregistered.

#### Scenario: Inicio card for a shortage
- **WHEN** the actor posts `qué sigue` and the projection type is `cash_difference_review`
- **THEN** the response `ui` MUST include one `next_best_action` version `1` whose only action is `closing.request@1` and whose `fallback_text` contains the server shortage title

#### Scenario: No action emits no card
- **WHEN** the actor posts `qué sigue` and the projection is null
- **THEN** `ui` MUST be empty and `text` MUST be `No hay un paso pendiente para el cierre de hoy.`

### Requirement: Flutter renders next_best_action@1
`GenerativeUIRenderer` MUST register `next_best_action` version `1`. It MUST show the server `title` and `reason` in the Inicio stream with the existing Lumo-mark gutter and card. It MUST render `Cerrar el día` only for `closing.request@1` on that card and MUST post that action through the existing actions endpoint. It MUST NOT render an amount field, a dismiss control, or a WorkItem list. An unknown version MUST show `fallback_text` and MUST NOT run actions. When response `text` equals `fallback_text`, the stream MUST show the card and MUST NOT also show that sentence as a second prose block.

#### Scenario: Renderer does not recompute the shortage
- **WHEN** the renderer receives `next_best_action` version `1` with a short title that already contains `$14.00`
- **THEN** it MUST show that title and MUST NOT derive the amount from `evidence`

#### Scenario: Unknown version
- **WHEN** the payload is `next_best_action` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT run its actions
