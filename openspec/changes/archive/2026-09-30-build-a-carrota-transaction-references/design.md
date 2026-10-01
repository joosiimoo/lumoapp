## Context

Today every durable business object uses UUIDv7 primary keys. Merchants and support have no shared human-readable handle for a confirmed sale, a void of that sale, or a completed daily close. Soft void (ADR-031) lives on the same `SaleSession` row (`confirmed` → `voided`) with `voided_at` / `voided_by_actor_id` / `void_reason`. Closing is a separate immutable `ClosingSnapshot` (ADR-018 / ADR-032). Factual Event Memory stores exact fact key sets per event type; Memoria hides UUIDs. Sales export is one row per `SaleItem` with `sale_status` including voided rows. There are no PostgreSQL sequences or merchant folios in migrations through `0017`.

Authority: PRD v0.11 (audit/evidence RF-057, Event Memory RF-086, cancellation §21.7). Product decision for this slice: display `TRX-000001`, user-facing **Número de transacción**, backend field `transaction_number`, one shared per-business stream across sale confirm, sale void, and daily close completed. Cash-count recording is intentionally not numbered.

## Goals / Non-Goals

**Goals:**

- Server-allocated, tenant-isolated, immutable transaction references for exactly three committed outcomes: sale confirmed, sale voided, daily close completed.
- Atomic concurrency-safe sequence; idempotent replay returns the original number; failed/rolled-back ops allocate nothing durable.
- Persist both the original sale number and a distinct void number for voided sales; relationship is domain data, not Flutter reconstruction.
- Minimal additive exposure in confirmation UI, Memoria, and CSV/XLSX export.
- Deterministic backfill for historical committed rows when safe.

**Non-Goals:**

- Search-by-TRX, receipts, fiscal folios, QR/barcodes, refunds, mixed payments, configurable/branch numbering, cash-count numbering, generic ledger platform, onboarding changes, Inicio/Hoy redesign.

## Decisions

### 1. What a transaction number represents

A `transaction_number` identifies one **committed business transaction/event**, not a mutable entity identity.

| Outcome | Example | Number |
|---------|---------|--------|
| Sale confirmed | Venta en efectivo por $120.00 | TRX-000101 |
| Sale voided | Venta anulada (of TRX-000101) | TRX-000105 (new) |
| Daily close completed | Cierre completado | TRX-000110 |

UUIDs remain authoritative technical identifiers. Flutter MUST NEVER generate numbers.

**Cash count distinction:** `CashCount` / `cash_count_recorded` is an intermediate operational fact while the day stays open. Confirmed sale, sale void, and completed close are committed business outcomes and are numbered. Cash count stays unnumbered in this slice.

### 2. Format and storage representation

- **Prefix:** fixed `TRX` (not configurable in Build A).
- **Display:** `TRX-{zero-padded sequence}` with initial width **6** (`TRX-000001`).
- **After 999999:** continue with wider digit width without padding truncation (`TRX-1000000`); do not wrap or reset.
- **Storage:** persist **numeric** `transaction_sequence BIGINT` (and `void_transaction_sequence` where needed). Format to `transaction_number` only at API/UI/export boundaries via one server helper. Domain logic MUST NOT parse formatted strings for allocation or equality of “next value.”
- **API/export field name:** `transaction_number` (string). Export columns: `sale_transaction_number`, `void_transaction_number`.

**Rejected:** storing only the formatted string as the sole source of truth (forces parse for sequencing).

### 3. Sequence / concurrency strategy

**Shared per-business counter** (one stream for all numbered types), not per-type sequences — matches product examples where sale, void, and close interleave in one TRX space.

New table (name finalized at implementation; conceptual):

```text
operations.business_transaction_counters
  business_id UUID PRIMARY KEY  -- FK identity.businesses
  last_value  BIGINT NOT NULL DEFAULT 0
```

- RLS: same `business_id::text = current_setting('app.current_business_id', true)` pattern as other operations tables; FORCE RLS.
- **Allocate** inside the business write transaction:

  1. Ensure counter row exists for `business_id` with a **race-safe insert**: `INSERT … ON CONFLICT DO NOTHING` (or equivalent) for `(business_id)` with `last_value=0`. Migration MAY also seed rows for existing businesses; runtime must not assume a row already exists.
  2. Authoritative increment: `UPDATE … SET last_value = last_value + 1 WHERE business_id = :id RETURNING last_value` (row lock).

