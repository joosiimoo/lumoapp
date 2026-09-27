## Why

Inicio still shows operational responsibility only after the merchant asks. Confirmed sales, cash counts, WorkItems, Next Best Action, the Daily Close outcome, and source coverage already exist, but opening Inicio does not say what Lumo is handling, what needs attention, or whether today's close is progressing, waiting, ready, or completed. PRD v0.11 §8.18 and §12.6 require Build A Inicio to be that operator surface.

## What Changes

- Add one server-owned, read-only projection of today's operational responsibility, shown on Inicio above the existing conversation.
- Use a closed operator state: no active day, organizing, cash count required, cash difference, ready to close, or closed. At most one primary action.
- Rank that action from the existing Daily Close WorkItem order and OutcomeRun. Do not add a recommendation engine, and do not let Flutter derive priority, totals, cash difference, coverage, or outcome state.
- Add `GET /api/v1/business-stream/today`. Do not stretch `GET /api/v1/operational-days/current/next-best-action` and do not assemble this surface from several client calls.
- Reuse the conversational cash count and the existing close request. Reading Inicio must not create an OperationalDay or any other row.

Trace: RF-076, RF-081, RF-089, RF-090, RF-094, RF-095, and the Build A proactivity items that current state can already express (cash difference, day ready to close, contextual cash count, source-coverage limitation, next close action). Missing payment is not a current Daily Close WorkItem, so this slice does not invent one.

## Capabilities

### New Capabilities

- `business-stream`: Today's typed operator projection, its read API, the single primary action, the coverage sentence, and the Inicio surface.

### Modified Capabilities

- `daily-close-outcome`: The new read may consume today's OutcomeRun. It must not add an outcome route or write a run.
- `source-coverage`: The new read may return the existing recorded-operations declaration. It must not add a coverage route, a score, or a write.
- `mobile-shell`: Inicio loads the operator surface when the tab opens and after a successful sale, cash count, or close turn. The greeting, composer, and conversation cards stay.

## Impact

- Backend: one application query and one GET. Tenant from the session. No Alembic revision. Head stays `0012_source_coverage_event_memory`.
- Mobile: Inicio panel and API client. No new Generative UI component and no new action id.
- Docs: ADR-027, status Accepted, for a dedicated projection instead of client assembly.
- Hoy's next-step block, Memoria, and the sale/close cards stay as they are.
- Reads must not write audit, outbox, idempotency, coverage, events, WorkItems, or OutcomeRuns.

## Non-goals

- RF-083 execution mode, RF-084 WorkAbsorptionRecord, RF-085 cost per outcome, RF-075 stage gate, and RF-096 pilot perception measurement.
- Push, background jobs, scheduled reminders, email, or WhatsApp.
- Comparisons with yesterday, trends, insights, recommendations, forecasting, replenishment, inferred memory, or Resolution Memory.
- Build B: mixed payments, payment corrections, cancellation, reopen, exception acceptance, late data, advanced permissions, or offline sync.
- A cash-count form, a coverage dashboard, a second Memoria, or an LLM-rendered first state.
