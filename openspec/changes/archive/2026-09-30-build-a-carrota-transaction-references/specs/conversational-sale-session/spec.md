## ADDED Requirements

### Requirement: Confirmed and voided sale responses expose transaction numbers
After a successful sale confirm, conversational and UI-bound responses that present the confirmed sale MUST include the server-formatted `transaction_number` for that sale. After a successful void, responses that present the voided sale MUST include the void `transaction_number` and the original sale `transaction_number` (or equivalent server fields `void_transaction_number` / `original_transaction_number`). Flutter MUST render those strings and MUST NOT invent or allocate numbers.

#### Scenario: Confirm response includes TRX
- **WHEN** `sale.commit@1` confirms a sale that received sequence `101`
- **THEN** the response contract MUST expose `transaction_number` `TRX-000101`

#### Scenario: Void response references original
- **WHEN** that sale is voided and receives void sequence `105`
- **THEN** the response MUST expose void `TRX-000105` and original `TRX-000101`
