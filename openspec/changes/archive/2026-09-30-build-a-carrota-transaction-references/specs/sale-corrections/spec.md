## ADDED Requirements

### Requirement: Void allocates its own transaction number and references the sale
A successful void mutate MUST allocate a new per-business sequence into `void_transaction_sequence` and MUST leave the sale `transaction_sequence` unchanged. The confirmed sale transaction MUST always own and preserve its original sale `transaction_number`; the void MUST NOT overwrite or semantically replace that number. The void relationship exposed to UI, Event Memory, and export MUST use the persisted sale sequence as `original_transaction_number` (or `original_sale_transaction_number`) and the void sequence as the void `transaction_number`. An explicit void result/event MAY present `"{void_transaction_number} · Anula {original_sale_transaction_number}"`. Flutter MUST NOT reconstruct the Anula relationship without those server fields. Memoria MUST keep separate `sale_confirmed` and `sale_voided` events.

#### Scenario: Void number differs from sale number
- **WHEN** sale `TRX-000101` is voided successfully
- **THEN** the void MUST receive a different number such as `TRX-000105` and MUST preserve original `TRX-000101` on the sale sequence and on the historical `sale_confirmed` event

#### Scenario: Repeated void does not allocate again
- **WHEN** an already-voided session is voided again or the original void is idempotently replayed
- **THEN** the stored `void_transaction_sequence` MUST be unchanged and no additional sequence MUST be allocated

#### Scenario: Concurrent void creates one void reference
- **WHEN** two concurrent void attempts target the same confirmed session
- **THEN** exactly one `void_transaction_sequence` MUST exist for that session after both complete
