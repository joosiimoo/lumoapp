## Purpose

Versioned `daily_close_preparation@1` for close preparation. The backend composes it from the write and read tools. Flutter renders those fields on Inicio and does not calculate them. Hoy stays a placeholder.

## Requirements

### Requirement: Register daily_close_preparation@1
`GenerativeUIRegistry` MUST register component `daily_close_preparation` version `1`. `GenerativeUIComposer` MUST emit this contract for a completed `closing.prepare@1` read of an open or not-started day, for a completed `closing.submit_cash_count@1` write, and for a `request_close` turn that has not closed the day, including the not-started and not-counted states. It MUST NOT emit this contract for a closed day. `actions` MUST be empty. Money MUST be decimal strings plus the business currency. `text` MUST equal `fallback_text`. The payload MUST NOT include a reopen action, an approval, an exception list, a product breakdown, a chart series, history, or accounting fields. `data.confirmation_token` MUST be null except on a confirmable `request_close` response, where it MUST be the server-issued `closing_confirm` token. PRD §10.5 names `closing_ready_card` and `cash_difference_card` MUST remain unregistered.

The contract MUST be:

```json
{
  "component": "daily_close_preparation",
  "version": 1,
  "data": {
    "operational_day_id": "<uuid>|null",
    "business_date": "2026-09-21",
    "day_status": "open|null",
    "currency": "MXN",
    "sale_count": 3,
    "expected_cash": {"amount": "22.50", "currency": "MXN"},
    "counted_cash": {"amount": "20.00", "currency": "MXN"},
    "cash_difference": {"amount": "-2.50", "currency": "MXN"},
    "cash_status": "short",
    "counted_at": "2026-09-21T23:10:00+00:00",
    "cash_count_id": "<uuid>|null",
    "confirmation_token": "<jwt>|null"
  },
  "actions": [],
  "fallback_text": "Cierre 2026-09-21 · Efectivo esperado $22.50 · Contado $20.00 · Diferencia -$2.50 · Faltante"
}
```

Status words in `fallback_text` MUST be `Sin contar` for `not_counted`, `Caja cuadrada` for `balanced`, `Sobrante` for `over`, and `Faltante` for `short`. When `cash_status` is `not_counted`, `fallback_text` MUST be `Cierre <business_date> · Efectivo esperado $<expected_cash> · Falta contar efectivo` and MUST NOT contain a counted amount or a difference. Amounts in the sentence MUST be the server decimal strings, and a negative difference MUST render its sign. `fallback_text` MUST NOT include the confirmation token.

#### Scenario: Composer emits a shortage card
- **WHEN** `expected_cash` is `22.50`, the current count is `20.00`, and the business date is `2026-09-21` on an open day
- **THEN** the agent response `ui` MUST include exactly one `daily_close_preparation` version `1` whose `cash_status` is `short`, `cash_difference.amount` is `-2.50`, `confirmation_token` is null, and `fallback_text` contains `Faltante`

#### Scenario: Composer emits the not-counted card
- **WHEN** the day has cash sales of `22.50` and no `CashCount`
- **THEN** `counted_cash`, `cash_difference`, `counted_at`, `cash_count_id`, and `confirmation_token` MUST be null, `cash_status` MUST be `not_counted`, and `fallback_text` MUST contain `Falta contar efectivo` and MUST NOT contain a difference

#### Scenario: Request close attaches a token
- **WHEN** `request_close` runs for an open counted day
- **THEN** `confirmation_token` MUST be a non-null string, `actions` MUST be empty, and `fallback_text` MUST NOT contain that token

#### Scenario: Unregistered close cards refused
- **WHEN** the composer is asked to emit `closing_ready_card@1` or `cash_difference_card@1`
- **THEN** the backend MUST refuse to include it in the response

### Requirement: Flutter renders daily_close_preparation@1
Flutter `GenerativeUIRenderer` MUST register `daily_close_preparation` version `1`. It MUST render a compact card in the existing Inicio stream using the Lumo-mark gutter and the soft `LumoCard`: the server business date, the expected-cash amount, the counted-cash amount, the difference, and a status label derived from `cash_status`. Flutter MAY format the ISO `business_date`, the ISO `counted_at`, and decimal strings for display. Flutter MUST NOT subtract, compare, or sum amounts, MUST NOT compute or re-derive `expected_cash`, `cash_difference`, or `cash_status`, and MUST NOT change the calendar day using the device timezone. When `cash_status` is `not_counted` it MUST show a "Falta contar efectivo" state with no counted amount and no difference. It MUST NOT render a confirm-close button, a reopen control, an approval control, an exception list, a chart, or history, and it MUST NOT display `confirmation_token`. When `confirmation_token` is a string, Flutter MUST keep it in memory for that conversation and MUST send it as `client_context.confirmation_token` on the next message. When a later response has `confirmation_token` null or is `daily_close_confirmed@1`, Flutter MUST clear the stored token. Flutter MUST NOT invent a token. An unknown component or version MUST show `fallback_text` and MUST NOT run actions.

#### Scenario: Card content comes from the payload
- **WHEN** the renderer receives `daily_close_preparation@1` with `expected_cash.amount` `22.50`, `counted_cash.amount` `20.00`, `cash_difference.amount` `-2.50`, and `cash_status` `short`
- **THEN** it MUST display those three server amounts and the shortage status, and MUST NOT compute `20.00 − 22.50` on the client

#### Scenario: Not-counted state
- **WHEN** the payload has `counted_cash` null, `cash_difference` null, and `cash_status` `not_counted`
- **THEN** the card MUST show the expected amount and a "Falta contar efectivo" state, and MUST NOT render `0.00` as the difference

#### Scenario: Token is echoed and not shown
- **WHEN** the payload includes a non-null `confirmation_token` and the user then submits `confirmar cierre`
- **THEN** that POST MUST send `client_context.confirmation_token` equal to the server value, and the card MUST NOT display the token

#### Scenario: Unknown version falls back
- **WHEN** the payload is `daily_close_preparation` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT execute any action

### Requirement: Preparation lives on Inicio and does not build Hoy
The capture turn and the preparation card MUST appear in the existing Inicio conversation stream as assistant artifacts: unbubbled, Lumo-mark gutter, warm canvas, max-width 420px, existing spacing and radius tokens. Inicio MUST keep the same `conversation_id` when sending cash-count, preparation, request-close, and confirm phrases. Navigation, the four-tab shell, the composer, and the theme MUST be unchanged. Hoy, Memoria, and Negocio MUST remain placeholders. The Design System "Preparar el cierre del día" action card, the Hoy hero metric card, the hourly chart, and a closing-flow screen MUST NOT be built in this change, and no new dark theme, accent hue, motion, or skeleton MUST be introduced.

#### Scenario: Cash count on Inicio
- **WHEN** the signed-in Carrota user submits `tengo 20 en caja` after a confirmed cash sale of `22.50`
- **THEN** the Inicio stream MUST show the user bubble and a Lumo-mark `daily_close_preparation@1` card with the server expected, counted, and difference amounts, and the Hoy tab MUST remain a placeholder

#### Scenario: Preparation request reuses the conversation
- **WHEN** the user submits `preparar el cierre` on the same Inicio instance used to confirm a sale
- **THEN** that POST MUST send the same `conversation_id` and Flutter MUST NOT generate a new UUID

#### Scenario: Closing screen is not introduced
- **WHEN** the Flutter feature tree is inspected after this change
- **THEN** there MUST NOT be a closing-flow screen, a wired "Preparar el cierre del día" action card, or a Hoy chart
