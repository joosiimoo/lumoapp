## Why

Lumo already confirms sales, opens the OperationalDay, records CashCount, keeps Daily Close WorkItems, projects a Next Best Action, and stores one ClosingSnapshot. None of those rows is the durable outcome for "this business day's Daily Close responsibility." PRD v0.11 §9.3–§9.4 and Build A §8.4 and §9.2 describe that contract; ADR-012 left the definition registry empty until a later change. Where v0.11 assumes Source Coverage, cost, or a general failure taxonomy, the implemented Build A close contract wins.

## What Changes

- Persist one `operations.outcome_runs` row for each business, OperationalDay, and `daily_close_ready` version `1` (Alembic `0011_daily_close_outcome`, down from `0010_work_items`).
- States are only `in_progress`, `ready`, and `completed`. Reason codes are `awaiting_cash_count`, `ready_balanced`, `ready_cash_short`, `ready_cash_over`, and `closed_confirmed`. `blocked`, `failed`, and `cancelled` are not stored.
- The first successful `sale.commit@1` that creates or attaches the day creates the row in that same transaction. Later sales reuse it. A new CashCount recomputes it. `closing.confirm@1` completes it and links the ClosingSnapshot.
- `ready` means the current Build A close gates are met, so `closing.request@1` may proceed. Short and over are ready while `cash_difference_review` stays open. `completed` means explicit confirmation succeeded. `OperationalDay.status` stays `open` or `closed`.
- Register OutcomeDefinition `daily_close_ready@1`. Do not register an execute tool. Do not add a merchant outcome route, a screen, or an OutcomeRun outbox event.
- Add nullable `work_items.outcome_run_id`. New Daily Close rows, and today's existing rows, point at that run. Closed historical days are not given a retroactive run.
- ADR-024 records the decision. ADR-015 through ADR-023 stay unchanged.

## Non-goals

- Build B, reopen, mixed payments, exception acceptance, a review queue, or tolerance.
- Source Coverage, Recorded Operations Completeness UI, Event Memory, Operational Context Memory, and WorkAbsorptionRecord.
- Cost instrumentation, human assignment, a workflow designer, a generic outcome engine, or a generic policy engine.
- `daily_sales_operations_ready@1`, `daily_close_ready.execute@1`, push, a new dashboard, inventory, replenishment, purchasing, suppliers, or forecasting.
- Redis, Kafka, a vector database, or another agent.
- Changing NBA title, reason, or actions, the close phrases, or the export.

## Capabilities

### New Capabilities

- `outcome-run-foundation`: Durable `daily_close_ready@1` row, identity, states, reason codes, evidence, RLS, and audit.
- `daily-close-outcome`: Contract, readiness and completion predicates, write hooks, WorkItem link, and the definition registry.

### Modified Capabilities

- `persistence`: Revision `0011_daily_close_outcome`, composite foreign keys, and cleanup order.
- `work-item-foundation`: Nullable `outcome_run_id` on new and current-day rows.
- `conversational-sale-session`: A confirming commit ensures the OutcomeRun in the same transaction.
- `daily-close-preparation`: A new cash count recomputes the OutcomeRun. `closing.prepare@1` stays a pure read.
- `daily-close-confirmation`: A successful close completes the OutcomeRun and links the snapshot.
- `next-best-action`: The projection adds `outcome_run_id` and still must not write.
- `ai-native-contracts`: Register `daily_close_ready@1` only. No execute tool.

## Impact

- Backend: one table, a nullable WorkItem column, and state updates inside `sale.commit@1`, a new CashCount insert, and `closing.confirm@1`. The existing deploy initializer also ensures today's open run and links that day's WorkItems. No new HTTP route and no Flutter change.
- Docs: ADR-024 only.
- Sale, payment, cash-count, close, NBA copy, and export behavior stay as they are, except these outcome writes in the same transactions.
