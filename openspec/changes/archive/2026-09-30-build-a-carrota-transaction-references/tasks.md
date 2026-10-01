## 1. ADR and migration foundation

- [x] 1.1 Write `docs/adr/ADR-033-transaction-references.md` as **Proposed**, explicitly recording: shared per-business stream; numeric storage + TRX display; entity columns; original sale vs void identity; race-safe first-allocation concurrency; migration-only Event Memory enrichment; historical idempotency-response compatibility exception; cash-count exclusion; Flutter non-generation
- [x] 1.2 Add Alembic `0018` following safe order: backfill-compatible columns + counter + RLS/FORCE RLS → drop/replace previous `business_events` exact-shape CHECK → deterministic entity sequence backfill → rewrite matching historical sale/void/close facts → install new exact-shape CHECK → final NOT NULL/CHECKs/uniques → initialize counter `last_value` from max
- [x] 1.3 Do **not** rewrite persisted pre-0018 idempotency response bodies
- [x] 1.4 Update domain/ORM models and persistence cleanup helpers; do not touch onboarding schema or the paused onboarding change
- [x] 1.5 Migration tests through base→head proving CHECK/backfill ordering, enriched facts, initialized counters, and RLS/FORCE RLS

## 2. Sequence allocator

- [x] 2.1 Implement server-only allocate helper: race-safe counter create (`INSERT … ON CONFLICT DO NOTHING` or equivalent) then authoritative `UPDATE … RETURNING last_value`, inside the caller's DB transaction
- [x] 2.2 Implement format helper `TRX-{value:06d}` with wider digits after 999999; never parse formatted strings for next-value logic
- [x] 2.3 Tests: first value, increment, tenant isolation, concurrent unique allocations, monotonicity, rollback safety
- [x] 2.4 Tests: concurrent first allocation with no counter row yet — distinct sequences, exactly one counter row, `last_value` reflects both commits

## 3. Sale confirm path

- [x] 3.1 In `CommitSaleSession` mutating path, allocate and persist `transaction_sequence` with payment/confirm in one transaction
- [x] 3.2 Ensure post-0018 idempotent replay and confirmed read-back return the stored formatted `transaction_number` without re-allocation
- [x] 3.3 Include `transaction_number` in `sale_confirmed@1` composer data and `sale_confirmed` Event Memory facts
- [x] 3.4 Tests: confirmed sale gets number; post-0018 payment replay returns same TRX; multi-item sale shares one sale number
- [x] 3.5 Tests: fresh entity read-back of a backfilled pre-0018 sale exposes TRX; exact pre-0018 stored idempotency replay MAY omit TRX and is not rewritten

## 4. Sale void path

- [x] 4.1 In `VoidSaleSession` mutating path, allocate distinct `void_transaction_sequence`; keep sale `transaction_sequence` immutable (do not replace sale identity with void number)
- [x] 4.2 Ensure repeated/idempotent void and concurrent void produce exactly one void sequence and return the stored numbers
- [x] 4.3 Extend void-result `sale_confirmed@1` (`status=voided`) and `sale_voided` facts with void + `original_transaction_number`; document void-result semantics vs original sale identity; keep separate Memoria events
- [x] 4.4 Tests: void number ≠ sale number; original reference persisted; replay/concurrent void do not double-allocate; presentation `TRX-void · Anula TRX-sale`

## 5. Daily close path

- [x] 5.1 In `ConfirmDailyClose` snapshot insert, allocate and persist `transaction_sequence`
- [x] 5.2 Ensure post-0018 close replay/read-back returns the same number; stale/failed confirm allocates no committed close reference
- [x] 5.3 Include `transaction_number` in `daily_close_confirmed@1` and `daily_close_completed` facts
- [x] 5.4 Verify cash-count path still allocates no transaction number
- [x] 5.5 Tests: completed close gets number; post-0018 confirm replay same; stale/failed creates none; cash count has none

## 6. Memoria and confirmation UI

- [x] 6.1 Update Memoria feed mapping for sale TRX, void `TRX · Anula TRX`, close TRX; cash count unchanged; keep TRX visually secondary; keep separate sale_confirmed / sale_voided events
- [x] 6.2 Update Flutter `sale_confirmed@1` subtle confirmed TRX and void-result Anula presentation without Inicio redesign or client generation
- [x] 6.3 Update Flutter `daily_close_confirmed@1` subtle `Día cerrado · TRX-…` (or equivalent) without Hoy/Inicio redesign
- [x] 6.4 Tests/widget coverage: sale/void/close TRX render; cash count has no TRX; no client-side generation helpers for sequences — validated manually by Carrota acceptance

## 7. Sales export

- [x] 7.1 Add `sale_transaction_number` and `void_transaction_number` columns to CSV/XLSX writers and column metadata; keep existing technical ids
- [x] 7.2 Repeat sale/void references on every SaleItem row; blank void column for confirmed rows
- [x] 7.3 Update XLSX column widths for the two new columns
- [x] 7.4 Tests: confirmed/voided/multi-item row behavior for both columns including backfilled historical rows

## 8. Regression and validation

- [x] 8.1 Regression: sale corrections, Daily Close, Memoria timeline behavior unchanged except additive TRX; onboarding untouched
- [x] 8.2 Run targeted backend test suites for confirm/void/close/memory/export/sequence/migration-order/idempotency-compatibility (Flutter suite deferred to owner)
- [x] 8.3 Run `openspec validate build-a-carrota-transaction-references --strict` after any spec edits during implementation
- [x] 8.4 Manual Carrota acceptance checklist for TRX on confirm, void Memoria line, close confirm, and export columns; then Accept ADR-033
