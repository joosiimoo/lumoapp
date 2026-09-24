## Purpose

Versioned `sale_summary@1` contract for a totalized sale. The backend composes it after a committed `sale.totalize@1` (or as a `ready_to_charge` read-back) and MUST NOT emit it after `sale.commit@1`. Flutter renders server-provided lines and totals without calculating them.
## Requirements
### Requirement: Register sale_summary@1
`GenerativeUIRegistry` MUST register component `sale_summary` version `1`. `GenerativeUIComposer` MUST emit this contract after a committed `sale.totalize@1` **transition**, and MAY emit the same contract as a current-state read-back when the session is already `ready_to_charge`. It MUST NOT emit `sale_summary@1` after `sale.commit@1` or for a `confirmed` session. It MUST refuse unknown components. The backend MUST NOT render Flutter widgets or HTML. Money MUST be decimal strings plus `MXN`. `fallback_text` MUST be server-provided and MUST contain the item count and total. For `ready_to_charge`, `actions` MUST be exactly `sale.pay.cash@1`, `sale.pay.card@1`, and `sale.pay.transfer@1`, in that order. Each action MUST have `option_id` null, a `typ=ui_action` `context_token` whose `sale_session_id` equals `data.sale_session_id`, and a server-issued `idempotency_key`. The contract version MUST remain `1`. Data fields MUST NOT add a payment amount or an authorization code.

The contract MUST be:

```json
{
  "component": "sale_summary",
  "version": 1,
  "data": {
    "sale_session_id": "<uuid>",
    "status": "ready_to_charge",
    "currency": "MXN",
    "item_count": 2,
    "subtotal": {"amount": "32.50", "currency": "MXN"},
    "total": {"amount": "32.50", "currency": "MXN"},
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
  "actions": [
    {
      "action_id": "sale.pay.cash@1",
      "option_id": null,
      "context_token": "<ui_action jwt>",
      "idempotency_key": "<uuid>"
    }
  ],
  "fallback_text": "Venta lista para cobrar · 2 artículos · $32.50"
}
```

The example shows one action object for shape. A real `ready_to_charge` payload MUST include all three payment actions. `subtotal` MUST equal `total` in this change (no discounts). `data.total.amount` MUST equal the Decimal sum of the persisted item `line_total`s. Item order MUST be persistence order (`created_at` ascending). `data.status` MUST be `ready_to_charge`.

#### Scenario: Composer emits after committed totalize
- **WHEN** `sale.totalize@1` has committed an open two-item session totaling `32.50` MXN
- **THEN** the agent response `ui` MUST include exactly one `sale_summary` version `1` payload whose `data.status` is `ready_to_charge`, whose `data.total.amount` is `32.50`, and whose `actions` are the three payment ids

#### Scenario: Payment tokens name this sale
- **WHEN** `sale_summary@1` is emitted for `sale_session_id` A
- **THEN** every payment `context_token` MUST be signed for `sale_session_id` A and the action request body MUST NOT include `sale_session_id`

#### Scenario: Composer emits current summary on ready_to_charge read-back
- **WHEN** the session is already `ready_to_charge` and the actor posts `totalizar` with a new idempotency key
- **THEN** the response `ui` MUST include `sale_summary@1` built from currently persisted items, including the three payment actions, and MUST NOT depend on a second totalize commit

#### Scenario: Confirmed sale does not reuse sale_summary
- **WHEN** `sale.commit@1` has committed and the session is `confirmed`
- **THEN** the agent response `ui` MUST NOT include `sale_summary@1`

#### Scenario: Unregistered confirmed-sale card still refused
- **WHEN** the composer is asked to emit `sale_confirmed_card@1` or `sale_ready_to_charge@1`
- **THEN** the backend MUST refuse to include it

### Requirement: Flutter maps sale_summary@1
Flutter `GenerativeUIRenderer` MUST register `sale_summary` version `1`. It MUST render a conversation card using existing Lumo language: Lumo mark gutter, soft `LumoCard`, status chip `Lista para cobrar`, product rows (name, user-facing quantity and unit price, right-aligned line total), and a total row from `data.total`. Display labels MUST remain `kilogram`→`kg`, `gram`→`g`, `unit`→`unidad`, `package`→`paquete`. Flutter MUST format server strings only and MUST NOT sum `line_total`s or recompute `total`. When the three payment actions are present it MUST show the prompt `¿Cómo pagó?` and buttons labeled `Efectivo`, `Tarjeta`, and `Transferencia` mapped from those action ids. It MUST NOT show Registrar, Corregir, an authorization field, or a POS table. Unknown versions MUST show `fallback_text` and MUST NOT run actions.

