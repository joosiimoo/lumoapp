## ADDED Requirements

### Requirement: Daily Close WorkItem is a durable row
The system MUST persist a `WorkItem` in `operations.work_items` for Daily Close responsibility. The only types MUST be `cash_count_required`, `cash_difference_review`, and `close_confirmation_required`. The only statuses MUST be `open` and `resolved`. `priority` MUST be `critical` for `cash_count_required`, `high` for `cash_difference_review`, and `normal` for `close_confirmation_required`. `responsible_party` MUST be `business`. `source` MUST be `daily_close_rule`. `reason_code` MUST be `cash_count_missing` for a count item, `cash_short` or `cash_over` for a difference item, and `close_confirmation_required` for a close item. Each row MUST store `id`, `business_id`, `operational_day_id`, `evidence`, `created_at`, and `updated_at`. A resolved row MUST also store `resolved_at`, `resolution_actor_type`, and `resolution_code`. `resolved_by_actor_id` MUST be set only when `resolution_actor_type` is `business`, and MUST be NULL when `resolution_actor_type` is `system` or the row is open. `resolution_actor_type` MUST be NULL while open and MUST be `business` or `system` when resolved. The row MUST NOT store title, reason, or other model prose. It MUST NOT have `surfaced_at`, `expires_at`, `outcome_run_id`, an assignee, or a dismiss reason. `payment_required` MUST NOT be a type. States `assigned`, `in_progress`, `waiting`, `dismissed`, `expired`, and `failed` MUST NOT be stored.

#### Scenario: First confirmed sale creates one count item
- **WHEN** today's first confirmed sale is committed and no `CashCount` exists
- **THEN** exactly one open `cash_count_required` row MUST exist for that business and operational day with `priority=critical`, `responsible_party=business`, `reason_code=cash_count_missing`, and `source=daily_close_rule`

#### Scenario: Pending payment is not a WorkItem
- **WHEN** a `ready_to_charge` session exists and is not confirmed
- **THEN** no `payment_required` row MUST exist and that session MUST NOT create a Daily Close WorkItem

### Requirement: One open WorkItem per type
The database MUST allow at most one `open` row for each `(business_id, operational_day_id, type)`. A repeated sale or cash count that keeps the same desired type MUST update that open row's evidence when the facts changed and MUST NOT insert a second open row of that type. A no-op sync MUST NOT change `updated_at`. A Next Best Action read MUST NOT update the row.

#### Scenario: A second sale keeps the same count item
- **WHEN** a second confirmed sale is committed on an open day that still has no cash count
- **THEN** the same `cash_count_required` id MUST remain the only open row of that type

#### Scenario: A read does not refresh evidence
- **WHEN** the Next Best Action read runs after expected cash has changed and no new sale, count, or close has synced
- **THEN** the stored evidence MUST be unchanged by that read

### Requirement: A returned condition inserts a new generation
A resolved row MUST NOT return to `open`. Its `resolved_at`, `resolution_actor_type`, `resolved_by_actor_id`, and `resolution_code` MUST stay unchanged. When `cash_difference_review` is resolved because cash became `balanced` and a later current count is `short` or `over` while the day is still open, sync MUST insert a new open `cash_difference_review` row and MUST keep the resolved row.

#### Scenario: Recount after balance creates a new difference row
- **WHEN** a difference row was resolved because a recount was `balanced`, and a later recount on the same open day is `short`
- **THEN** the resolved row MUST stay resolved and exactly one new open `cash_difference_review` row MUST exist

#### Scenario: Short becomes over on the same open row
- **WHEN** an open `cash_difference_review` row has `reason_code=cash_short` and a later current count on that open day is `over`
- **THEN** that same id MUST remain open with `reason_code=cash_over` and no second open difference row MUST exist

### Requirement: WorkItems are derived from persisted close facts
Sync MUST build the desired open set only for the OperationalDay whose `business_date` is today in the business timezone. It MUST use confirmed-sale `sale_count`, the current `CashCount` (`superseded_by_id` NULL), and `cash_status` from `counted − expected`, where `expected` is that day's confirmed cash total. It MUST NOT consult an LLM. Older open days MUST NOT gain rows from this sync.

