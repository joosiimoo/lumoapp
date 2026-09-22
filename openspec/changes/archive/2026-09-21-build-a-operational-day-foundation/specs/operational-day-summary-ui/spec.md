## Purpose

Versioned `operational_day_summary@1` for today's confirmed-sales summary. The backend composes it from the read-tool payload. Flutter renders those fields and does not calculate them.

## ADDED Requirements

### Requirement: Register operational_day_summary@1
`GenerativeUIRegistry` MUST register component `operational_day_summary` version `1`. `GenerativeUIComposer` MUST emit this contract for a completed `operational_day.summary@1` read, including the zero-sales summary. It MUST refuse unknown components. The backend MUST NOT render Flutter widgets or HTML. `actions` MUST be empty. Money MUST be decimal strings plus the business currency. `text` MUST equal `fallback_text`. The payload MUST NOT include expected cash, counted cash, a difference, a close action, exceptions, product rows, or a chart.

The contract MUST be:

```json
{
  "component": "operational_day_summary",
  "version": 1,
  "data": {
    "operational_day_id": "<uuid>|null",
    "business_date": "2026-09-21",
    "status": "open|null",
    "currency": "MXN",
    "sale_count": 1,
    "gross_sales_total": {"amount": "56.50", "currency": "MXN"},
    "cash_total": {"amount": "56.50", "currency": "MXN"},
    "card_total": {"amount": "0.00", "currency": "MXN"},
    "transfer_total": {"amount": "0.00", "currency": "MXN"}
  },
  "actions": [],
  "fallback_text": "Hoy 2026-09-21 · 1 venta · $56.50 · Efectivo $56.50 · Tarjeta $0.00 · Transferencia $0.00"
}
```

`business_date` MUST be an ISO calendar date. `status` MUST be `open` when `operational_day_id` is present and MUST be null when it is not. `sale_count` of `1` MUST use `1 venta` in `fallback_text`; every other count MUST use `N ventas`. Method labels in that sentence MUST be `Efectivo`, `Tarjeta`, and `Transferencia`. Amounts in the sentence MUST be the server decimal strings. `data.gross_sales_total.amount` MUST equal the sum of the three method amounts. PRD name `daily_summary_card` MUST remain unregistered.

#### Scenario: Composer emits a one-sale summary
- **WHEN** today's confirmed sales are one cash sale of `56.50` MXN on business date `2026-09-21`
- **THEN** the agent response `ui` MUST include exactly one `operational_day_summary` version `1` whose `sale_count` is `1`, `gross_sales_total.amount` is `56.50`, `cash_total.amount` is `56.50`, the other method amounts are `0.00`, `status` is `open`, and `fallback_text` contains `1 venta`

#### Scenario: Composer emits zeros without a day id
- **WHEN** the summary is today's date and no OperationalDay exists
- **THEN** `operational_day_id` and `status` MUST be null, `sale_count` MUST be `0`, every amount MUST be `0.00`, and `fallback_text` MUST contain `0 ventas`

#### Scenario: Unregistered close card refused
- **WHEN** the composer is asked to emit `daily_summary_card@1` or `closing_ready_card@1`
- **THEN** the backend MUST refuse to include it

### Requirement: Flutter maps operational_day_summary@1
Flutter `GenerativeUIRenderer` MUST register `operational_day_summary` version `1`. It MUST render a compact Inicio card using the existing Lumo mark gutter and soft `LumoCard`: the server business date, sale count, gross total, and cash, card, and transfer amounts. Flutter MAY format the ISO `business_date` and decimal strings for display. It MUST NOT derive the calendar day from the device timezone, MUST NOT add method totals, and MUST NOT replace `gross_sales_total`. It MUST NOT show a close button, expected cash, a difference, exceptions, a chart, or history. Unknown versions MUST show `fallback_text` and MUST NOT run actions.

#### Scenario: Card content from payload
- **WHEN** the renderer receives `operational_day_summary@1` with `business_date` `2026-09-21`, `sale_count` `2`, `gross_sales_total.amount` `80.00`, `cash_total.amount` `56.50`, `card_total.amount` `23.50`, and `transfer_total.amount` `0.00`
- **THEN** it MUST show that date, count `2`, gross `$80.00`, and the three method amounts without adding `56.50` and `23.50` to produce the gross

#### Scenario: Unknown version falls back
- **WHEN** the payload is `operational_day_summary` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT execute actions

### Requirement: Summary fits Inicio and does not build Hoy
The summary MUST appear in the existing Inicio conversation stream as an assistant artifact: unbubbled, Lumo-mark gutter, warm canvas, max-width 420px. Navigation and composer behavior MUST be unchanged. Flutter MUST keep the same `conversation_id`. Hoy, Memoria, and Negocio MUST remain placeholders. The Design System closing action MUST NOT be wired.

#### Scenario: Ventas de hoy on Inicio
- **WHEN** the signed-in Carrota user submits `ventas de hoy`
- **THEN** the stream MUST show the user bubble and a Lumo-mark `operational_day_summary@1` card whose count and totals match the server payload, and the Hoy tab MUST NOT become a daily-close screen
