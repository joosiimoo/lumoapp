## Why

Carrota merchants and Lumo support can only cite opaque UUIDv7s (`sale_session_id`, `closing_snapshot_id`) when referring to a completed sale, void, or daily close. There is no shared human-readable reference across those committed outcomes, so support and audit conversations are ambiguous. Product authority (`docs/PRD_Lumo_AI_Native_Managed_Business_Operations_v0.11.md`) already requires durable audit/evidence for operations and corrections (RF-057, RF-086, §21.7–21.8); this change adds the missing support identifier without inventing receipts, fiscal folios, or Build B behavior.

## What Changes

- Introduce a tenant-scoped, server-allocated **Número de transacción** (`transaction_number`) for committed business transactions only, display format `TRX-000001`.
- Assign one number per successful **sale confirmed**, **sale voided**, and **daily close completed**. A sale and its later void MUST receive different numbers; the void MUST persist a reference to the original sale number.
- Persist numbers immutably with the source entities; allocate via an atomic per-`business_id` sequence integrated with the existing write transaction (no Flutter generation, no `COUNT(*)+1`).
- Expose numbers additively in sale/close confirmation UI, Memoria Event Memory facts/rendering, and sales CSV/XLSX export (`sale_transaction_number`, `void_transaction_number`).
- Deterministic historical backfill for existing confirmed/voided sales and completed closes when safe; never invent numbers at render time.
- New ADR for the cross-domain transaction-reference invariant, concurrency (including race-safe first counter allocation), original-sale vs void identity, migration-only Event Memory enrichment, historical idempotency-response compatibility exception, and Flutter non-generation (Proposed until implementation + manual acceptance).
- Alembic migration `0018` required (ordered exact-fact CHECK drop → backfill → new CHECK).

## Non-goals

- Search by transaction number.
- Receipt/ticket generation, QR/barcodes, fiscal invoice/folio semantics.
- Refunds, mixed payments, transaction edit/reuse.
- Numbering cash-count events (cash count remains an intermediate operational fact).
- Branch-specific or configurable numbering; global cross-tenant sequence.
- Generic accounting ledger / event-platform redesign beyond this slice.
- Receipts, Build B features, or any change to paused onboarding (`build-a-conversational-onboarding-and-minimum-configuration`).
- Redesign of Inicio/Hoy beyond subtle confirmation presentation.

## Capabilities

### New Capabilities

- `transaction-references`: Cross-domain invariants for `transaction_number` (uniqueness, monotonicity, immutability, format, allocation, idempotency, rollback, Flutter non-generation), sequence/counter persistence, and which committed types are numbered in Build A.

### Modified Capabilities

- `sales-session-foundation`: Persist sale `transaction_sequence` on confirm and `void_transaction_sequence` on void; CHECKs/uniqueness; UUIDs remain PKs.
- `conversational-sale-session`: Confirmed-sale responses expose `transaction_number`; void responses expose void + original numbers.
- `sale-confirmed-ui`: Subtle confirmation presentation (`Venta registrada · TRX-…`); voided variant includes void/original references when present.
- `sale-corrections`: Successful void allocates its own number and preserves original sale number; idempotent/repeated void does not re-allocate.
- `closing-snapshot-foundation`: Persist `transaction_sequence` on completed ClosingSnapshot.
- `daily-close-confirmation`: Successful `closing.confirm@1` allocates one number; stale/failed confirm allocates none; replay returns the same number.
- `daily-close-confirmed-ui`: Subtle close confirmation presentation (`Día cerrado · TRX-…`).
- `factual-event-memory`: Additive fact keys for sale/void/close transaction references; cash-count facts unchanged (no TRX).
- `memoria-timeline`: Render secondary TRX lines for sale, void (+ Anula original), and close; cash count unchanged.
- `daily-sales-export`: Add `sale_transaction_number` and `void_transaction_number`; multi-item rows repeat the same values.
- `sales-export-ui`: Caption/schema awareness that export includes transaction reference columns (download UX otherwise unchanged).
- `persistence`: Alembic counter table + entity columns + backfill + RLS; uniqueness indexes.
- `generative-ui-actions`: No new action ids; response/read-back bodies that already carry sale/close contracts MUST pass through server `transaction_number` fields when present.
- `ai-native-contracts`: Document additive response/fact fields; closed tool catalog unchanged for allocation (server-only).

## Impact

- Backend: counter allocation helper; `CommitSaleSession`, `VoidSaleSession`, `ConfirmDailyClose`; SaleSession/ClosingSnapshot columns; Event Memory fact CHECKs; export columns; ADR-033 (Proposed) covering migration-only memory enrichment, historical idempotency compatibility, void identity, and first-allocation concurrency; migration `0018`.
- Mobile: subtle TRX on `sale_confirmed@1` / `daily_close_confirmed@1`; Memoria secondary TRX lines; no client sequence generation.
- Integrity: allocation inside the same DB transaction as the business mutation; post-0018 idempotent replay returns stored numbers; rollback leaves no committed reference; pre-0018 stored idempotency bodies are a compatibility exception only.
- Unchanged: onboarding change, cash-count numbering, Inicio/Hoy layout redesign, sale-corrections domain rules beyond additive references.
