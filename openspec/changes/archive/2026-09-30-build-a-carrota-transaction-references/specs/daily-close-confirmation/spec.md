## ADDED Requirements

### Requirement: Successful close confirmation allocates a transaction number
The mutating path of `closing.confirm@1` that inserts a ClosingSnapshot MUST allocate one per-business sequence into that snapshot in the same write transaction. Idempotent replay and already-closed read-back MUST return the same formatted `transaction_number` and MUST NOT allocate another. Stale confirmation, invalid/missing token, and any failure before snapshot commit MUST NOT create a committed transaction reference.

#### Scenario: Close gets a number
- **WHEN** `closing.confirm@1` commits successfully
- **THEN** the ClosingSnapshot MUST have a `transaction_sequence` and responses MUST expose its formatted `transaction_number`

#### Scenario: Close replay keeps the same number
- **WHEN** the same successful close is replayed with the same idempotency key and payload hash
- **THEN** the returned `transaction_number` MUST equal the original and no second sequence MUST be allocated

#### Scenario: Stale confirm allocates nothing
- **WHEN** confirmation is stale and no snapshot is inserted
- **THEN** the business transaction counter MUST NOT advance as a committed close reference for that attempt
