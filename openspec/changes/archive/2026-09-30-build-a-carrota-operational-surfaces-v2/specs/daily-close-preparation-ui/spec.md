## MODIFIED Requirements

### Requirement: Flutter renders daily_close_preparation@1
Flutter `GenerativeUIRenderer` MUST register `daily_close_preparation` version `1`. It MUST render a card in the existing Inicio stream using the Lumo-mark gutter and the soft `LumoCard`: the server business date, the expected-cash amount, the counted-cash amount when present, the difference when present, `sale_count` as `1 venta` or `N ventas`, and a status label derived from `cash_status`. Flutter MAY format the ISO `business_date`, the ISO `counted_at`, and decimal strings for display. Flutter MUST NOT subtract, compare, or sum amounts, MUST NOT compute or re-derive `expected_cash`, `cash_difference`, or `cash_status`, and MUST NOT change the calendar day using the device timezone. `balanced` MUST show `Caja cuadrada`. `short` MUST show `Faltante` and the server signed difference. `over` MUST show `Sobrante` and a display-only `+` before the formatted positive server amount. When `cash_status` is `not_counted` it MUST show `Falta contar efectivo` with no counted amount, no difference, no amount input, and no close button. Historical or typed-composer `request_close` cards MAY keep their existing action control. The operator path (`Preparar el cierre del día` from Hoy) MUST use the dedicated close workspace, MUST NOT insert a merchant utterance, and MUST NOT append a new `daily_close_preparation@1` card into the visible transcript. Operator confirm MUST appear only inside that workspace as `Cerrar el día`. It MUST NOT render a reopen control, an approval control, an exception list, a chart, or history, and it MUST NOT display `confirmation_token` or `context_token`. An unknown component or version MUST show `fallback_text` and MUST NOT run actions.

#### Scenario: Card content comes from the payload
- **WHEN** the renderer receives `daily_close_preparation@1` with `expected_cash.amount` `22.50`, `counted_cash.amount` `20.00`, `cash_difference.amount` `-2.50`, and `cash_status` `short`
- **THEN** it MUST display those three server amounts and `Faltante`, and MUST NOT compute `20.00 − 22.50` on the client

#### Scenario: Overage shows a display plus
- **WHEN** `cash_status` is `over` and `cash_difference.amount` is `10.00`
- **THEN** the card MUST show `Sobrante` and a visible `+` on the formatted amount, and MUST NOT add 10 to the expected amount

#### Scenario: Not-counted state
- **WHEN** the payload has `counted_cash` null, `cash_difference` null, `cash_status` `not_counted`, and empty `actions`
- **THEN** the card MUST show the expected amount and `Falta contar efectivo`, and MUST NOT render an amount field or a close button

#### Scenario: Operator workspace does not duplicate confirm
- **WHEN** the merchant opens Daily Close from `Preparar el cierre del día`
- **THEN** Inicio MUST NOT also show a new `daily_close_preparation@1` card whose only purpose is to host a second confirm control

#### Scenario: Typed close phrase may still emit a card
- **WHEN** the merchant types an approved `request_close` phrase in the composer
- **THEN** the existing preparation card path MAY appear in the transcript as history and MUST NOT replace the Hoy close workspace for the operator CTA

#### Scenario: Unknown version falls back
- **WHEN** the payload is `daily_close_preparation` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT execute any action

### Requirement: Preparation lives on Inicio and does not build Hoy
Cash counting for the **conversational** path MUST stay phrase-based on Inicio. The **operator** Daily Close path MUST be the Hoy close workspace specified by `mobile-shell`: numeric count, server difference, optional note, and `Cerrar el día`, without navigating to Inicio for count entry. Typed cash-count, preparation, request-close, and confirm phrases, and posts of `closing.request@1` or `closing.confirm@1`, MUST keep the same Inicio `conversation_id` when used conversationally. Navigation, the four-tab shell, and the theme MUST be unchanged. Memoria and Negocio MUST NOT gain a separate close workflow beyond displaying persisted close-note facts. The Design System "Preparar el cierre del día" action card meaning for operator chrome is the Hoy entry CTA opening the workspace—not a Hoy analytics hero. An hourly chart MUST NOT be built. No new dark theme, accent hue, motion, or skeleton MUST be introduced. Inicio MUST NOT expose operator Daily Close initiation CTAs.

#### Scenario: Conversational cash count on Inicio
- **WHEN** the signed-in Carrota user submits `tengo 20 en caja` after a confirmed cash sale of `22.50`
- **THEN** the Inicio stream MUST show the user bubble and a Lumo-mark `daily_close_preparation@1` card with the server expected, counted, and difference amounts

#### Scenario: Preparation request reuses the conversation
- **WHEN** the user submits `preparar el cierre` on the same Inicio instance used to confirm a sale
- **THEN** that POST MUST send the same `conversation_id` and Flutter MUST NOT generate a new UUID

#### Scenario: Closing dashboard is not introduced
- **WHEN** the Flutter feature tree is inspected after this change
- **THEN** there MUST NOT be a Hoy chart, inventory screen, or mixed-payment form added by this slice

#### Scenario: Typed cerrar el día still works
- **WHEN** the merchant types `cerrar el día` on Inicio for a counted open day
- **THEN** the historical conversational preparation path MUST still run and MUST NOT be removed by the Hoy close workspace
