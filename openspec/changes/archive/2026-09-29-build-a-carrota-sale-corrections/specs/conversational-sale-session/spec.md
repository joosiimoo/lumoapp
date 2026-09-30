## ADDED Requirements

### Requirement: Merchant can remove an item from the active sale
While the interaction context has an `open` or `ready_to_charge` session, removing a specific line MUST call `sale.remove_item@1` for that `sale_item_id`. The conversation MUST stay on the same session. After remove, the merchant MUST see the updated remaining items and total from the server. Removing the last item MUST leave an empty active sale without confirming payment.

#### Scenario: Remove mid-sale continues the same session
- **WHEN** the merchant removes one line from a multi-item open sale
- **THEN** later add-item on the same conversation MUST reuse that same session id

#### Scenario: Empty sale is not a confirmation
- **WHEN** the merchant removes the final line before payment
- **THEN** the response MUST NOT emit `sale_confirmed@1` and MUST NOT record a `Payment`

### Requirement: Merchant can void a confirmed sale on an open day from Memoria
After a sale is `confirmed` and its OperationalDay is still `open`, the merchant MAY void that sale through the explicit void confirmation path started from Memoria (`sale.void.request@1` → reason + server impact → `sale.void.confirm@1`). The void MUST require a non-empty reason. Inicio and Hoy MUST NOT be void entry points. A voided sale MUST remain inspectable as voided and MUST NOT be presented as a live confirmed sale in Hoy operational totals.

#### Scenario: Void after confirm on open day
- **WHEN** the merchant confirms void for today's confirmed sale with a reason from Memoria
- **THEN** the sale MUST become `voided` and Hoy live totals MUST exclude it

#### Scenario: Void is not undo-without-trace
- **WHEN** a confirmed sale is voided
- **THEN** the original confirmation facts MUST remain in Event Memory beside the void event
