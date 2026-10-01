## ADDED Requirements

### Requirement: Transaction number identifies a committed business transaction
A `transaction_number` MUST identify one committed business transaction/event for a tenant, not a mutable business entity identity. User-facing terminology MUST be **Número de transacción**. The backend API/export field name MUST be `transaction_number` (formatted string). UUIDv7 domain ids MUST remain the authoritative technical primary keys. A `transaction_number` MUST NOT replace those primary keys.

#### Scenario: Sale and void are different transactions
- **WHEN** a confirmed sale later voids successfully
- **THEN** the sale and the void MUST have different `transaction_number` values

#### Scenario: Technical ids stay primary
- **WHEN** a confirmed sale is stored
- **THEN** `sale_sessions.id` MUST remain the primary key and `transaction_number` MUST be a separate support identifier

### Requirement: Build A numbered transaction types
Build A MUST assign a `transaction_number` only to these successful committed outcomes: sale confirmed, sale voided, and daily close completed. Cash-count recording MUST NOT receive a `transaction_number`. Failed, rolled-back, stale, clarify, totalize, item-remove, and open/`ready_to_charge` sessions MUST NOT appear as numbered committed transactions.

#### Scenario: Cash count has no number
- **WHEN** a CashCount is recorded successfully
- **THEN** no `transaction_number` MUST be allocated or persisted for that count

#### Scenario: Failed close allocates nothing
- **WHEN** `closing.confirm@1` fails or is stale before a ClosingSnapshot commits
- **THEN** no new committed transaction reference MUST exist from that attempt

### Requirement: Format TRX with numeric sequence storage
The display prefix MUST be the fixed string `TRX` and MUST NOT be configurable in Build A. Initial display format MUST be `TRX-{zero-padded sequence}` with width 6 (example `TRX-000001`). After sequence `999999`, display MUST continue with more digits without wrapping or resetting (example `TRX-1000000`). Persistence MUST store a numeric sequence (`BIGINT`) separately from display formatting. Domain allocation and uniqueness MUST use the numeric sequence. Formatted `transaction_number` strings MUST be produced by one server formatting helper at API, Event Memory facts, UI contract, and export boundaries.

#### Scenario: First number formats with six digits
- **WHEN** a business allocates its first sequence value `1`
- **THEN** the formatted `transaction_number` MUST be `TRX-000001`

#### Scenario: Storage is numeric
- **WHEN** a confirmed sale is persisted
- **THEN** the row MUST store a numeric sequence column and MUST NOT rely on parsing `TRX-…` strings to allocate the next value

### Requirement: Per-business atomic sequence
Each business MUST have one shared monotonic sequence for all Build A numbered transaction types. Allocation MUST be concurrency-safe, tenant-isolated, and integrated in the same database transaction as the successful business mutation. The allocator MUST NOT use `COUNT(*)+1` and MUST NOT accept client-supplied numbers. Flutter MUST NEVER generate transaction numbers. Concurrent allocations MUST NOT produce duplicate sequences within a `business_id`. Gaps MUST be acceptable if required by concurrency or transaction safety; Build A MUST keep allocation and entity persistence in one transaction so a rollback does not leave a durable committed reference without an entity. Counter-row creation for a business with no row yet MUST be race-safe (for example `INSERT … ON CONFLICT DO NOTHING` or equivalent). The authoritative increment MUST be `UPDATE … SET last_value = last_value + 1 … RETURNING last_value`.

#### Scenario: Tenant isolation
- **WHEN** business A and business B each confirm their first sale
- **THEN** each MAY receive `TRX-000001` within its own business and MUST NOT share one global sequence

#### Scenario: Concurrent allocations are unique
- **WHEN** two concurrent mutating requests for the same business each require a new number
- **THEN** the two committed sequences MUST be different

#### Scenario: Concurrent first allocation without a counter row
- **WHEN** a business has no `business_transaction_counters` row and two concurrent transactions each require their first transaction number
- **THEN** both successful commits MUST receive distinct sequences, exactly one counter row MUST exist for that business, and `last_value` MUST equal the higher of the two committed sequences

#### Scenario: Client generation is forbidden
- **WHEN** a Flutter client omits or invents a transaction number on confirm, void, or close
- **THEN** the server MUST allocate or read back the authoritative number and MUST NOT trust a client-generated value

### Requirement: Immutability and idempotent replay
Once assigned, a transaction sequence on an entity MUST be immutable. For operations first committed after migration `0018`, exact idempotency replay of a successful confirm, void, or close MUST return the same persisted `transaction_number` in the stored response body and MUST NOT allocate another sequence. Non-mutating fresh entity read-back MUST also return the stored formatted number without re-allocation.

#### Scenario: Payment replay keeps the same number
- **WHEN** a successful post-0018 `sale.commit@1` is retried with the same idempotency key and payload hash
- **THEN** the response MUST expose the same `transaction_number` and exactly one sequence MUST exist for that sale

#### Scenario: Sequence is not rewritten on void
- **WHEN** a confirmed sale is later voided
- **THEN** the sale's original `transaction_sequence` MUST remain unchanged and the void MUST use a different sequence

### Requirement: Original sale vs void transaction identity
The confirmed sale transaction MUST always own and preserve its original sale `transaction_number`. A void MUST own a different `transaction_number`. An explicit void result or `sale_voided` event MAY present `"{void_transaction_number} · Anula {original_sale_transaction_number}"`. The system MUST NOT semantically replace the original confirmed sale's transaction number with the void number. Memoria MUST keep separate `sale_confirmed` and `sale_voided` events; the `sale_confirmed` event MUST retain the sale number and the `sale_voided` event MUST carry the void number plus the original sale number.

#### Scenario: Void presentation references original without replacing it
- **WHEN** sale `TRX-000101` is voided as `TRX-000105`
- **THEN** the sale sequence MUST remain `TRX-000101`, the void sequence MUST be `TRX-000105`, and void presentation MAY show `TRX-000105 · Anula TRX-000101`

#### Scenario: Memoria keeps both events
- **WHEN** a sale is confirmed and later voided
- **THEN** both a `sale_confirmed` event with the sale TRX and a `sale_voided` event with void TRX plus original TRX MUST exist

### Requirement: Pre-0018 idempotency response compatibility
Migration MUST NOT migrate or rewrite persisted pre-0018 idempotency response bodies. For historical operations assigned a TRX by migration backfill, fresh entity read-back, Event Memory, and export MUST expose the backfilled `transaction_number`. Pre-0018 exact persisted idempotency response bodies MAY remain in their historical shape without TRX. This is a migration compatibility exception only and MUST NOT weaken post-0018 idempotency requirements.

#### Scenario: Fresh read-back of backfilled sale exposes TRX
- **WHEN** a pre-0018 confirmed sale receives a backfilled sequence and a fresh confirmed read-back is composed from the entity
- **THEN** the read-back MUST include the backfilled `transaction_number`

#### Scenario: Pre-0018 stored replay may omit TRX
- **WHEN** an exact idempotency replay returns a response body persisted before `0018`
- **THEN** that stored body MAY omit `transaction_number` and MUST NOT be rewritten by migration
