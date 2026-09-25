## MODIFIED Requirements

### Requirement: Preparation lives on Inicio and does not build Hoy
The capture turn and the preparation card MUST appear in the existing Inicio conversation stream as assistant artifacts: unbubbled, Lumo-mark gutter, warm canvas, max-width 420px, existing spacing and radius tokens. Inicio MUST keep the same `conversation_id` when sending cash-count, preparation, request-close, and confirm phrases, and when posting `closing.request@1` or `closing.confirm@1`. Navigation, the four-tab shell, the composer, and the theme MUST be unchanged. Hoy MAY show the next-best-action block and the sales export panel. Memoria and Negocio MUST NOT gain a close workflow. The Design System "Preparar el cierre del día" action card, the Hoy hero metric card, the hourly chart, and a closing-flow screen MUST NOT be built, and no new dark theme, accent hue, motion, or skeleton MUST be introduced. Cash counting MUST stay conversational.

#### Scenario: Cash count on Inicio
- **WHEN** the signed-in Carrota user submits `tengo 20 en caja` after a confirmed cash sale of `22.50`
- **THEN** the Inicio stream MUST show the user bubble and a Lumo-mark `daily_close_preparation@1` card with the server expected, counted, and difference amounts

#### Scenario: Preparation request reuses the conversation
- **WHEN** the user submits `preparar el cierre` on the same Inicio instance used to confirm a sale
- **THEN** that POST MUST send the same `conversation_id` and Flutter MUST NOT generate a new UUID

#### Scenario: Closing screen is not introduced
- **WHEN** the Flutter feature tree is inspected after this change
- **THEN** there MUST NOT be a closing-flow screen, a wired "Preparar el cierre del día" action card, or a Hoy chart
