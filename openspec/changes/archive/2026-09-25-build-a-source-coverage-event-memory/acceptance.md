# Acceptance notes

Manual acceptance PASS:

- first confirmed sale created one `sales` coverage row with `source_type=manual_capture`, `status=observed`, and `limitation_code=only_lumo_registered_operations`
- that sale created one `sale_confirmed` business event
- no `cash_count` coverage existed yet
- the OutcomeRun remained `in_progress` / `awaiting_cash_count`
- a pure Next Best Action read wrote nothing
- a short cash count of `10.00` against expected `12.00` created one `cash_count` coverage row and one `cash_count_recorded` event
- the sales coverage id and `created_at` stayed unchanged, and both coverage rows stayed `observed`
- the cash-count facts were exact, including `cash_status=short` and difference `-2.00`
- the OutcomeRun became `ready` / `ready_cash_short`, and `cash_difference_review` was open
- a pure read wrote nothing
- the short close left those same sales and cash-count coverage rows unchanged
- no `daily_close` coverage domain was created
- no `complete` or `declared_complete` status was created
- exactly one `daily_close_completed` business event was created
- that event's `source_type` is `manual_capture` and its proving entity is the ClosingSnapshot
- the OutcomeRun became `completed` / `closed_confirmed`
- one ClosingSnapshot exists
- open Daily Close WorkItems are 0
- the post-close Next Best Action is null
- the sales export stayed a pure read
- no completeness was inferred
- no new UI was added

Technical acceptance:

- both new tables use `ENABLE` and `FORCE` row level security, policy `tenant_isolation`, and `lumo_app` grants of `SELECT`, `INSERT`, and `DELETE` only
- `lumo_app` and `lumo_admin` remain `NOBYPASSRLS`
- `business_events_immutable` rejects `UPDATE`
- event facts use the exact JSON shapes, with money as two-decimal strings and `sale_count` as a JSON integer
- a failed parent rolls back coverage and events with the parent
- migration `0012` and the initializer do not backfill business events
- no coverage or event audit action and no new outbox type were added
- no memory or coverage tool, route, or Generative UI component was added
- pure reads write no coverage or business event
- another tenant cannot read these rows

Accepted non-functional deviation:

`alembic_version.version_num` was widened from `varchar(32)` to `varchar(64)` because revision id `0012_source_coverage_event_memory` is 34 characters. The widening is required for Alembic revision persistence. It does not change product-table semantics. Downgrade leaves the column at `varchar(64)`. This is not a product discrepancy.
