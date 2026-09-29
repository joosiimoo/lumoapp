## MODIFIED Requirements

### Requirement: Flutter renders daily_close_preparation@1
Flutter `GenerativeUIRenderer` MUST register `daily_close_preparation` version `1`. It MUST render a card in the existing Inicio stream using the Lumo-mark gutter and the soft `LumoCard`: the server business date, the expected-cash amount, the counted-cash amount when present, the difference when present, `sale_count` as `1 venta` or `N ventas`, and a status label derived from `cash_status`. Flutter MAY format the ISO `business_date`, the ISO `counted_at`, and decimal strings for display. Flutter MUST NOT subtract, compare, or sum amounts, MUST NOT compute or re-derive `expected_cash`, `cash_difference`, or `cash_status`, and MUST NOT change the calendar day using the device timezone. `balanced` MUST show `Caja cuadrada`. `short` MUST show `Faltante` and the server signed difference. `over` MUST show `Sobrante` and a display-only `+` before the formatted positive server amount. When `cash_status` is `not_counted` it MUST show `Falta contar efectivo` with no counted amount, no difference, no amount input, and no close button. Historical or typed-composer `request_close` cards MAY keep their existing action control. The operator CTA path (`Revisar cierre` from Business Stream or Hoy) MUST silent-run `request_close`, MUST open the dedicated review surface, MUST NOT insert a merchant utterance, and MUST NOT append a new `daily_close_preparation@1` card into the visible transcript. `Confirmar cierre` on the operator path MUST appear only on that review surface. The renderer MUST NOT display `confirmation_token` or `context_token`. An unknown component or version MUST show `fallback_text` and MUST NOT run actions.

#### Scenario: Card content comes from the payload
- **WHEN** the renderer receives `daily_close_preparation@1` with `expected_cash.amount` `22.50`, `counted_cash.amount` `20.00`, `cash_difference.amount` `-2.50`, and `cash_status` `short`
- **THEN** it MUST display those three server amounts and `Faltante`, and MUST NOT compute `20.00 − 22.50` on the client

#### Scenario: Operator review does not duplicate confirm
- **WHEN** the merchant opens Daily Close review from `Revisar cierre`
- **THEN** Inicio MUST NOT also show a new `daily_close_preparation@1` card whose only purpose is to host a second `Confirmar cierre`

#### Scenario: Typed close phrase may still emit a card
- **WHEN** the merchant types an approved `request_close` phrase in the composer
- **THEN** the existing preparation card path MAY appear in the transcript as history and MUST NOT replace the dedicated review surface for the `Revisar cierre` CTA

### Requirement: Preparation lives on Inicio and does not build Hoy
Cash counting MUST stay conversational: `Registrar conteo` focuses the composer; the merchant types an amount phrase; the existing cash-count tools run. The operator Daily Close review MUST be the dedicated Flutter surface specified by `mobile-shell`, not a Hoy closing-flow screen and not a chart. Navigation, the four-tab shell, and the theme MUST be unchanged. Memoria and Negocio MUST NOT gain a close workflow. The Design System "Preparar el cierre del día" action card, a Hoy hero analytics card, and an hourly chart MUST NOT be built.

#### Scenario: Cash count on Inicio
- **WHEN** the signed-in Carrota user submits `tengo 20 en caja` after a confirmed cash sale of `22.50`
- **THEN** the Inicio stream MUST show the user bubble and a Lumo-mark `daily_close_preparation@1` card with the server expected, counted, and difference amounts

#### Scenario: Closing dashboard is not introduced
- **WHEN** the Flutter feature tree is inspected after this change
- **THEN** there MUST NOT be a Hoy chart, inventory screen, or mixed-payment form added by this slice