The desired open set MUST contain at most one type:
- empty when no such day exists, `sale_count` is less than 1, or the day is `closed`;
- `cash_count_required` only when the day is open, `sale_count` is at least 1, and no current count exists;
- `cash_difference_review` only when the current `cash_status` is `short` or `over`;
- `close_confirmation_required` only when the current `cash_status` is `balanced`.

`short` or `over` MUST NOT also leave `close_confirmation_required` open. Evidence MUST include `currency`, `expected_cash`, and `sale_count`. Counted types MUST also include `counted_cash`, signed `cash_difference`, `cash_status`, and `cash_count_id`. Amounts MUST be decimal strings. Sync MUST refresh evidence on the existing open row when those facts change and the type stays open.

#### Scenario: Sales without a count
- **WHEN** today has confirmed sales and no current `CashCount` and a confirming commit syncs
- **THEN** the only open WorkItem type for that day MUST be `cash_count_required`

#### Scenario: Short cash is one difference job
- **WHEN** a new current count is less than expected cash and the day is open
- **THEN** the only open row MUST be `cash_difference_review` with `reason_code=cash_short`, and `close_confirmation_required` MUST NOT be open

#### Scenario: Over cash is one difference job
- **WHEN** a new current count is greater than expected cash and the day is open
- **THEN** the only open row MUST be `cash_difference_review` with `reason_code=cash_over`

#### Scenario: Balanced cash is only close confirmation
- **WHEN** a new current count equals expected cash and the day is open
- **THEN** the only open WorkItem type MUST be `close_confirmation_required`

#### Scenario: No day creates nothing
- **WHEN** a sync runs and no OperationalDay exists for today's business date
- **THEN** sync MUST insert no WorkItem

#### Scenario: Open day with no confirmed sales creates nothing
- **WHEN** an open OperationalDay for today has `sale_count` 0 and sync runs
- **THEN** the desired open set MUST be empty

### Requirement: Resolution follows the fact in the same transaction
`cash_count_required` MUST resolve with `resolution_code=cash_count_recorded`, `resolution_actor_type=business`, and `resolved_by_actor_id` equal to the authenticated counter when that counter inserts a current count. `cash_difference_review` MUST resolve with `resolution_code=cash_balanced`, `resolution_actor_type=system`, and `resolved_by_actor_id` NULL when the day is still open and a later count or cash sale makes `cash_status` `balanced`. That same transaction MUST insert one open `close_confirmation_required` row. `closing.confirm@1` MUST resolve the one open Daily Close WorkItem for that day with `resolution_code=day_closed`, `resolution_actor_type=business`, and the confirmer's actor id. That close pass MUST NOT insert a WorkItem. A short or over close MUST NOT require a `close_confirmation_required` row to exist. When a balanced day's status becomes `short` or `over` before close, sync MUST resolve `close_confirmation_required` with `resolution_code=cash_unbalanced`, `resolution_actor_type=system`, and `resolved_by_actor_id` NULL, and MUST insert `cash_difference_review`. Product code MUST NOT delete resolved rows. There MUST be no merchant operation that resolves a row while its condition is still true. A read requester MUST NOT be stored as `resolved_by_actor_id`.

Successful `sale.commit@1` MUST run sync in the commit transaction after the day and payment exist. Idempotent replay and confirmed read-back MUST NOT run it again. A successful new `CashCount` insert MUST run sync in that transaction. The equal-amount cash-count read-back that writes no count MUST NOT run it. `closing.prepare@1`, `operational_day.summary@1`, daily sales export, `GET /api/v1/operational-days/current/next-best-action`, and `operational_day.next_best_action@1` MUST NOT run it.

#### Scenario: Counting resolves the count item as the merchant
- **WHEN** a current `CashCount` is inserted for an open day that had `cash_count_required`
- **THEN** that row MUST be `resolved` with `resolution_code=cash_count_recorded`, `resolution_actor_type=business`, and `resolved_by_actor_id` equal to the counting actor, in the same transaction as the count

#### Scenario: A balancing recount resolves the difference as the system
- **WHEN** an open difference row exists and the replacement current count equals expected cash
- **THEN** that difference row MUST be `resolved` with `resolution_code=cash_balanced`, `resolution_actor_type=system`, and `resolved_by_actor_id` NULL, and exactly one open `close_confirmation_required` row MUST exist