- **Concurrent first allocation (no counter row yet):** two concurrent transactions that each need a first number MUST both succeed with **distinct** sequences; exactly **one** counter row MUST exist afterward; `last_value` MUST reflect both committed allocations. Race-safe insert + `UPDATE … RETURNING` is required; do not use a non-atomic check-then-insert.
- **No** `COUNT(*)+1`, **no** client generation, **no** advisory-lock-only design without the counter row.
- **Concurrency:** concurrent allocators serialize on the counter row once it exists; each `RETURNING` value is unique within the business.
- **Monotonicity:** values increase; **gaps are acceptable** if a transaction allocates then rolls back (or if a future safety path burns a value). Prefer allocate-then-write-entity in the same DB transaction so a rollback releases the uncommitted counter update as well — **no durable gap from rollback** when allocation and entity write share one transaction. Gaps remain acceptable if product later needs pre-allocation outside the entity txn; Build A MUST keep allocation and entity persistence in one transaction.
- **Idempotency:** allocate only on the real mutating path that first commits the outcome. Replay / read-back / already-confirmed / already-voided / already-closed paths MUST read stored sequences and MUST NOT call the allocator.
- **Tenant isolation:** counter PK is `business_id`; RLS prevents cross-tenant reads/writes. No global sequence.

**Rejected alternatives:** PostgreSQL `SEQUENCE` per tenant (DDL proliferation); `MAX(sequence)+1` without locking; application UUID-as-display.

### 4. Persistence model (minimal)

**Prefer entity columns + counter table** over a polymorphic transaction ledger for Build A.

Rationale: soft void already keeps sale+void on one `SaleSession` (ADR-031 rejected a separate void table as primary truth); ClosingSnapshot is already the close document; Event Memory uniqueness is entity-keyed; export already joins from sale sessions/items.

| Location | Columns | When set |
|----------|---------|----------|
| `sales.sale_sessions` | `transaction_sequence BIGINT NULL` | On successful confirm only |
| `sales.sale_sessions` | `void_transaction_sequence BIGINT NULL` | On successful void mutate only |
| `operations.closing_snapshots` | `transaction_sequence BIGINT NOT NULL` | On insert in successful confirm |

Constraints (conceptual):

- CHECK: `status IN ('confirmed','voided')` ⇒ `transaction_sequence IS NOT NULL`; open/ready_to_charge ⇒ both sequences NULL.
- CHECK: `status = 'voided'` ⇒ `void_transaction_sequence IS NOT NULL`; else void sequence NULL.
- Partial UNIQUE `(business_id, transaction_sequence)` WHERE `transaction_sequence IS NOT NULL`.
- Partial UNIQUE `(business_id, void_transaction_sequence)` WHERE `void_transaction_sequence IS NOT NULL`.
- UNIQUE `(business_id, transaction_sequence)` on `closing_snapshots`.

Cross-table uniqueness of sequence integers is **enforced by sole use of the counter allocator**, not by a single multi-table UNIQUE. Documented in ADR.

**Rejected for Build A sole source of truth:** generic `transaction_references(entity_type, entity_id, …)` ledger — extra dual-write and joins without improving soft-void semantics. May be revisited if future types proliferate.

**Do not overload one field:** sale number stays on `transaction_sequence` after void; void number is `void_transaction_sequence`. Never reuse the sale sequence for the void.

### 5. Sale → void reference model (resolved)

**Identity rules (final):**

- The confirmed sale transaction **always owns and preserves** its original sale `transaction_number` (`transaction_sequence`). Void MUST NOT overwrite or semantically replace that number.
- A void owns a **different** `transaction_number` (`void_transaction_sequence`).
- An explicit void result/event MAY present: `{void_transaction_number} · Anula {original_sale_transaction_number}`.
- Memoria continues to keep **separate** `sale_confirmed` and `sale_voided` events. The `sale_confirmed` event retains the sale TRX; the `sale_voided` event carries void TRX + original sale TRX.

Persisted on the same `SaleSession`:

- Original sale reference = format(`transaction_sequence`) → `sale_confirmed` facts `transaction_number`; void facts `original_transaction_number`; export `sale_transaction_number`.
- Void reference = format(`void_transaction_sequence`) → void facts / void-result UI `transaction_number` (void); export `void_transaction_number`.

