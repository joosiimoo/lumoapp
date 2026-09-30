## MODIFIED Requirements

### Requirement: Hoy shows one next step and the pending count
Hoy MUST NOT use `GET /api/v1/operational-days/current/next-best-action` as its primary body. Hoy MUST show the Business Stream today projection as specified in `business-stream`, including the single prepare-close entry when present. When that projection has no `primary_action`, Hoy MUST omit closing CTAs. When `pending_count` semantics exist only on the NBA GET, Hoy MUST NOT require a pendientes line or invent a count from the supporting copy `Confirma efectivo y revisa pendientes`. Hoy MUST NOT render a WorkItem list, a chart, a hero analytics metric, a day picker, or a separate closing-flow screen outside the Hoy prepare-close workspace. Memoria and Negocio MUST stay unchanged aside from close-note display rules owned by `memoria-timeline`.

#### Scenario: After close the closing CTA is gone
- **WHEN** today's day is `closed` and the merchant opens Hoy
- **THEN** Hoy MUST show the closed daily summary and MUST NOT show `Preparar el cierre del día`, `Revisar cierre`, `Confirmar cierre`, or `Cerrar el día`

### Requirement: Hoy starts close through the existing phrase
When today `primary_action.kind` is `prepare_daily_close`, Hoy MUST show `Preparar el cierre del día` and MUST open the close workspace (`invocation` `close_workspace`). It MUST NOT show `Cerrar el día` as the Hoy chrome primary label, MUST NOT show `Registrar conteo` or `Revisar cierre` as the operator progression, and MUST NOT append a visible merchant bubble. When `primary_action` is null, Hoy MUST NOT show a close control. Inicio MUST NOT mirror the operator CTA.

#### Scenario: Prepare-close opens workspace
- **WHEN** the merchant taps `Preparar el cierre del día` on Hoy for an open close-eligible day
- **THEN** the client MUST open the close workspace and MUST NOT navigate to Inicio for cash count entry

#### Scenario: Count action is not a separate Hoy CTA
- **WHEN** the today GET state is `cash_count_required`
- **THEN** Hoy MUST show `Preparar el cierre del día` and MUST NOT show a standalone `Registrar conteo` button