#### Scenario: Short close resolves only the difference
- **WHEN** the only open row is `cash_difference_review` and `closing.confirm@1` commits
- **THEN** that row MUST be `resolved` with `resolution_code=day_closed` and `resolution_actor_type=business`, and no `close_confirmation_required` row MUST be inserted

#### Scenario: Failed commit does not leave a WorkItem
- **WHEN** the commit transaction rolls back after preparing a WorkItem insert
- **THEN** that WorkItem MUST NOT remain

### Requirement: Closed days are not given new actionable work
The confirm transaction MUST resolve the open WorkItem for the day that is closing. A later read of that closed day MUST NOT insert or resolve a WorkItem. Resolved rows MUST stay stored. Sync MUST NOT insert a WorkItem for a closed day.

#### Scenario: Reading a closed day writes nothing
- **WHEN** the Next Best Action read runs for a business whose today is already `closed`
- **THEN** no open WorkItem MUST exist for that day, no new WorkItem MUST be inserted, and no audit row MUST be written by that read

### Requirement: WorkItem sync is tenant scoped
Every repository read or write of a WorkItem MUST use the authenticated `TenantContext`, except the deploy initializer which sets `app.current_business_id` to the business it is initializing before it writes. The row MUST be bound by a composite foreign key `(operational_day_id, business_id)` to `operations.operational_days (id, business_id)`. A session scoped to business B MUST NOT read or resolve business A's rows.

#### Scenario: Another tenant cannot read the row
- **WHEN** business A has an open WorkItem and the database session is scoped to business B
- **THEN** a select of `operations.work_items` MUST NOT return A's row

### Requirement: Lifecycle audit is create and resolve only
Inserting a WorkItem MUST write one audit action `work_item.created` in the same transaction. Resolving it MUST write one audit action `work_item.resolved` in the same transaction. The resolve payload MUST include the ids, type, status, reason code, evidence, `resolution_code`, and `resolution_actor_type`. It MUST include `resolved_by_actor_id` only when `resolution_actor_type` is `business`. It MUST NOT include model prose. An evidence-only update MUST NOT write audit. A Next Best Action read MUST NOT write audit. WorkItem lifecycle MUST NOT enqueue an outbox event.

#### Scenario: Business and system resolutions are distinguishable
- **WHEN** a count item is resolved by a cash count and a difference item is later resolved because a recount balances
- **THEN** the count resolution audit MUST record `resolution_actor_type=business` and that actor id, and the difference resolution audit MUST record `resolution_actor_type=system` and MUST NOT record an actor id

#### Scenario: A pure reread is quiet
- **WHEN** the Next Best Action read finds an open WorkItem
- **THEN** audit, outbox, idempotency, and WorkItem row counts for that business MUST be unchanged by that read

### Requirement: Deploy initializer covers open today
After migration `0010_work_items`, an application command MUST be runnable with `DATABASE_ADMIN_URL` before traffic. It MUST NOT be a public HTTP route, a merchant API, or a FastAPI request hook. It MUST NOT grant `BYPASSRLS`. It MUST disable RLS only on `identity.businesses` inside the transaction that lists business ids, then enable and force RLS again before that transaction commits. For each business it MUST set `app.current_business_id` and run the same desired-set function for that business's open OperationalDay dated today in the business timezone. It MUST skip closed days and older open days. It MUST NOT modify sales, cash counts, closing snapshots, outbox, or idempotency. An actual insert MUST audit `work_item.created` with `actor_id` NULL, `route_or_tool` `work_item.bootstrap`, and `origin` `rollout_bootstrap`. A second run MUST insert no duplicate open row and MUST write no audit when nothing is inserted. Alembic `0010` itself MUST insert no WorkItem.

#### Scenario: Pre-migration open today is initialized without a GET
- **WHEN** an open OperationalDay for today already has confirmed sales and no cash count, migration `0010` has been applied, and the initializer runs
- **THEN** one open `cash_count_required` row MUST exist, and a following Next Best Action GET MUST NOT insert or update any row

#### Scenario: A second initializer run is quiet
- **WHEN** the initializer runs again and the open row already matches the desired set
- **THEN** no second open row MUST exist and no additional `work_item.created` audit MUST be written
