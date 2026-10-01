## ADDED Requirements

### Requirement: Action responses pass through server transaction numbers
Existing generative UI action paths for sale payment, void confirm, and close confirm MUST pass through server-authored `transaction_number` fields on sale/close contracts when present. No new UiAction id is required for transaction numbering. Clients MUST NOT supply allocation inputs.

#### Scenario: Payment action confirmation includes TRX
- **WHEN** a successful `sale.pay.cash@1` (or equivalent) commits a sale
- **THEN** the returned `sale_confirmed@1` MUST include `data.transaction_number` from the server
