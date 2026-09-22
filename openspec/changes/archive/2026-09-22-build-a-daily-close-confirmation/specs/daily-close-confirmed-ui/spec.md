## ADDED Requirements

### Requirement: Register daily_close_confirmed@1
`GenerativeUIRegistry` MUST register component `daily_close_confirmed` version `1`. `GenerativeUIComposer` MUST emit this contract after a committed `closing.confirm@1`, after an already-closed read-back, and when `closing.prepare@1` or `request_close` reads a closed day. `actions` MUST be empty. Money MUST be decimal strings plus the business currency. `text` MUST equal `fallback_text`. The payload MUST NOT include a reopen action, an approval, an exception list, a product breakdown, a chart series, history, or accounting fields. PRD §10.5 names `closing_ready_card` and `cash_difference_card` MUST remain unregistered.

The contract MUST be:

```json
{
  "component": "daily_close_confirmed",
  "version": 1,
  "data": {
    "operational_day_id": "<uuid>",
    "closing_snapshot_id": "<uuid>",
    "business_date": "2026-09-21",
    "day_status": "closed",
    "closed_at": "2026-09-22T02:10:00+00:00",
    "currency": "MXN",
    "sale_count": 3,
    "gross_sales_total": {"amount": "56.50", "currency": "MXN"},
    "expected_cash": {"amount": "22.50", "currency": "MXN"},
    "counted_cash": {"amount": "22.50", "currency": "MXN"},
    "cash_difference": {"amount": "0.00", "currency": "MXN"},
    "cash_status": "balanced"
  },
  "actions": [],
  "fallback_text": "Cierre confirmado · 2026-09-21 · 3 ventas · $56.50 · Efectivo esperado $22.50 · Contado $22.50 · Diferencia $0.00 · Caja cuadrada"
}
```

`day_status` MUST be `closed`. `sale_count` of `1` MUST use `1 venta` in `fallback_text`; every other count MUST use `N ventas`. Status words MUST be `Caja cuadrada` for `balanced`, `Sobrante` for `over`, and `Faltante` for `short`. Amounts in the sentence MUST be the server decimal strings, and a negative difference MUST render its sign. `fallback_text` MUST start with `Cierre confirmado`.

#### Scenario: Composer emits the confirmed card
- **WHEN** a balanced close commits for business date `2026-09-21` with gross `56.50`, expected cash `22.50`, and counted cash `22.50`
- **THEN** the agent response `ui` MUST include exactly one `daily_close_confirmed` version `1` whose `day_status` is `closed`, `cash_difference.amount` is `0.00`, `actions` is empty, and `fallback_text` starts with `Cierre confirmado` and contains `Caja cuadrada`

#### Scenario: Shortage card keeps the sign
- **WHEN** the frozen difference is `-2.50` and `cash_status` is `short`
- **THEN** `cash_difference.amount` MUST be `-2.50` and `fallback_text` MUST contain `Faltante` and `-$2.50`

### Requirement: Flutter renders daily_close_confirmed@1
Flutter `GenerativeUIRenderer` MUST register `daily_close_confirmed` version `1`. It MUST render a compact card in the existing Inicio stream using the Lumo-mark gutter and the soft `LumoCard`: the words `Cierre confirmado`, the server business date, the gross sales total, expected cash, counted cash, the difference, the status label, and `closed_at`. Flutter MAY format the ISO `business_date`, the ISO `closed_at`, and decimal strings for display. Flutter MUST NOT subtract, compare, or sum amounts, MUST NOT compute `cash_status`, and MUST NOT change the calendar day using the device timezone. It MUST NOT render a reopen control, a confirm button, an approval, an exception list, a chart, or history. An unknown component or version MUST show `fallback_text` and MUST NOT run actions.

#### Scenario: Card content comes from the payload
- **WHEN** the renderer receives `daily_close_confirmed@1` with `gross_sales_total.amount` `56.50`, `expected_cash.amount` `22.50`, `counted_cash.amount` `22.50`, and `cash_difference.amount` `0.00`
- **THEN** it MUST display those server amounts and MUST NOT compute `22.50 − 22.50` on the client

#### Scenario: Unknown version falls back
- **WHEN** the payload is `daily_close_confirmed` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT execute any action

### Requirement: Confirmed close lives on Inicio
The confirmed card MUST appear in the existing Inicio conversation stream as an assistant artifact: unbubbled, Lumo-mark gutter, warm canvas, max-width 420px, existing spacing and radius tokens. Inicio MUST keep the same `conversation_id`. Navigation, the four-tab shell, the composer, and the theme MUST be unchanged. Hoy, Memoria, and Negocio MUST remain placeholders. The Design System "Preparar el cierre del día" action card, the Hoy hero metric card, the hourly chart, and a closing-flow screen MUST NOT be built in this change.

#### Scenario: Confirmed close on Inicio
- **WHEN** the signed-in Carrota user confirms today's close on Inicio
- **THEN** the Inicio stream MUST show a Lumo-mark `daily_close_confirmed@1` card and the Hoy tab MUST remain a placeholder

#### Scenario: Closing screen is not introduced
- **WHEN** the Flutter feature tree is inspected after this change
- **THEN** there MUST NOT be a closing-flow screen, a wired "Preparar el cierre del día" action card, or a Hoy chart
