## MODIFIED Requirements

### Requirement: Hoy shows one next step and the pending count
Hoy MUST NOT use `GET /api/v1/operational-days/current/next-best-action` as its primary body. Hoy MUST show the Business Stream today projection as specified in `business-stream`. When that projection has no `primary_action`, Hoy MUST omit closing CTAs. When `pending_count` semantics exist only on the NBA GET, Hoy MUST NOT require a pendientes line. Hoy MUST NOT render a WorkItem list, a chart, a hero analytics metric, a day picker, or a closing-flow screen. Memoria and Negocio MUST stay unchanged.

#### Scenario: After close the closing CTA is gone
- **WHEN** today's day is `closed` and the merchant opens Hoy
- **THEN** Hoy MUST show the closed daily summary and MUST NOT show `Revisar cierre`, `Confirmar cierre`, or `Cerrar el día`

### Requirement: Hoy does not calculate money or priority
Hoy MUST display server strings and server amounts from `GET /api/v1/business-stream/today`. It MUST NOT format evidence amounts into NBA sentences, MUST NOT subtract counted cash from expected cash, MUST NOT choose which WorkItem is next, and MUST NOT invent a priority.

#### Scenario: Shortage copy is server state
- **WHEN** the today GET `cash_status` is `short` and `cash_difference.amount` is `-2.50`
- **THEN** Hoy MUST show `Faltante` and `-2.50` and MUST NOT compute `20.00 − 22.50`

### Requirement: Hoy starts close through the existing phrase
When today `primary_action.kind` is `request_close`, Hoy MUST show `Revisar cierre` and MUST use the same silent `request_close` plus review-surface path as Inicio (`POST /api/v1/lumo/messages` with the technical identifier, then the sheet). It MUST NOT show `Cerrar el día`. It MUST NOT append a visible merchant bubble. When the action is `record_cash_count`, Hoy MUST communicate `Registrar conteo` and MUST NOT show an amount field. When `primary_action` is null, Hoy MUST NOT show a close control.

#### Scenario: Count action has no close button
- **WHEN** the today GET state is `cash_count_required`
- **THEN** Hoy MUST NOT show `Cerrar el día` or `Confirmar cierre`

#### Scenario: Close action opens review
- **WHEN** the merchant taps `Revisar cierre` on Hoy for a counted open day
- **THEN** the client MUST silent-post `request_close`, MUST open the review surface, and MUST NOT insert a user turn `cerrar el día`

## ADDED Requirements

### Requirement: Conversational NBA on Inicio is unchanged in role
`next_best_action` version `1` on Inicio remains the artifact for a typed `qué sigue` (or equivalent) turn. That card MUST NOT become Hoy's primary layout. If that Inicio card still emits `closing.request@1`, any visible button on a newly rendered card SHOULD use `Revisar cierre` rather than `Cerrar el día`, and MUST NOT be required for the operator review-surface path.

#### Scenario: Qué sigue still has a card path
- **WHEN** the actor posts `qué sigue` and the projection type is `close_confirmation_required`
- **THEN** Inicio MAY show `next_best_action` version `1` in the transcript and Hoy MUST still be the structured daily summary
