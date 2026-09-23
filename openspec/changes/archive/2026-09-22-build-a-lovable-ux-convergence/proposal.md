## Why

Build A already confirms a sale and a daily close, but the merchant still types the obvious next step while the card repeats the assistant sentence. PRD §10.5, SRS RF-A-112/113, and Architecture §5.4 and §6 already require opaque, revalidated generative-UI actions and `POST /api/v1/lumo/actions`. `GenerativeUIAction` exists, and every composer emits `actions: []`. This slice makes the existing card the primary artifact and lets a tap reach the same workflows as the approved phrases. It adds no business capability.

## What Changes

- Emit a closed action set on the existing version-1 contracts, only when server state allows it. `sale_summary@1` offers cash, card, and transfer. A counted open `daily_close_preparation@1` offers request-close, then confirm-close only after the server issues a token. Confirmed sale, confirmed close, a not-counted day, and the day summary emit no mutating action.
- Add the single architecture endpoint `POST /api/v1/lumo/actions`. It does not call the interpreter, does not synthesize a phrase, and does not accept amounts or domain ids in the body. Each payment action's signed token is bound to the `sale_session_id` that emitted it. A fresh tap of an old button does not confirm a later sale and does not append that earlier sale's confirmed card when a newer active sale exists. An exact completed idempotency replay may still return its stored body. The route dispatches into existing `sale.commit@1`, `request_close`, and `closing.confirm@1`.
- Keep typed phrases on `POST /api/v1/lumo/messages`. Typing and tapping share one workflow, one audit action, and one outbox event.
- Hide duplicate assistant prose when a recognized card already shows every fact in that sentence. Keep `fallback_text` in the contract for fallback and accessibility.
- Restyle those cards with the current Lumo design system, using only server fields. `sale_confirmed@1` renders every server line. Preparation stays cash-focused. Not-counted stays conversational.
- Stay on contract version 1. The `actions` envelope field already exists and remains optional. Propose ADR-019. Do not edit ADR-015 through ADR-018.

## Capabilities

### New Capabilities

- `generative-ui-actions`: closed action catalog, `POST /api/v1/lumo/actions`, context tokens, tap idempotency, and typed/tapped equivalence.

### Modified Capabilities

- `ai-native-contracts`: version-1 cards may carry the closed optional actions; confirm token is also the confirm action's `context_token`.
- `mobile-shell`: action dispatcher, card-first stream, loading and retry, no client business rules.
- `conversational-sale-runtime`: action dispatch bypasses interpretation and reuses the existing handlers.
- `conversational-sale-session`: a payment tap is the same `sale.commit@1` transition as the approved phrase.
- `sale-summary-ui`: payment actions and the charge-ready presentation.
- `sale-confirmed-ui`: all server line items, method label, no payment actions.
- `daily-close-preparation-ui`: two-stage close actions, difference presentation, conversational not-counted.
- `daily-close-confirmed-ui`: confirmed presentation, no reopen or close actions.
- `operational-day-summary-ui`: same card language, still no actions and no Hoy redesign.

## Impact

- One new route. `POST /api/v1/lumo/messages` stays. No migration, table, tool, domain state, or infrastructure.
- Payment and confirm taps use the existing idempotency operation types. Request-close remains a non-persisting read.
- Flutter Inicio only. Hoy, Memoria, and Negocio stay placeholders.

## Non-goals

- No database migration, new table, domain entity, workflow state, or tool that changes business behavior.
- No inventory, stock, replenishment, low-stock warning, or product recommendation.
- No card authorization, settlement, mixed or combined payment, payment amount input, or undo/edit/delete of a sale.
- No close note, review-sales flow, tolerance, approval, exception queue, reopen, or export.
- No historical comparison, hourly analytics, top products, charts, "Lumo observa", Hoy redesign, WorkItems, Next Best Action, or OutcomeRuns.
- No inline cash-count input and no `gross_sales_total` on the preparation card.
- No second payment or close mutation path, and no per-button endpoint.
