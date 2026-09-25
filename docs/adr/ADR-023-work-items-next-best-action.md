# ADR-023: WorkItems are transition-maintained; Next Best Action is a pure read

- Status: Accepted
- Date: 2026-09-24

## Decision

Daily Close responsibility is a durable `operations.work_items` row. The row is maintained only inside the write that changed the underlying facts: a successful `sale.commit@1`, a successful insert of a new current `CashCount`, and a successful `closing.confirm@1`. Next Best Action reads are pure projections. `GET /api/v1/operational-days/current/next-best-action` and `operational_day.next_best_action@1` never reconcile and never persist, including no `surfaced_at`.

Identity is one open row per business, day, and type. A returned condition inserts a new generation. Only `open` and `resolved` exist. Short or over has one active `cash_difference_review`, not a simultaneous close item. If more than one open row is ever present, rank is `cash_count_required`, then `cash_difference_review`, then `close_confirmation_required`.

Direct resolutions record `resolution_actor_type=business` and the authenticated actor: a cash count clears `cash_count_required` with `cash_count_recorded`, and close clears the open difference or close item with `day_closed`. Derived recomputation records `system` and a null actor id: `cash_balanced` when a difference becomes balanced, and `cash_unbalanced` when a balanced close item becomes short or over. The open job's `responsible_party` is `business`. Scope is today's Daily Close. The row belongs to `OperationalDay` through a composite foreign key.

`outcome_run_id` waits for a later slice. This slice does not insert an OutcomeRun, a `next_best_actions` table, or a WorkItem outbox event. Migration `0010_work_items` does not backfill. A deploy command initializes open today only, with bootstrap audit (`actor_id` null, `route_or_tool=work_item.bootstrap`, `origin=rollout_bootstrap`) and no merchant endpoint. Audit is create and resolve only. Hoy shows one action and a count. Inicio renders `next_best_action` version 1. The model cannot set priority or amounts.

ADR-015 through ADR-022 are unchanged.

## Consequences

The merchant sees one pending Daily Close step without a second source of truth and without a read that mutates. Short and over stay closable after the existing confirmation. A skipped initializer leaves open today without WorkItems until the next successful commit, new cash count, or close.
