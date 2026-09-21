## Purpose

Versioned `sale_confirmed@1` contract for an operationally completed sale. The backend composes it after a committed `sale.commit@1`; Flutter renders server-provided confirmation values without calculating them.

## ADDED Requirements

### Requirement: Register sale_confirmed@1
`GenerativeUIRegistry` MUST register component `sale_confirmed` version `1`. `GenerativeUIComposer` MUST emit this contract after a committed `sale.commit@1` **transition**, and MAY emit the same contract as a current-state read-back when the session is already `confirmed` and no newer active session exists for the interaction context. It MUST refuse unknown components. The backend MUST NOT render Flutter widgets or HTML. `actions` MUST be empty. Money MUST be decimal strings plus `MXN`. `fallback_text` MUST be server-provided and MUST contain the item count, total, and payment method display label (`Efectivo` | `Tarjeta` | `Transferencia`).

The contract MUST be:

```json
{
  "component": "sale_confirmed",
  "version": 1,
  "data": {
    "sale_session_id": "<uuid>",
    "payment_id": "<uuid>",
    "status": "confirmed",
    "currency": "MXN",
    "item_count": 3,
    "total": {"amount": "56.50", "currency": "MXN"},
    "payment": {
      "method": "cash",
      "amount": {"amount": "56.50", "currency": "MXN"},
      "status": "recorded"
    },
    "items": [
      {
        "sale_item_id": "<uuid>",
        "product_name": "Zanahoria",
        "quantity_normalized": "0.900",
        "unit_normalized": "kilogram",
        "unit_price": {"amount": "25.00", "currency": "MXN"},
        "line_total": {"amount": "22.50", "currency": "MXN"}
      }
    ]
  },
  "actions": [],
  "fallback_text": "Venta registrada · 3 artículos · $56.50 · Efectivo"
}
```

`data.status` MUST be `confirmed`. `data.payment.method` MUST be `cash`, `card`, or `transfer`. `data.payment.amount` MUST equal `data.total`. `data.total.amount` MUST equal the Decimal sum of persisted item `line_total`s. Item order MUST be persistence order (`created_at` ascending). This contract MUST NOT be used for `ready_to_charge` sales. `sale_summary@1` MUST NOT be emitted after a successful commit. PRD name `sale_confirmed_card` MUST remain unregistered.

#### Scenario: Composer emits after committed cash
- **WHEN** `sale.commit@1` has committed a three-item session totaling `56.50` MXN with method `cash`
- **THEN** the agent response `ui` MUST include exactly one `sale_confirmed` version `1` payload whose `data.status` is `confirmed`, `data.total.amount` is `56.50`, `data.payment.method` is `cash`, and `data.payment.amount.amount` is `56.50`

#### Scenario: Composer emits current confirmation on confirmed read-back
- **WHEN** the session is already `confirmed`, no newer `open` or `ready_to_charge` session exists for that conversation, and the actor posts `efectivo` with a new `Idempotency-Key`
- **THEN** the response `ui` MUST include `sale_confirmed@1` built from the persisted session, items, and payment and MUST NOT depend on a second commit

#### Scenario: Unregistered PRD card name still refused
- **WHEN** the composer is asked to emit `sale_confirmed_card@1` or `sale_completed@1`
- **THEN** the backend MUST refuse to include it

### Requirement: Flutter maps sale_confirmed@1
Flutter `GenerativeUIRenderer` MUST register `sale_confirmed` version `1`. It MUST render a compact conversation card using existing Lumo language mapped to Design System §4.12 (sale registered): Lumo mark gutter, soft `LumoCard`, registered status treatment, item count, total, payment method display label, and payment amount. Flutter MUST format server strings only and MUST NOT sum `line_total`s, recompute `total`, or derive payment amount. It MUST map `cash`→`Efectivo`, `card`→`Tarjeta`, `transfer`→`Transferencia` for display only. It MUST NOT show payment-selection chips, Registrar, Corregir, Deshacer, receipt, invoice, or a POS table. Unknown versions MUST show `fallback_text` and MUST NOT run actions.

#### Scenario: Confirmed card content from payload
- **WHEN** the renderer receives a `sale_confirmed@1` payload with `total.amount` `56.50`, `item_count` `3`, and `payment.method` `card`
- **THEN** it MUST show confirmed/registered status, item count `3`, total `$56.50`, method Tarjeta, and payment amount `$56.50` without adding line totals or inventing change due

#### Scenario: Unknown version falls back
- **WHEN** the payload is `sale_confirmed` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT execute actions

### Requirement: Confirmation fits Inicio without redesign
The confirmation MUST appear in the existing Inicio conversation stream as an assistant artifact: unbubbled, Lumo-mark gutter, warm canvas, max-width 420px. It MUST be a compact structured card, not a desktop table. Navigation and composer behavior MUST be unchanged. Flutter MUST keep the same `conversation_id` after rendering this card.

#### Scenario: Efectivo on Inicio
- **WHEN** the signed-in Carrota user submits `efectivo` after a totalized sale
- **THEN** the stream MUST show the user bubble for that text and a Lumo-mark `sale_confirmed@1` card whose visible total and method match the server payload
