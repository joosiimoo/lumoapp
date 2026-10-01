# ADR-033: Transaction references

- Status: Accepted
- Date: 2026-09-30

## Context

Carrota merchants and Lumo support can only cite opaque UUIDv7 identifiers for confirmed sales, voids, and completed daily closes. Soft void (ADR-031) keeps sale and void on the same `SaleSession` row. Closing produces an immutable `ClosingSnapshot` (ADR-018 / ADR-032). There is no merchant-facing folio. Flutter must not invent identifiers. Event Memory uses exact fact key CHECKs that must be migrated carefully.

## Decision

### Per-business independent sequence

Each `business_id` owns an independent monotonic sequence in `operations.business_transaction_counters` (`business_id` PK, `last_value BIGINT NOT NULL DEFAULT 0`). Every business may start at `TRX-000001`. There is **no** global Lumo transaction sequence. Uniqueness of allocated values is scoped to `business_id`. Support must interpret `transaction_number` in business context.

### Storage and display

Persist numeric `BIGINT` sequences on entities. Format display strings with one server helper:

- `1` → `TRX-000001`
- `999999` → `TRX-999999`
- `1000000` → `TRX-1000000`

Do not parse formatted strings for sequencing. UUIDv7 domain ids remain the authoritative technical primary keys. Flutter never allocates TRX.

### Numbered outcomes

Allocate only for:

- sale confirmed → `sales.sale_sessions.transaction_sequence`
- sale voided → `sales.sale_sessions.void_transaction_sequence` (distinct from the sale sequence)
- daily close completed → `operations.closing_snapshots.transaction_sequence`

Cash-count recording is excluded. The confirmed sale always owns and preserves its original sale TRX. A void owns a different TRX and references the original sale TRX (`original_transaction_number`). `sale_confirmed@1` with `status=voided` is the void result / current void state, not a rewritten identity of the original confirmed-sale transaction. Memoria keeps separate `sale_confirmed` and `sale_voided` events.

### Allocation concurrency

Inside the same DB transaction as the business mutation:

1. Race-safe ensure counter row: `INSERT … ON CONFLICT DO NOTHING` (or equivalent).
2. Authoritative increment: `UPDATE … SET last_value = last_value + 1 RETURNING last_value`.

No `COUNT(*)+1`. Concurrent first allocation for a business with no counter row must produce distinct sequences, exactly one counter row, and a `last_value` that reflects both committed allocations. Gaps are acceptable when required by concurrency/transaction safety. Rollback of the business transaction rolls back the counter update when allocation and entity write share one transaction. Idempotent replay / non-mutating read-back must return stored sequences and must not allocate again.

### Migration and historical compatibility

Migration `0018` enriches historical Event Memory facts **only inside the migration**, after dropping the previous exact-shape CHECK and before installing the new CHECK. Pre-0018 persisted idempotency response bodies are **not** rewritten (compatibility exception). Fresh entity read-back, Event Memory, and export expose backfilled TRX. Post-0018 exact idempotency replay must still return the same persisted `transaction_number`.

## Consequences

- Alembic `0018` is required at implementation time.
- Export gains `sale_transaction_number` / `void_transaction_number`.
- Confirmation UI and Memoria show TRX as a subtle secondary caption only (not as the event/status chip).
- This ADR is Accepted after Carrota manual acceptance.
