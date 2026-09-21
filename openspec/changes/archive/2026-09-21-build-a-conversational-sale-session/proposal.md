## Why

The archived conversational-sale foundation can add one catalog line, but Lumo still does not own a sale across turns. PRD §7.3 requires a merchant to build a detailed sale over several interactions and receive a structured proposal; this slice is that workflow without payment: accumulate items, expose session state, and totalize to a deterministic ready-to-charge point.

## What Changes

- Keep one `SaleSession` per `(business_id, actor_id, conversation_id)` and allow multiple independent `SaleItem`s on the same open session.
- Extend `SaleSession.status` from `open` only to `open` → `ready_to_charge`. This is not PRD `confirmed` and not Architecture `sale.commit` (those include payment).
- Register `sale.totalize@1` and application workflow `TotalizeSaleSession`. Explicit utterances `totalizar`, `total`, and `el total` totalize; they MUST NOT record payment.
- Seed two additional Carrota products so a realistic multi-item sale can be exercised: Tomate (kg) and Galleta A (unit). Do not seed Papa.
- After unique catalog resolve, a count product (`sale_unit` `unit` or `package`) MAY complete without an explicit mass unit (`2 galletas A`). Kilogram products still MUST clarify a missing unit (`500 tomate` → ask unit).
- Keep `sale_item_added@1` at version 1. Flutter MUST display the already-specified `session_item_count` and `session_total`.
- Register Generative UI `sale_summary@1` after a committed totalize. Flutter renders server values and MUST NOT sum lines.
- Reject adding an item after `ready_to_charge` with a resolution-oriented response. Do not silently reopen or create a second session for that conversation.
- Preserve conversation_id scope, FORCE RLS, one application write transaction, audit, outbox, and message-level idempotency.
- Serialize add-item and totalize on an existing `SaleSession` with a PostgreSQL row lock (`SELECT ... FOR UPDATE`) before checking mutable status. Repeat `totalizar` on `ready_to_charge` is a stable read-back, not a second transition.

**BREAKING** relative to the active baseline: `SaleSession.status` is no longer `open`-only; `ToolRegistry` and `GenerativeUIRegistry` gain `sale.totalize@1` and `sale_summary@1`; the unique index from `0002_catalog_sales` keeps `COALESCE(conversation_id, '')` and only widens its predicate to `open` and `ready_to_charge`.

## Non-goals

- Payment capture, cash/card/transfer, mixed payments, `sale.commit@1`, confirmed `Sale` finalization.
- Daily Close, OperationalDay, CashCount, WorkItems, NextBestAction, outcomes.
- Inventory, stock decrement, purchasing, suppliers, receiving, replenishment, forecasting.
- Manual price override, discounts, unknown/free-concept persistence, catalog CRUD UI.
- Edit, remove, or correct a line; cancel sale; reopen `ready_to_charge`.
- History screens, CSV/XLSX export, voice, camera, vendor LLM, advanced Memory, Redis, Kafka, vector database.
- Multi-product interpretation in one utterance; redesign of Inicio.

## Capabilities

### New Capabilities

- `conversational-sale-session`: Lumo owns an in-progress sale: accumulate items, know the session total, totalize to `ready_to_charge`, and reject invalid transitions.
- `sale-summary-ui`: Versioned `sale_summary@1` contract, backend composition after committed totalize, and Flutter rendering on Inicio.

### Modified Capabilities

- `sales-session-foundation`: Status machine `open` | `ready_to_charge`; items only while `open`; row-lock serialization; totals remain the sum of persisted items (no duplicated mutable session total).
- `conversational-sale-runtime`: Totalize intent and tool; count-product completion after resolve; add-item blocked once ready to charge; `ready_to_charge` totalize is a non-mutating read-back; scripted interpreter remains local/test.
- `catalog-foundation`: Idempotent seed adds Tomate and Galleta A; Papa stays unknown.
- `sale-item-added-ui`: Render existing `session_item_count` and `session_total`; do not bump the contract version.
- `ai-native-contracts`: Register `sale.totalize@1` and `sale_summary@1`. `sale.commit@1` and payment/confirmed-sale cards stay unregistered.
- `persistence`: Allow `ready_to_charge`; widen the existing unique-index predicate only; extend sale integrity cleanup to totalize audit/outbox/idempotency.
- `mobile-shell`: Inicio stream renders `sale_summary@1` and accumulated add-item totals from server strings.

## Impact

- Backend: `SaleSessionStatus`, Alembic 0003, seed, `sale.totalize@1`, `TotalizeSaleSession`, add-item session-state gate, scripted totalize/count-product paths, `sale_summary@1`.
- Mobile: `GenerativeUIRenderer` maps `sale_summary@1`; add-item card shows session count/total; no client math.
- Integrity: a transitioning totalize is one application-owned write transaction (status + audit + outbox + idempotency) after locking the session row. Add-item and totalize serialize on that row. Message `Idempotency-Key` scopes `lumo.message.totalize_sale` separately from `lumo.message.add_sale_item`. A different-key `totalizar` on `ready_to_charge` is a read-back and MUST NOT persist a second transition, outbox, or idempotency row.
- Tests: the twelve original acceptance scenarios plus different-key no-op totalize and concurrent add-item vs totalize.
