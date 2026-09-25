## Why

Build A already records sales, cash counts, and an explicit Daily Close, but the merchant still has to know commands such as "preparar el cierre", "contar efectivo", and "cerrar el día". PRD Build A §2 and §7.8 require Minimum Operator Behavior: Lumo keeps what is pending and names the single next action. This slice does that for the Daily Close facts that already exist.

## What Changes

- Persist a minimal `WorkItem` in `operations.work_items` (Alembic `0010_work_items`, `down_revision` `0009_catalog_price_override`). The model derives items only from today's open `OperationalDay`, its confirmed sales, and its current `CashCount`.
- v1 types are `cash_count_required`, `cash_difference_review`, and `close_confirmation_required`. `payment_required` is excluded: a confirmed sale already has one recorded `Payment`, and `ready_to_charge` is not attached to the day and does not block close (sale-payment spec; daily-close-confirmation spec; ADR-018).
- A short or over count stays closable after explicit confirmation. The difference item is review work, not a new block and not an exception acceptance (ADR-018).
- Next Best Action is a deterministic projection over active WorkItems. It is not a stored entity and not an LLM decision.
- Hoy shows that one action, a pending count, and the existing sales export. "¿qué sigue?", "¿qué falta?", and "¿qué tengo pendiente?" use the same read. Cash counting stays conversational. Close reuses `closing.request@1`.
- ADR-023 records why the WorkItem is durable and why the action is derived.

## Non-goals

- Generic task manager, user-created tasks, dismiss, assignment, roles, or a review queue.
- OutcomeRun, Source Coverage, Event Memory, WorkAbsorptionRecord, and the Build B exception engine.
- Inventory, replenishment, purchasing, suppliers, forecasting, CRM, reminders, or push.
- A recommendation or insight ranker, configurable priorities, or a workflow designer.
- Reopening, mixed payments, tolerance, manager approval, or cash correction.
- Redis, Kafka, a vector database, or another agent.
- Changing sale, payment, cash-count, close-confirmation, or export behavior except to create or resolve these WorkItems in the same transactions.

## Capabilities

### New Capabilities

- `work-item-foundation`: Durable Daily Close WorkItems, identity, predicates, and transition-driven sync.
- `next-best-action`: Deterministic single-action projection, read API, and read tool.
- `next-best-action-ui`: Hoy block, Inicio card, and Flutter rendering of server copy.

### Modified Capabilities

- `persistence`: Table, RLS, composite foreign key, head revision `0010_work_items`, and cleanup order.
- `conversational-sale-session`: A confirming commit may create `cash_count_required` in the same transaction.
- `daily-close-preparation`: A new cash count syncs WorkItems. `closing.prepare@1` stays a pure read.
- `daily-close-confirmation`: A successful close resolves open Daily Close WorkItems without changing short/over rules.
- `ai-native-contracts`: Register `operational_day.next_best_action@1` and `next_best_action@1`.
- `conversational-sale-runtime`: Route the closed pending-work phrase set to that read tool.
- `operational-day-summary-ui`: Hoy may show the next-action block and must not become a close screen.
- `daily-close-preparation-ui`: Preparation stays on Inicio. Hoy is no longer required to be an empty placeholder.
- `sales-export-ui`: The export panel stays; the next-action block sits above it.
- `mobile-shell`: The renderer registers `next_best_action` version `1`.

## Impact

- Backend: domain rules, repository, and sync inside commit, a new cash count, and confirm. The Next Best Action GET and tool are pure reads. A deploy-time initializer covers open days that already exist today. No `next_best_actions` table, no WorkItem outbox event, no new UI action id.
- Mobile: Hoy and the Inicio renderer. Flutter does not calculate money or priority.
- Docs: ADR-023 only. ADR-015 through ADR-022 stay unchanged.
- Existing close phrases, `closing.request@1`, `closing.confirm@1`, and the Hoy export downloads keep their current contracts.