#### Scenario: Summary card content
- **WHEN** the renderer receives a `sale_summary@1` payload with Zanahoria `22.50` and Tomate `10.00` and `total.amount` `32.50`
- **THEN** it MUST show both product names, both line totals, status `Lista para cobrar`, and total `$32.50` without adding 22.50 + 10.00 on the client

#### Scenario: Payment buttons follow emitted actions
- **WHEN** the payload includes the three payment actions
- **THEN** the card MUST show Efectivo, Tarjeta, and Transferencia and MUST NOT show a fourth method

#### Scenario: Unknown version falls back
- **WHEN** the payload is `sale_summary` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT execute actions

### Requirement: Summary fits Inicio without redesign
The summary MUST appear in the existing Inicio conversation stream as an assistant artifact: unbubbled, Lumo-mark gutter, warm canvas, max-width 420px. It MUST be a compact structured card, not a desktop table. Navigation and the sticky composer MUST remain. Typing a payment phrase MUST remain valid.

#### Scenario: Totalizar on Inicio
- **WHEN** the signed-in Carrota user submits `totalizar` after a multi-item sale
- **THEN** the stream MUST show the user bubble for that text and a Lumo-mark `sale_summary@1` card whose visible total matches the server payload

#### Scenario: Typed payment still works
- **WHEN** the user types `efectivo` instead of tapping Efectivo
- **THEN** the client MUST send that phrase to `POST /api/v1/lumo/messages`

### Requirement: Summary rows include free-concept names
`sale_summary@1` MUST stay version `1`. Each item `product_name` MUST be that line's `product_name_snapshot`, including a free-concept snapshot. The row MUST use the existing quantity, unit label, unit price, and server line total. Flutter MUST show `product_name` exactly as supplied, including accents and casing. The payload MUST NOT add a source badge or a save-to-catalog action. `data.total` MUST remain the Decimal sum of persisted line totals. Flutter MUST NOT sum the rows.

#### Scenario: Mixed summary names
- **WHEN** totalize commits a session with Zanahoria `22.50` and `bolsas de hielo` `36.00`
- **THEN** `sale_summary@1` `data.items` MUST include both `product_name` values and `data.total.amount` MUST be `58.50`

#### Scenario: Renderer does not label the concept
- **WHEN** Flutter renders that summary
- **THEN** it MUST show `bolsas de hielo` and MUST NOT show "Concepto libre"

#### Scenario: Renderer keeps an accented summary name
- **WHEN** a summary item has `product_name` `Café Molido`
- **THEN** Flutter MUST show `Café Molido` and MUST NOT show `cafe molido`

### Requirement: Summary rows show an adjusted catalog price
`sale_summary@1` MUST remain version `1`. An override item MUST include `catalog_unit_price` as the snapshot money object and MUST keep `unit_price` as the charged price and `line_total` as the persisted total. A normal catalog item and a free-concept item MUST omit `catalog_unit_price`. The payload MUST NOT include the reason. `data.total` MUST remain the Decimal sum of persisted line totals. Flutter MUST show `Precio ajustado · antes $20.00/kg` on a row only when that item has `catalog_unit_price`, and MUST NOT sum the rows.

#### Scenario: Mixed summary keeps the charged Tomate total
- **WHEN** totalize commits a session with Zanahoria `22.50` and a Tomate override line `27.00`
- **THEN** the Tomate item MUST include `catalog_unit_price.amount` `20.00` and `unit_price.amount` `30.00`, the Zanahoria item MUST omit `catalog_unit_price`, and `data.total.amount` MUST be `49.50`

#### Scenario: Renderer captions only the override row
- **WHEN** Flutter renders that summary
- **THEN** it MUST show `Precio ajustado · antes $20.00/kg` on Tomate and MUST NOT show that caption on Zanahoria

