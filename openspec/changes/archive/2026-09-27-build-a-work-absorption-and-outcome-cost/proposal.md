## Why

Daily Close already produces a durable `daily_close_ready@1` OutcomeRun, WorkItems, CashCount, ClosingSnapshot, source coverage, and factual events. None of those rows answers how the outcome was produced or what it cost. PRD v0.11 RF-083, RF-084, RF-085, CAO-007, and E26 require Build A to classify execution mode, persist `WorkAbsorptionRecord`, and record cost per OutcomeRun. This slice is internal instrumentation of the existing Daily Close path. It does not change merchant close behavior.

## What Changes

- Persist `WorkAbsorptionRecord` in `operations.work_absorption_records` for `daily_close_ready@1` only. The economic unit is OutcomeRun, not user, conversation, token, message, screen, or session.
- Persist execution mode as the closed PRD §9.12 enum. RF-083 Spanish names map 1:1 onto those values. Mode is how a task was executed. It is not WorkItem status, OutcomeRun status, actor, risk, or completion percentage.
- Use a versioned static Daily Close baseline for `human_steps_before`, `human_steps_after`, and `estimated_minutes_saved`. Copy those integers onto each record. Do not let the LLM invent them.
- Persist cost on a related `operations.outcome_costs` row, not on `operations.outcome_runs`. ADR-024 already forbids a cost summary on OutcomeRun. ADR-028 (Proposed) records the related-record decision, the baseline, and measured vs estimated vs unavailable semantics.
- Instrument only inside existing OutcomeRun write transactions: successful `sale.commit@1`, a new current CashCount, successful `closing.confirm@1`, and the today-only initializer. Reads, `closing.prepare@1`, Business Stream, NBA, export, and Flutter redraws write nothing.
- Add Alembic `0013_work_absorption_outcome_cost`, down from `0012_source_coverage_event_memory`. Do not backfill closed days.
- No merchant API, no admin dashboard, no Flutter surface, and no Business Stream metrics.

## Capabilities

### New Capabilities

- `work-absorption`: Closed execution-mode enum, Daily Close task taxonomy, versioned baseline, `WorkAbsorptionRecord` persistence, evidence ids, idempotency, and freeze on OutcomeRun completion.
- `outcome-cost`: Related `OutcomeCost` row, USD money contract, measured vs estimated vs unavailable components, retry count, intervention seconds, and partial-total semantics.

### Modified Capabilities

- `outcome-run-foundation`: OutcomeRun still stores no cost summary. Completion finalizes related absorption and cost rows. Historical completed facts do not silently change.
- `daily-close-outcome`: Existing Daily Close writes also emit absorption and cost. Close gates, statuses, reason codes, evidence keys, and merchant behavior stay unchanged.
- `daily-close-preparation`: `closing.prepare@1` remains a pure read and MUST NOT insert or update absorption or cost rows.
- `persistence`: Revision `0013_work_absorption_outcome_cost`, RLS, uniqueness, composite FKs, immutability after completion, and cleanup order.

## Impact

- Backend: two `operations` tables, domain contracts, and writes inside `sync_daily_close_outcome` / close. Head becomes `0013`. Tests and repository queries are the acceptance surface.
- Docs: ADR-028 Proposed until implementation and manual acceptance.
- Mobile: no change. Inicio, Hoy, Memoria, sale/close cards, and Business Stream stay as they are.
- No new HTTP route. No new tool. No new Generative UI contract.

## Non-goals

- Merchant-facing ROI, cost, absorption, automation score, or minutes-saved UI.
- Internal analytics dashboard, Business Stream / Hoy / Memoria metrics, public cost endpoint.
- Pricing, billing, margin, revenue attribution, gross-margin optimization, recommendations, AutomationCandidate.
- LLM-estimated savings, inferred labor rates, financial savings claims to the merchant.
- Dynamic workflow redesign, baseline-management UI, stage-gate UI, anti-POS survey UI.
- Build B: `partially_completed`, reopen, mixed payments, exception acceptance, reversible/under-policy execution in this flow, internal ReviewTask.
- External cloud billing, latency-derived infra cost, historical backfill of closed days.
- `daily_sales_operations_ready@1`, a generic outcome-execution tool, or a new event store.
