## MODIFIED Requirements

### Requirement: Daily Close WorkItem is a durable row
The system MUST persist a `WorkItem` in `operations.work_items` for Daily Close responsibility. The only types MUST be `cash_count_required`, `cash_difference_review`, and `close_confirmation_required`. The only statuses MUST be `open` and `resolved`. `priority` MUST be `critical` for `cash_count_required`, `high` for `cash_difference_review`, and `normal` for `close_confirmation_required`. `responsible_party` MUST be `business`. `source` MUST be `daily_close_rule`. `reason_code` MUST be `cash_count_missing` for a count item, `cash_short` or `cash_over` for a difference item, and `close_confirmation_required` for a close item. Each row MUST store `id`, `business_id`, `operational_day_id`, `evidence`, `created_at`, and `updated_at`. `outcome_run_id` MUST be nullable. A resolved row MUST also store `resolved_at`, `resolution_actor_type`, and `resolution_code`. `resolved_by_actor_id` MUST be set only when `resolution_actor_type` is `business`, and MUST be NULL when `resolution_actor_type` is `system` or the row is open. `resolution_actor_type` MUST be NULL while open and MUST be `business` or `system` when resolved. The row MUST NOT store title, reason, or other model prose. It MUST NOT have `surfaced_at`, `expires_at`, an assignee, or a dismiss reason. `payment_required` MUST NOT be a type. States `assigned`, `in_progress`, `waiting`, `dismissed`, `expired`, and `failed` MUST NOT be stored.

#### Scenario: First confirmed sale creates one count item
- **WHEN** today's first confirmed sale is committed and no `CashCount` exists
- **THEN** exactly one open `cash_count_required` row MUST exist for that business and operational day with `priority=critical`, `responsible_party=business`, `reason_code=cash_count_missing`, and `source=daily_close_rule`

#### Scenario: Pending payment is not a WorkItem
- **WHEN** a `ready_to_charge` session exists and is not confirmed
- **THEN** no `payment_required` row MUST exist and that session MUST NOT create a Daily Close WorkItem

### Requirement: Deploy initializer covers open today
After migration `0011_daily_close_outcome`, an application command MUST be runnable with `DATABASE_ADMIN_URL` before traffic. It MUST NOT be a public HTTP route, a merchant API, or a FastAPI request hook. It MUST NOT grant `BYPASSRLS`. It MUST disable RLS only on `identity.businesses` inside the transaction that lists business ids, then enable and force RLS again before that transaction commits. For each business it MUST set `app.current_business_id` and run the same desired-set function for that business's open OperationalDay dated today in the business timezone. It MUST also ensure that day's OutcomeRun and set `outcome_run_id` on that day's WorkItems, as `daily-close-outcome` requires. It MUST skip closed days and older open days. It MUST NOT modify sales, cash counts, closing snapshots, outbox, or idempotency. An actual WorkItem insert MUST audit `work_item.created` with `actor_id` NULL, `route_or_tool` `work_item.bootstrap`, and `origin` `rollout_bootstrap`. A second run MUST insert no duplicate open row and MUST write no WorkItem audit when nothing is inserted. Alembic `0010` and `0011` themselves MUST insert no WorkItem and no OutcomeRun.

#### Scenario: Pre-migration open today is initialized without a GET
- **WHEN** an open OperationalDay for today already has confirmed sales and no cash count, migration `0011` has been applied, and the initializer runs
- **THEN** one open `cash_count_required` row MUST exist, its `outcome_run_id` MUST reference that day's OutcomeRun, and a following Next Best Action GET MUST NOT insert or update any row

#### Scenario: A second initializer run is quiet
- **WHEN** the initializer runs again and the open row already matches the desired set
- **THEN** no second open row MUST exist and no additional `work_item.created` audit MUST be written

## ADDED Requirements

### Requirement: WorkItems reference the day's OutcomeRun
When an OutcomeRun exists for the operational day, a WorkItem inserted for that day MUST set `outcome_run_id` to that run. The same transaction MUST set `outcome_run_id` on any of that day's existing WorkItems whose column is still null, including a WorkItem resolved earlier in that same `closing.confirm@1` transaction before the missing OutcomeRun was inserted. Setting the column MUST NOT change the WorkItem id, status, resolution fields, or evidence, and MUST NOT write `work_item.created` or `work_item.resolved`. A WorkItem on a day with no OutcomeRun MUST keep `outcome_run_id` null. The foreign key MUST bind `(outcome_run_id, business_id, operational_day_id)` to `operations.outcome_runs (id, business_id, operational_day_id)`.

#### Scenario: The count item points at the new outcome
- **WHEN** today's first confirmed sale creates `cash_count_required` and the OutcomeRun
- **THEN** that WorkItem's `outcome_run_id` MUST equal the OutcomeRun id for that day

#### Scenario: Close repair links the already resolved row
- **WHEN** close resolves a WorkItem whose `outcome_run_id` is null and then inserts the missing completed OutcomeRun in that same transaction
- **THEN** that resolved WorkItem's `outcome_run_id` MUST equal the new OutcomeRun id, and the link MUST NOT write `work_item.created` or `work_item.resolved`

#### Scenario: A historical closed day stays unlinked
- **WHEN** a closed day has resolved WorkItems and no OutcomeRun
- **THEN** those WorkItems MUST keep `outcome_run_id` null
