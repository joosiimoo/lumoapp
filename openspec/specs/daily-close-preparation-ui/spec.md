## Purpose

Versioned `daily_close_preparation@1` for close preparation. The backend composes it from the write and read tools. Flutter renders those fields on Inicio and does not calculate them. Hoy stays a placeholder.
## Requirements
### Requirement: Register daily_close_preparation@1
`GenerativeUIRegistry` MUST register component `daily_close_preparation` version `1`. `GenerativeUIComposer` MUST emit this contract for a completed `closing.prepare@1` read of an open or not-started day, for a completed `closing.submit_cash_count@1` write, and for a `request_close` turn that has not closed the day, including the not-started and not-counted states. It MUST NOT emit this contract for a closed day. Money MUST be decimal strings plus the business currency. The data fields MUST stay the current set and MUST NOT add `gross_sales_total`. `data.confirmation_token` MUST be null except on a confirmable `request_close` response, where it MUST equal the `closing.confirm@1` action `context_token`. Counted open preparation with `cash_status` `balanced`, `short`, or `over` and a null token MUST emit exactly `closing.request@1`. A confirmable `request_close` response MUST emit exactly `closing.confirm@1` and MUST NOT also emit `closing.request@1`. `not_counted`, a missing day, and a missing current count MUST emit `actions: []`. `fallback_text` MUST NOT include the confirmation token. PRD §10.5 names `closing_ready_card` and `cash_difference_card` MUST remain unregistered. The version MUST remain `1`.

Status words in the standard `Cierre ` fallback MUST be `Sin contar` for `not_counted`, `Caja cuadrada` for `balanced`, `Sobrante` for `over`, and `Faltante` for `short`. When `cash_status` is `not_counted`, that fallback MUST be `Cierre <business_date> · Efectivo esperado $<expected_cash> · Falta contar efectivo` and MUST NOT contain a counted amount or a difference. Amounts in the sentence MUST be the server decimal strings, and a negative difference MUST render its sign.

#### Scenario: Composer emits a shortage card
- **WHEN** `expected_cash` is `22.50`, the current count is `20.00`, and the business date is `2026-09-21` on an open day that has not requested close
- **THEN** the agent response `ui` MUST include exactly one `daily_close_preparation` version `1` whose `cash_status` is `short`, `cash_difference.amount` is `-2.50`, `confirmation_token` is null, `actions` is `closing.request@1` only, and `fallback_text` contains `Faltante`

#### Scenario: Composer emits the not-counted card
- **WHEN** the day has cash sales of `22.50` and no `CashCount`
- **THEN** `counted_cash`, `cash_difference`, `counted_at`, `cash_count_id`, and `confirmation_token` MUST be null, `cash_status` MUST be `not_counted`, `actions` MUST be empty, and `fallback_text` MUST contain `Falta contar efectivo` and MUST NOT contain a difference

#### Scenario: Request close attaches one confirm action
- **WHEN** `request_close` runs for an open counted day
- **THEN** `actions` MUST be exactly `closing.confirm@1`, `confirmation_token` MUST equal that action's `context_token`, the day MUST stay open, and `fallback_text` MUST NOT contain that token

#### Scenario: Unregistered close cards refused
- **WHEN** the composer is asked to emit `closing_ready_card@1` or `cash_difference_card@1`
- **THEN** the backend MUST refuse to include it in the response

