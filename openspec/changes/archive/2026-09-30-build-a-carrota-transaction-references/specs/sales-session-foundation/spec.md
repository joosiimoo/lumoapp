## ADDED Requirements

### Requirement: SaleSession stores sale and void transaction sequences
`sales.sale_sessions` MUST gain nullable `transaction_sequence BIGINT` and nullable `void_transaction_sequence BIGINT`. On successful confirm, `transaction_sequence` MUST be set to the newly allocated per-business sequence and MUST remain set after void. On successful void mutate, `void_transaction_sequence` MUST be set to a different newly allocated sequence. Open and `ready_to_charge` sessions MUST keep both NULL. CHECK constraints MUST enforce: `status IN ('confirmed','voided')` implies `transaction_sequence IS NOT NULL`; `status = 'voided'` implies `void_transaction_sequence IS NOT NULL`; non-voided statuses imply `void_transaction_sequence IS NULL`. Partial UNIQUE indexes MUST enforce uniqueness of non-null `(business_id, transaction_sequence)` and `(business_id, void_transaction_sequence)`.

#### Scenario: Confirm stores sale sequence
- **WHEN** `sale.commit@1` confirms a session
- **THEN** that row MUST store a non-null `transaction_sequence` and NULL `void_transaction_sequence`

#### Scenario: Void stores a second sequence
- **WHEN** that confirmed session is voided
- **THEN** `transaction_sequence` MUST be unchanged and `void_transaction_sequence` MUST be a different non-null value
