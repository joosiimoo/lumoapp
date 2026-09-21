## Purpose

Versioned `sale_summary@1` contract for a totalized sale. The backend composes it after commit; Flutter renders server-provided lines and totals without calculating them.

## ADDED Requirements

### Requirement: Register sale_summary@1
`GenerativeUIRegistry` MUST register component `sale_summary` version `1`. `GenerativeUIComposer` MUST emit this contract after a committed `sale.totalize@1` **transition**, and MAY emit the same contract as a current-state read-back when the session is already `ready_to_charge`. It MUST refuse unknown components. The backend MUST NOT render Flutter widgets or HTML. `actions` MUST be empty. Money MUST be decimal strings plus `MXN`. `fallback_text` MUST be server-provided and MUST contain the item count and total.

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
      },
      {
        "sale_item_id": "<uuid>",
        "product_name": "Tomate",
        "quantity_normalized": "0.500",
        "unit_normalized": "kilogram",
        "unit_price": {"amount": "20.00", "currency": "MXN"},
        "line_total": {"amount": "10.00", "currency": "MXN"}
      }
    ]
  },
  "actions": [],
  "fallback_text": "Venta lista para cobrar · 2 artículos · $32.50"
}
```

`subtotal` MUST equal `total` in this change (no discounts). `data.total.amount` MUST equal the Decimal sum of the persisted item `line_total`s. Item order MUST be persistence order (`created_at` ascending).

#### Scenario: Composer emits after committed totalize
- **WHEN** `sale.totalize@1` has committed an open two-item session totaling `32.50` MXN
- **THEN** the agent response `ui` MUST include exactly one `sale_summary` version `1` payload whose `data.status` is `ready_to_charge` and whose `data.total.amount` is `32.50`

#### Scenario: Composer emits current summary on ready_to_charge read-back
- **WHEN** the session is already `ready_to_charge` and the actor posts `totalizar` with a new idempotency key
- **THEN** the response `ui` MUST include `sale_summary@1` built from currently persisted items and MUST NOT depend on a second totalize commit

#### Scenario: Unregistered confirmed-sale card still refused
- **WHEN** the composer is asked to emit `sale_confirmed_card@1` or `sale_ready_to_charge@1`
- **THEN** the backend MUST refuse to include it

### Requirement: Flutter maps sale_summary@1
Flutter `GenerativeUIRenderer` MUST register `sale_summary` version `1`. It MUST render a compact conversation card using existing Lumo language: Lumo mark gutter, soft `LumoCard`, accent status chip, product rows (name, user-facing quantity and unit price, right-aligned line total), and a total row. Display labels MUST remain `kilogram`→`kg`, `gram`→`g`, `unit`→`unidad`, `package`→`paquete`. Flutter MUST format server strings only and MUST NOT sum `line_total`s or recompute `total`. It MUST NOT show payment chips, Registrar, Corregir, or a POS table. Unknown versions MUST show `fallback_text` and MUST NOT run actions.

#### Scenario: Summary card content
- **WHEN** the renderer receives a `sale_summary@1` payload with Zanahoria `22.50` and Tomate `10.00` and `total.amount` `32.50`
- **THEN** it MUST show both product names, both line totals, item count `2`, status ready to charge, and total `$32.50` without adding 22.50 + 10.00 on the client

#### Scenario: Unknown version falls back
- **WHEN** the payload is `sale_summary` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT execute actions

### Requirement: Summary fits Inicio without redesign
The summary MUST appear in the existing Inicio conversation stream as an assistant artifact: unbubbled, Lumo-mark gutter, warm canvas, max-width 420px. It MUST be a compact structured card, not a desktop table. Navigation and composer behavior MUST be unchanged.

#### Scenario: Totalizar on Inicio
- **WHEN** the signed-in Carrota user submits `totalizar` after a multi-item sale
- **THEN** the stream MUST show the user bubble for that text and a Lumo-mark `sale_summary@1` card whose visible total matches the server payload
