## Purpose

Versioned `sale_confirmed@1` contract for an operationally completed sale. The backend composes it after a committed `sale.commit@1`; Flutter renders server-provided confirmation values without calculating them.
## Requirements
### Requirement: Register sale_confirmed@1
`GenerativeUIRegistry` MUST register component `sale_confirmed` version `1`. `GenerativeUIComposer` MUST emit this contract after a committed `sale.commit@1` **transition**, and MAY emit the same contract as a current-state read-back when the session is already `confirmed` and no newer `open` or `ready_to_charge` session exists for the interaction context. A current-state read-back MUST NOT be composed when a newer active session exists. An exact completed idempotency replay MAY still return a previously stored body that contains `sale_confirmed@1`; that replay is not a fresh current-state read-back. A fresh payment action bound to an already confirmed session MUST NOT compose that historical `sale_confirmed@1` when a newer active session exists; it returns `ui_action_stale` with empty `ui`. It MUST refuse unknown components. The backend MUST NOT render Flutter widgets or HTML. `actions` MUST be empty, including after a payment tap. Money MUST be decimal strings plus `MXN`. `fallback_text` MUST be server-provided and MUST contain the item count, total, and payment method display label (`Efectivo` | `Tarjeta` | `Transferencia`). The contract version MUST remain `1`. `data.items` MUST include every persisted line.

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
- **THEN** the agent response `ui` MUST include exactly one `sale_confirmed` version `1` payload whose `data.status` is `confirmed`, `data.total.amount` is `56.50`, `data.payment.method` is `cash`, `data.payment.amount.amount` is `56.50`, `data.items` length is 3, and `actions` is empty

#### Scenario: Composer emits current confirmation on confirmed read-back
- **WHEN** the session is already `confirmed`, no newer `open` or `ready_to_charge` session exists for that conversation, and the actor posts `efectivo` with a new `Idempotency-Key`
- **THEN** the response `ui` MUST include `sale_confirmed@1` built from the persisted session, items, and payment and MUST NOT depend on a second commit

#### Scenario: Fresh stale action does not compose a historical card
- **WHEN** session A is `confirmed`, session B is `ready_to_charge` in the same conversation, and an unused payment action bound to A is submitted
- **THEN** the response `ui` MUST be empty and MUST NOT include `sale_confirmed@1`

#### Scenario: Exact replay may return a stored confirmed card
- **WHEN** a completed payment action for session A is retried with the same key and hash after session B is `ready_to_charge`
- **THEN** the stored body MAY include session A's `sale_confirmed@1` and that response MUST be the persisted replay, not a newly composed current-state card for A or B

#### Scenario: Unregistered PRD card name still refused
- **WHEN** the composer is asked to emit `sale_confirmed_card@1` or `sale_completed@1`
- **THEN** the backend MUST refuse to include it

### Requirement: Flutter maps sale_confirmed@1
Flutter `GenerativeUIRenderer` MUST register `sale_confirmed` version `1`. It MUST render a conversation card using existing Lumo language: Lumo mark gutter, soft `LumoCard`, status chip `Venta registrada`, every server item row (name, user-facing quantity and unit price, right-aligned server line total), one total row from `data.total`, and a payment row labeled `Pago` with the method display label. Flutter MUST format server strings only and MUST NOT sum `line_total`s, recompute `total`, or derive payment amount. It MUST map `cash`→`Efectivo`, `card`→`Tarjeta`, `transfer`→`Transferencia` for display only. It MUST NOT show a second amount for `payment.amount`, payment-selection chips, Registrar, Corregir, Deshacer, inventory copy, a receipt, an invoice, or a POS table. Unknown versions MUST show `fallback_text` and MUST NOT run actions.

#### Scenario: Confirmed card lists every item
- **WHEN** the renderer receives a `sale_confirmed@1` payload with two items, `total.amount` `32.50`, and `payment.method` `cash`
- **THEN** it MUST show both product names, both server line totals, total `$32.50`, and `Pago` `Efectivo`, without adding the line totals

#### Scenario: Unknown version falls back
- **WHEN** the payload is `sale_confirmed` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT execute actions

### Requirement: Confirmation fits Inicio without redesign
The confirmation MUST appear in the existing Inicio conversation stream as an assistant artifact: unbubbled, Lumo-mark gutter, warm canvas, max-width 420px. It MUST be a compact structured card, not a desktop table. Navigation and composer behavior MUST be unchanged. Flutter MUST keep the same `conversation_id` after rendering this card. When `text` equals `fallback_text`, the visible stream MUST NOT also show that sentence as a prose block.

#### Scenario: Efectivo on Inicio
- **WHEN** the signed-in Carrota user submits `efectivo` after a totalized sale
- **THEN** the stream MUST show the user bubble for that text and a Lumo-mark `sale_confirmed@1` card whose visible lines, total, and method match the server payload

### Requirement: Confirmed rows include free-concept names
`sale_confirmed@1` MUST stay version `1`. `data.items` MUST include every persisted line. A free-concept line MUST use its snapshot as `product_name` and its persisted `line_total`. The payload MUST NOT add a source badge, a save-to-catalog action, or a second card component. Flutter MUST render `product_name` exactly as supplied, including accents and casing, and MUST NOT recompute the total.

#### Scenario: Confirmed card shows the concept
- **WHEN** `sale.commit@1` confirms a sale whose lines include `bolsas de hielo`
- **THEN** `sale_confirmed@1` `data.items` MUST include `product_name` `bolsas de hielo`

#### Scenario: Renderer shows the confirmed concept
- **WHEN** Flutter receives that payload
- **THEN** it MUST show `bolsas de hielo` and the server total, and it MUST NOT show "Concepto libre"

#### Scenario: Renderer keeps an accented confirmed name
- **WHEN** a confirmed item has `product_name` `Café Orgánico`
- **THEN** Flutter MUST show `Café Orgánico` and MUST NOT show `cafe organico`

