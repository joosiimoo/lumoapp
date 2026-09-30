## 1. Architecture and persistence

- [x] 1.1 Write ADR-031 documenting voided status, aggregate exclusion, open-day-only void, `sale_voided` memory, export `sale_status`, and persisted `sale_revision` for payment-action staleness
- [x] 1.2 Add Alembic revision: widen sale status check to `voided`, keep voided day membership, add `voided_at` / `voided_by_actor_id` / `void_reason` with completeness CHECK, add `sale_revision INTEGER NOT NULL DEFAULT 1` with `CHECK (sale_revision >= 1)` and backfill existing rows to `1`
- [x] 1.3 Extend domain `SaleSessionStatus`, SaleSession entity (`sale_revision: int`), SQLAlchemy model, and repository mappers for void metadata and `sale_revision` (new sessions initialize at `1`)
- [x] 1.4 Extend sale cleanup helpers for remove/void audit, outbox, idempotency, and `sale_voided` business events

## 2. Active sale item removal

- [x] 2.1 Add `SalesPort.remove_item` and persistence hard-delete under session `FOR UPDATE`
- [x] 2.2 Implement `RemoveSaleItem` workflow with status rules (`ready_to_charge`→`open` when empty), persist `sale_revision = sale_revision + 1` when pre-remove status was `ready_to_charge` (leave unchanged for `open`), audit, outbox `sale.item.removed`, idempotency
- [x] 2.3 Register tool `sale.remove_item@1` and UI action `sale.remove_item@1` with JWT binding for session+item
- [x] 2.4 Update `sale_item_added@1` and `sale_summary@1` composers to emit remove actions; after ready_to_charge remove recompose with fresh payment actions bound to the advanced persisted `sale_revision`
- [x] 2.5 Enforce payment-action JWT `sale_revision` claim against the locked session column so pre-remove cash/card/transfer tokens return `ui_action_stale` without commit (no in-memory/client-only revision)
- [x] 2.6 Flutter: secondary remove controls on item and summary cards via actions endpoint; no client totals

## 3. Confirmed sale void (Memoria-only entry)

- [x] 3.1 Implement `VoidSaleSession` workflow: `confirmed`+open-day mutates with reason; already `voided` is non-mutating read-back (no second event/audit/outbox); other statuses refuse; keep payment/items/day membership
- [x] 3.2 Same transaction on mutate only: audit `sale.void@1`, outbox `sale.voided`, append `sale_voided` event, call `maintain_open_daily_close`
- [x] 3.3 Register tool `sale.void@1` and UI actions `sale.void.request@1` / `sale.void.confirm@1` with server before/after impact; voided path returns read-back
- [x] 3.4 Ensure Inicio `sale_confirmed@1` does NOT emit Anular / `sale.void.request@1`; voided read-back may still render when returned by a void flow
- [x] 3.5 Memoria timeline: on `GET /api/v1/memory/events`, attach server-authored `sale.void.request@1` (+ `conversation_id`) only when session is `confirmed` on the current open OperationalDay; omit for voided, closed-day, and non-sale events
- [x] 3.6 Flutter Memoria: render Anular only when timeline `actions` include `sale.void.request@1`; reuse existing void confirmation (impact + reason → `sale.void.confirm@1`) with server `conversation_id`; refresh Memoria after void
- [x] 3.7 Hoy: no sale-level void actions and no individual sales list in this slice

## 4. Aggregates, close, export, memory

- [x] 4.1 Verify/adjust `summarize_day`, expected cash, Business Stream, and prepare paths remain confirmed-only (exclude `voided`)
- [x] 4.2 Extend daily sales export to include voided rows, add `sale_status` column, reconcile operational totals on confirmed only
- [x] 4.3 Update Hoy export caption for voided-with-status semantics
- [x] 4.4 Extend factual event memory checks/facts for `sale_voided`; Memoria timeline title "Venta anulada"
- [x] 4.5 Ensure source coverage is not deleted or rewritten on void; factual memory reads include void chronology

## 5. Policies, contracts, and registration

- [x] 5.1 Add/adjust PolicyEngine rules for remove and void: active-only remove; allow void for `confirmed` (mutate) and `voided` (read-back); deny other statuses; closed-day deny on mutate; non-empty reason on mutate only
- [x] 5.2 Register tools/actions in boot catalogs; keep LLM non-mutation
- [x] 5.3 Wire operator-surface refresh after remove/void mutations

## 6. Tests

- [x] 6.1 Unit/integration: remove one item, remove last item, remove from ready_to_charge, refuse remove on confirmed/voided; `sale_revision` starts at 1 and increments only on ready_to_charge remove; open remove leaves revision unchanged; pre-remove pay token stale; fresh pay token commits new total
- [x] 6.2 Integration: void keeps rows/payment; closed-day refuse; idempotent replay; already-voided read-back with no second event/audit/outbox; other-status refuse; concurrency lock
- [x] 6.3 Aggregates: gross/count/tenders/expected cash drop after void; Business Stream / Hoy refresh
- [x] 6.4 Cash count: counted preserved; difference/status recompute; ready_to_close / balanced invalidated; confirm token stale
- [x] 6.5 Memory: `sale_voided` facts + uniqueness with `sale_confirmed`; Memoria renders "Venta anulada"; remove writes no event
- [x] 6.6 Export: voided rows present with `sale_status`; confirmed-only reconciliation; Flutter caption
- [x] 6.7 Flutter widget/golden or pump tests for remove secondary controls and void confirmation gating (reason required)
- [x] 6.8 Migration/RLS tests for void constraints, `sale_revision` column/default/check, and tenant isolation
- [x] 6.9 Timeline API: open-day confirmed `sale_confirmed` exposes `sale.void.request@1`; already-voided and closed-day do not; token binds `sale_session_id`
- [x] 6.10 Inicio `sale_confirmed@1` after commit has no Anular / no `sale.void.request@1`
- [x] 6.11 Flutter Memoria: Anular only when server action present; posts existing void request token path; reload still allows void while eligible

## 7. Manual acceptance

- [x] 7.1 Remove item from active sale
- [x] 7.2 Remove item after totalize and pay with fresh action
- [x] 7.3 Void confirmed sale from Memoria and verify Hoy totals
- [x] 7.4 Verify void after cash count changes cash difference
- [x] 7.5 Verify Memoria shows Venta registrada (no Anular) and Venta anulada after void
- [x] 7.6 Verify export contains confirmed/voided sale_status
- [x] 7.7 Verify closed-day void is refused / Memoria does not expose Anular
- [x] 7.8 Verify Inicio confirmed card has no Anular
- [x] 7.9 Verify app restart still allows void from Memoria while eligible