### Requirement: Flutter renders daily_close_preparation@1
Flutter `GenerativeUIRenderer` MUST register `daily_close_preparation` version `1`. It MUST render a card in the existing Inicio stream using the Lumo-mark gutter and the soft `LumoCard`: the server business date, the expected-cash amount, the counted-cash amount when present, the difference when present, `sale_count` as `1 venta` or `N ventas`, and a status label derived from `cash_status`. Flutter MAY format the ISO `business_date`, the ISO `counted_at`, and decimal strings for display. Flutter MUST NOT subtract, compare, or sum amounts, MUST NOT compute or re-derive `expected_cash`, `cash_difference`, or `cash_status`, and MUST NOT change the calendar day using the device timezone. `balanced` MUST show `Caja cuadrada`. `short` MUST show `Faltante` and the server signed difference. `over` MUST show `Sobrante` and a display-only `+` before the formatted positive server amount. When `cash_status` is `not_counted` it MUST show `Falta contar efectivo` with no counted amount, no difference, no amount input, and no close button. Historical or typed-composer `request_close` cards MAY keep their existing action control. The operator CTA path (`Revisar cierre` from Business Stream or Hoy) MUST silent-run `request_close`, MUST open the dedicated review surface, MUST NOT insert a merchant utterance, and MUST NOT append a new `daily_close_preparation@1` card into the visible transcript. `Confirmar cierre` on the operator path MUST appear only on that review surface. It MUST NOT render a reopen control, an approval control, an exception list, a chart, or history, and it MUST NOT display `confirmation_token` or `context_token`. An unknown component or version MUST show `fallback_text` and MUST NOT run actions.

#### Scenario: Card content comes from the payload
- **WHEN** the renderer receives `daily_close_preparation@1` with `expected_cash.amount` `22.50`, `counted_cash.amount` `20.00`, `cash_difference.amount` `-2.50`, and `cash_status` `short`
- **THEN** it MUST display those three server amounts and `Faltante`, and MUST NOT compute `20.00 − 22.50` on the client

#### Scenario: Overage shows a display plus
- **WHEN** `cash_status` is `over` and `cash_difference.amount` is `10.00`
- **THEN** the card MUST show `Sobrante` and a visible `+` on the formatted amount, and MUST NOT add 10 to the expected amount

#### Scenario: Not-counted state
- **WHEN** the payload has `counted_cash` null, `cash_difference` null, `cash_status` `not_counted`, and empty `actions`
- **THEN** the card MUST show the expected amount and `Falta contar efectivo`, and MUST NOT render an amount field or a close button

#### Scenario: Operator review does not duplicate confirm
- **WHEN** the merchant opens Daily Close review from `Revisar cierre`
- **THEN** Inicio MUST NOT also show a new `daily_close_preparation@1` card whose only purpose is to host a second `Confirmar cierre`

#### Scenario: Typed close phrase may still emit a card
- **WHEN** the merchant types an approved `request_close` phrase in the composer
- **THEN** the existing preparation card path MAY appear in the transcript as history and MUST NOT replace the dedicated review surface for the `Revisar cierre` CTA

#### Scenario: Unknown version falls back
- **WHEN** the payload is `daily_close_preparation` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT execute any action

### Requirement: Preparation lives on Inicio and does not build Hoy
Cash counting MUST stay conversational: `Registrar conteo` focuses the composer; the merchant types an amount phrase; the existing cash-count tools run. The operator Daily Close review MUST be the dedicated Flutter surface specified by `mobile-shell`, not a Hoy closing-flow screen and not a chart. Typed cash-count, preparation, request-close, and confirm phrases, and posts of `closing.request@1` or `closing.confirm@1`, MUST keep the same Inicio `conversation_id`. Navigation, the four-tab shell, and the theme MUST be unchanged. Memoria and Negocio MUST NOT gain a close workflow. The Design System "Preparar el cierre del día" action card, a Hoy hero analytics card, and an hourly chart MUST NOT be built. No new dark theme, accent hue, motion, or skeleton MUST be introduced.

#### Scenario: Cash count on Inicio
- **WHEN** the signed-in Carrota user submits `tengo 20 en caja` after a confirmed cash sale of `22.50`
- **THEN** the Inicio stream MUST show the user bubble and a Lumo-mark `daily_close_preparation@1` card with the server expected, counted, and difference amounts

#### Scenario: Preparation request reuses the conversation
- **WHEN** the user submits `preparar el cierre` on the same Inicio instance used to confirm a sale
- **THEN** that POST MUST send the same `conversation_id` and Flutter MUST NOT generate a new UUID

#### Scenario: Closing dashboard is not introduced
- **WHEN** the Flutter feature tree is inspected after this change
- **THEN** there MUST NOT be a Hoy chart, inventory screen, or mixed-payment form added by this slice
