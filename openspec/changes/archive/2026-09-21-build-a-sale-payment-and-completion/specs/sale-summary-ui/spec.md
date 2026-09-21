## MODIFIED Requirements

### Requirement: Register sale_summary@1
`GenerativeUIRegistry` MUST register component `sale_summary` version `1`. `GenerativeUIComposer` MUST emit this contract after a committed `sale.totalize@1` **transition**, and MAY emit the same contract as a current-state read-back when the session is already `ready_to_charge`. It MUST NOT emit `sale_summary@1` after `sale.commit@1` or for a `confirmed` session. It MUST refuse unknown components. The backend MUST NOT render Flutter widgets or HTML. `actions` MUST be empty. Money MUST be decimal strings plus `MXN`. `fallback_text` MUST be server-provided and MUST contain the item count and total.

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

`subtotal` MUST equal `total` in this change (no discounts). `data.total.amount` MUST equal the Decimal sum of the persisted item `line_total`s. Item order MUST be persistence order (`created_at` ascending). `data.status` MUST be `ready_to_charge`.

#### Scenario: Composer emits after committed totalize
- **WHEN** `sale.totalize@1` has committed an open two-item session totaling `32.50` MXN
- **THEN** the agent response `ui` MUST include exactly one `sale_summary` version `1` payload whose `data.status` is `ready_to_charge` and whose `data.total.amount` is `32.50`

#### Scenario: Composer emits current summary on ready_to_charge read-back
- **WHEN** the session is already `ready_to_charge` and the actor posts `totalizar` with a new idempotency key
- **THEN** the response `ui` MUST include `sale_summary@1` built from currently persisted items and MUST NOT depend on a second totalize commit

#### Scenario: Confirmed sale does not reuse sale_summary
- **WHEN** `sale.commit@1` has committed and the session is `confirmed`
- **THEN** the agent response `ui` MUST NOT include `sale_summary@1`

#### Scenario: Unregistered confirmed-sale card still refused
- **WHEN** the composer is asked to emit `sale_confirmed_card@1` or `sale_ready_to_charge@1`
- **THEN** the backend MUST refuse to include it
