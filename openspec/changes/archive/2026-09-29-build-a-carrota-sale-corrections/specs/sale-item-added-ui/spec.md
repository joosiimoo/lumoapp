## MODIFIED Requirements

### Requirement: Register sale_item_added@1
`GenerativeUIRegistry` MUST register component `sale_item_added` version `1`. `GenerativeUIComposer` MUST emit this contract only after a committed `sale.add_item@1` and MUST refuse unknown components. The backend MUST NOT render Flutter widgets or HTML.

The contract MUST be:

```json
{
  "component": "sale_item_added",
  "version": 1,
  "data": {
    "sale_session_id": "<uuid>",
    "sale_item_id": "<uuid>",
    "product_name": "Zanahoria",
    "quantity_input": "900",
    "unit_input": "gram",
    "quantity_normalized": "0.900",
    "unit_normalized": "kilogram",
    "unit_price": {"amount": "25.00", "currency": "MXN"},
    "line_total": {"amount": "22.50", "currency": "MXN"},
    "session_item_count": 1,
    "session_total": {"amount": "22.50", "currency": "MXN"}
  },
  "actions": [
    {
      "action_id": "sale.remove_item@1",
      "option_id": null,
      "context_token": "<ui_action jwt>",
      "idempotency_key": "<server uuid>"
    }
  ],
  "fallback_text": "Agregué 0.900 kg de Zanahoria · $22.50"
}
```

`actions` MUST contain exactly one `sale.remove_item@1` whose token binds this card's `sale_session_id` and `sale_item_id`. Money MUST be decimal strings plus `MXN`. `fallback_text` MUST be server-provided and MUST contain the confirmed product and line total.

#### Scenario: Composer emits after commit
- **WHEN** `sale.add_item@1` has committed the golden Zanahoria item
- **THEN** the agent response `ui` MUST include exactly one `sale_item_added` version `1` payload whose `data.line_total.amount` is `22.50` and whose `actions` include `sale.remove_item@1`

#### Scenario: Unregistered component still refused
- **WHEN** the composer is asked to emit `sale_confirmed_card@1`
- **THEN** the backend MUST refuse to include it

## ADDED Requirements

### Requirement: Flutter remove control on the item card
Flutter MUST render a secondary remove control for `sale.remove_item@1` on `sale_item_added@1` without becoming a POS editor. Tapping MUST post the existing UI action endpoint with the server token and idempotency key. Flutter MUST NOT recompute totals after remove; it MUST render the next server UI payload.

#### Scenario: Remove tap uses server action
- **WHEN** the merchant taps remove on the item card
- **THEN** Flutter MUST call `POST /api/v1/lumo/actions` with `sale.remove_item@1` and MUST NOT send a client total
