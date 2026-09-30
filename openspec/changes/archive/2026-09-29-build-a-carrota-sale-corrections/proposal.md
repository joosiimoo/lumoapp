## Why

Carrota MVP pilots need safe, auditable corrections: merchants must drop a mistaken line from an active sale before charging, and void a wrong confirmed sale without erasing history. Today the status machine stops at `confirmed`, item remove is forbidden, aggregates and export assume every confirmed sale is live, and RF-086 corrections never feed Event Memory — so a bad sale either sticks forever or would require unsafe deletes.

## What Changes

- Allow removing one `SaleItem` from an active `SaleSession` in `open` or `ready_to_charge`. Backend locks the session, deletes that line, and recomposes remaining items and session total. Removing the last item leaves an empty active sale (no confirmed history). Removing from `ready_to_charge` with items remaining keeps `ready_to_charge`; emptying the session returns it to `open`.
- Allow voiding a `confirmed` sale while its `OperationalDay` is still `open`. Transition `confirmed` → `voided` without deleting the session, items, or `Payment`. Persist void actor, timestamp, and reason. Closed-day voids are refused; no reopen.
- Keep voided sales out of live operational aggregates: gross sales, sale count, payment-method totals, expected cash, Daily Close preparation, and Business Stream / Hoy figures. Live cash-count difference and `cash_status` recompute from preserved counted cash; `ready_to_close` / Caja cuadrada MUST invalidate when the difference is no longer balanced.
- Append factual Event Memory `sale_voided` (Memoria: "Venta anulada") without mutating `sale_confirmed`. RF-086.
- **BREAKING** for export consumers: daily sales export includes voided sales with an explicit `sale_status` column; operational reconciliation totals use only `confirmed` rows.
- Smallest secondary Flutter controls: remove on active-sale cards / ready_to_charge summary (unchanged). Confirmed-sale void entry is **Memoria-only**: a "Venta registrada" timeline entry may expose server-authored Anular (`sale.void.request@1`) when the sale is still `confirmed` on the current open OperationalDay; explicit confirmation with server before/after impact then `sale.void.confirm@1`. Inicio `sale_confirmed@1` and Hoy MUST NOT expose void. Conversation stays primary for sales; Memoria is the correction entry for void.
- New ADR for the status expansion, aggregate predicates, memory event, closed-day refusal, and export contract.

## Non-goals

- Refunds, partial refunds, payment-method change, item-by-item edit of a confirmed sale.
- Post-close corrections, day reopen, versioned ClosingSnapshot rewrite.
- Inventory, stock reverse, RF-009, Build B.
- Soft-delete of `SaleItem` history for active removes; separate void table as primary truth; physically deleting confirmed sales or payments.
- Mixed payment, discounts, tips, acquirer voids, admin-only hidden tooling without merchant UX for this pilot carve-out.

## Capabilities

### New Capabilities

- `sale-corrections`: Active-sale item removal and confirmed-sale void domain rules, void metadata on `SaleSession`, open-day gate, live aggregate exclusion, cash-count/close consequence, void confirmation impact payload, and correction Event Memory write.

### Modified Capabilities

- `sales-session-foundation`: Status set adds `voided`; day-membership check keeps voided day linkage; remove-item persistence; persisted `sale_revision` for payment-action staleness; active unique index still excludes `confirmed` and `voided`.
- `conversational-sale-session`: Remove-item and void intents; empty active sale; no confirmed history from uncommitted remove.
- `conversational-sale-runtime`: Register `sale.remove_item@1` and `sale.void@1` (plus UI-bound confirm path); workflows own locks/idempotency/outbox/audit.
- `sale-payment`: Void keeps the recorded `Payment`; payment is not deleted or re-recorded.
- `sale-item-added-ui`: Secondary remove control on the active item card.
- `sale-summary-ui`: Secondary remove per line on `ready_to_charge` summary; recomposed total after remove.
- `sale-confirmed-ui`: Confirmed card stays informational (no Anular); voided read-back presentation when a void flow returns it.
- `generative-ui-actions`: New action ids for remove and void confirm; Memoria may emit `sale.void.request@1` using the same token infrastructure.
- `ai-native-contracts`: Register tools/UI/actions and correction policies.
- `persistence`: Alembic status/`void_*` columns and `sale_revision`; cleanup helpers; RLS unchanged.
- `mobile-shell`: Renderer/action wiring for remove and void.
- `daily-sales-export`: Include voided rows; add `sale_status`; reconcile operational totals on confirmed only.
- `sales-export-ui`: Caption/copy that voided lines may appear with status.
- `factual-event-memory`: Allow and write `sale_voided`.
- `factual-memory-read`: Expose void facts in day/recent reads.
- `factual-memory-tool`: Closed taxonomy accepts `sale_voided`.
- `memoria-timeline`: Render "Venta anulada"; server-authored Anular on eligible "Venta registrada" entries; no client eligibility inference.
- `cash-count-foundation`: After void, counted cash preserved; expected/difference/status live.
- `daily-close-preparation`: Preparation figures exclude voided; fingerprint may stale.
- `daily-close-confirmation`: Stale confirmation when void changes prep fingerprint.
- `daily-close-outcome`: Re-sync WorkItems / OutcomeRun after void on open day.
- `business-stream`: Hoy / Inicio aggregates exclude voided (via `summarize_day`).
- `source-coverage`: Void MUST NOT delete or reverse `sales` coverage already observed for the day.

## Impact

- Backend: `SaleSessionStatus.voided`, void columns, persisted `sale_revision`, `RemoveSaleItem` / `VoidSaleSession` workflows, tools, policies, `summarize_day` / export filters, memory writer, `maintain_open_daily_close` after void, ADR-031.
- Mobile: remove secondary controls on active sale; Memoria Anular + void confirmation; Memoria voided card; export caption. No Inicio/Hoy void entry.
- Integrity: row locks, idempotency keys, audit/outbox in the same write transaction as today; Flutter still does no money math.
- Docs authority: PRD v0.11 §21.7–21.8 and RF-086; Build A MVP reserved `voided` state is deliberately exposed for this Carrota pilot carve-out.