**`sale_confirmed@1` with `status=voided`:** this variant represents the **void result / current void state** immediately after a successful void (or void read-back). It is **not** a rewritten identity of the original confirmed-sale transaction. In that variant, `data.transaction_number` is the **void** number and `data.original_transaction_number` is the preserved sale number. The original confirmed-sale transaction number remains on the entity’s `transaction_sequence` and on the historical `sale_confirmed` Event Memory row.

Memoria contract for voided sale:

```text
16:40 Venta anulada
TRX-000105 · Anula TRX-000101
…
```

The “Anula …” target MUST come from persisted `transaction_sequence` on that session (exposed as `original_transaction_number` in `sale_voided` facts), not from Flutter joining timelines.

Existing void audit (`sale_session_id`, void metadata, `sale_voided` event identity) remains intact.

### 6. Allocation sites and idempotency

| Mutation | Workflow | Allocate? |
|----------|----------|-----------|
| First confirm of a session | `CommitSaleSession` mutating path | Yes → `transaction_sequence` |
| Commit replay / confirmed read-back | same | No — return stored |
| First void of a confirmed session | `VoidSaleSession` mutating path | Yes → `void_transaction_sequence` |
| Void replay / already voided | same | No — return stored |
| First close confirm | `ConfirmDailyClose` snapshot insert | Yes → snapshot `transaction_sequence` |
| Close replay / closed read-back | same | No — return stored |
| Stale/failed close confirm | no snapshot | No |
| Cash count | `RecordCashCount` | No |
| Remove item / totalize / clarify | — | No |

Concurrent void attempts: existing session row lock + already-voided read-back ⇒ exactly one void sequence.

**Post-0018 idempotency (strict):** for operations first committed after migration `0018`, exact idempotency replay MUST return the same persisted `transaction_number` in the stored response body. Do not weaken this for new transactions.

**Pre-0018 idempotency compatibility (migration exception only):** Do **NOT** migrate or rewrite persisted pre-0018 idempotency response bodies. For historical operations that receive a TRX via backfill:

- Fresh entity read-back, Event Memory, and export MUST expose the backfilled `transaction_number`.
- Pre-0018 exact persisted idempotency response bodies MAY remain in their historical shape without TRX.

### 7. Event Memory facts (additive)

Extend exact fact key sets via migration `0018` ordered CHECK handling (§11):

- `sale_confirmed`: add `transaction_number` (formatted **sale** number). Historical row retains this sale number after void.
- `sale_voided`: add `transaction_number` (void) and `original_transaction_number` (sale). Separate event from `sale_confirmed`.
- `daily_close_completed`: add `transaction_number`.
- `cash_count_recorded`: **unchanged** — no TRX key.

Facts remain exact-key; no narrative fields. Historical facts are enriched **only in migration** when entity sequences are backfilled — not by rewriting idempotency bodies.

### 8. Confirmation UI

- `sale_confirmed@1` confirmed: additive `data.transaction_number` = sale TRX; subtle `Venta registrada · TRX-000101`. No card redesign.
- `sale_confirmed@1` voided (void result / current void state): `data.transaction_number` = void TRX; `data.original_transaction_number` = preserved sale TRX; MAY present `{void} · Anula {original}`. This does **not** rewrite the original confirmed-sale transaction identity (see §5).
- `daily_close_confirmed@1`: additive `data.transaction_number`; subtle `Día cerrado · TRX-…` without redesigning the card layout.
- Inicio/Hoy shell layout unchanged.

### 9. Memoria presentation

TRX is visually secondary (support/audit), not primary content.

- Sale: time + “Venta” + TRX line + primary payment sentence.
- Void: “Venta anulada” + `TRX-void · Anula TRX-original` + primary + motivo.
- Close: “Cierre” + TRX + existing primary/secondary.
- Cash count: unchanged, no TRX.
- No search-by-TRX.

### 10. Sales export CSV/XLSX

Add columns (keep existing UUID columns):

| Column | Confirmed | Voided |
|--------|-----------|--------|
| `sale_transaction_number` | TRX of sale | TRX of original sale |
| `void_transaction_number` | empty | TRX of void |

Multi-item sales: every `SaleItem` row repeats the same sale (and void, if any) reference. Do not create a general transaction export.

### 11. Historical backfill and migration `0018` order

Migration id expected: **`0018`** (after `0017`). Backfill **per business**, deterministic candidates:

- Sale assign: each session with `status IN ('confirmed','voided')` and `confirmed_at` set → type `sale`, time `confirmed_at`.
- Void assign: each `status = 'voided'` with `voided_at` → type `void`, time `voided_at`.
- Close assign: each ClosingSnapshot → type `close`, time `closed_at` / `created_at`.

Sort by `(occurred_at ASC, type_order ASC, entity_id ASC)` where `type_order` is sale=1, void=2, close=3.

**Implementation-safe migration order (required):**

1. Add counter table + sequence columns in a **backfill-compatible** state (nullable where needed; do not yet apply final NOT NULL / status CHECKs that require populated sequences).
2. Enable RLS + FORCE RLS on the counter table; verify policies.
3. **Drop/replace** the previous `business_events` exact-shape CHECK **before** rewriting historical facts (so enrichment is not rejected).
4. Deterministic entity sequence backfill (assign `1..N` to sale/void/close columns).
5. Rewrite matching historical `sale_confirmed` / `sale_voided` / `daily_close_completed` facts with formatted TRX keys (**migration-only** Event Memory enrichment).
6. Install the **new** exact-shape CHECK only **after** facts are migrated.
7. Apply final NOT NULL / status CHECKs and uniqueness indexes that depend on completed backfill.
8. Initialize each counter `last_value` from the assigned maximum for that business.
9. Do **not** rewrite pre-0018 idempotency response bodies.

**Invariant:** migration MUST NOT temporarily require new fact keys before historical rows have been enriched.

**Guarantees:** no duplicate sequences within a business; chronological as reasonably possible; open/`ready_to_charge` and cash counts untouched; Flutter never invents TRX.

**Tests:** Alembic base→head (and head→base if project practice) MUST prove this CHECK/backfill ordering.

### 12. ADR and migration

- **Migration: yes** — Alembic `0018` per §11 order.
- **ADR: yes** — prepare **ADR-033** at implementation time as **Proposed** until Carrota manual acceptance. MUST explicitly record:
  - shared per-business stream, numeric storage + TRX display, entity columns, cash-count exclusion, Flutter non-generation;
  - original sale vs void transaction identity (sale number preserved; void has distinct number; voided `sale_confirmed@1` is void-result state, not rewritten sale identity; separate Memoria events);
  - first-allocation concurrency (race-safe counter insert + `UPDATE … RETURNING`);
  - migration-only Event Memory enrichment;
  - historical idempotency-response compatibility exception (pre-0018 bodies not rewritten; post-0018 replay still strict).
  Does not rewrite ADR-015/018/031/032; extends them.
- Do **not** create the ADR file in this OpenSpec refinement; implementation task writes it.

### 13. Onboarding / parallel changes

Do not modify `openspec/changes/build-a-conversational-onboarding-and-minimum-configuration/` or onboarding runtime behavior.

## Risks / Trade-offs

- [Counter row contention under burst confirms] → Acceptable for Build A single-cashier pilots; row lock is correct; revisit sharding only if measured.
- [Cross-table sequence uniqueness not one DB constraint] → Single allocator + tests; ADR states invariant; optional future ledger table.
- [Exact-fact CHECK vs historical rows] → Ordered drop → enrich → install new CHECK (§11); migration tests through base→head.
- [Concurrent first insert of counter] → `INSERT … ON CONFLICT DO NOTHING` then `UPDATE … RETURNING`; tested explicitly.
- [Pre-0018 idempotency bodies lack TRX] → Compatibility exception only; fresh read-back/memory/export expose backfilled TRX; post-0018 replay remains strict.
- [Backfill ordering ties] → Stable sort key; gaps not used in backfill path.
- [Export consumers see new columns] → Additive only; document in `daily-sales-export` / `sales-export-ui`.
- [Wider TRX after 999999] → Document; no wrap; UI treats as opaque string.

## Migration Plan

1. Land ADR-033 Proposed + Alembic `0018` following §11 order (columns → drop old fact CHECK → backfill entities → enrich facts → new fact CHECK → final constraints → counter max → RLS verify).
2. Wire allocator (race-safe first insert + `UPDATE … RETURNING`) into confirm / void / close mutating paths only.
3. Extend composers, memory writer, export columns, Flutter subtle display.
4. Rollback: reverse migration drops columns/table (numbers lost); forward-only preferred in pilot.

## Open Questions

- Exact confirmation copy microcopy: chip `Venta registrada · TRX-…` vs secondary caption under title — resolve at implement against current Generative UI components; keep subtle.
- Counter table schema name (`operations.business_transaction_counters`) — finalize in migration to match existing schema conventions.
