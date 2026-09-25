## Context

Daily Close already works. `sale.commit@1` confirms a sale only with one recorded `Payment` and opens today's `OperationalDay`. `closing.submit_cash_count@1` appends a current `CashCount`. `cash_status` is `not_counted`, `balanced`, `short`, or `over` from `counted − expected`. `not_counted` cannot close. `balanced`, `short`, and `over` can, after an explicit token (ADR-018). `closing.prepare@1` is a pure read. `closing.reopen@1` is unregistered. An open or `ready_to_charge` session does not block close and is not on the day until commit.

WorkItems are transition-maintained in `operations.work_items`. Next Best Action is a pure read whose `outcome_type` is the constant `daily_close_ready` (ADR-023). `OutcomeEngine` is a port with an empty registry that fail-closes (ADR-012). There is no `operations.outcome_runs` row.

`OperationalDay.status` is only `open` or `closed`. That status is not the outcome. This slice adds the outcome without a workflow schema, a second close screen, or a generic engine.

Code lives in the existing modular monolith:

- pure rules in `backend/app/domain/operations/daily_close_outcome.py` (no FastAPI or SQLAlchemy);
- the write helper in `backend/app/application/workflows/sync_daily_close_outcome.py`;
- the table and repository next to the other `operations` types;
- registration in the existing `OutcomeEngine` port at bootstrap.

No `workflow` schema, no `outcome_definitions` table, and no `completion_evidence` table.

## Goals / Non-Goals

**Goals:**

- One durable OutcomeRun for `daily_close_ready@1` per business and OperationalDay.
- Deterministic status, reason, and evidence from persisted sales, the current CashCount, and the ClosingSnapshot.
- The same close gates that exist today, including short and over remaining closable.
- Completion only when `closing.confirm@1` commits, with the snapshot linked.
- WorkItems for that day point at the run. Historical closed days are left alone.

**Non-Goals:**

- The proposal's non-goals. In particular: no `failed`, `blocked`, or `cancelled` state; no Source Coverage; no cost columns; no merchant outcome API; no new UI; no OutcomeRun outbox event; no execute tool; no `daily_sales_operations_ready@1`.

## Decisions

### 1. OutcomeRun fields

`operations.outcome_runs`:

- `id` UUID primary key, UUIDv7
- `business_id` UUID NOT NULL
- `operational_day_id` UUID NOT NULL
- `outcome_type` VARCHAR NOT NULL, CHECK `daily_close_ready`
- `outcome_version` INTEGER NOT NULL, CHECK `1`
- `status` VARCHAR NOT NULL
- `owner_type` VARCHAR NOT NULL, CHECK `business`
- `reason_code` VARCHAR NOT NULL
- `evidence` JSONB NOT NULL, object
- `created_at`, `updated_at` timestamptz NOT NULL
- `ready_at` timestamptz NULL
- `completed_at` timestamptz NULL
- `closing_snapshot_id` UUID NULL

No `failed_at`, `owner_id`, cost summary, source-coverage id, or prose column. `reason_code` is NOT NULL because every stored state has one reason. A nullable reason that is re-derived on read was rejected: the row would not answer "why" after the facts move.

### 2. State set

Exactly `in_progress`, `ready`, and `completed`.

| status | meaning |
|---|---|
| `in_progress` | The day is open, at least one confirmed sale exists, and there is no current CashCount. The next work is known. |
| `ready` | The day is open, a current count exists, and `cash_status` is `balanced`, `short`, or `over`. The merchant may confirm. |
| `completed` | `closing.confirm@1` succeeded. The day is `closed` and one ClosingSnapshot is linked. |

`blocked` is excluded. Missing cash is normal actionable work, not an unrecoverable blocker. Build A has no other persisted blocker: `payment_required` is not a WorkItem, and `ready_to_charge` does not attach to the day.

`failed` is excluded. A technical failure rolls the parent transaction back. It is not a durable outcome state.

`cancelled` is excluded. Nothing in Build A cancels a day or an outcome. Reopen stays unregistered.

`not_ready` is an `OutcomeEngine.evaluate` verdict for an unknown definition id. It is not an `OutcomeRun.status`, not a `reason_code`, and not a value of the `operations.outcome_runs` status check.

PRD v0.11 §9.8 and Build A §8.4 list a wider lifecycle. Those codes are not imported.

### 3. Reason codes

Persisted with the status. No merchant prose.

| status | reason_code |
|---|---|
| `in_progress` | `awaiting_cash_count` |
| `ready` | `ready_balanced`, `ready_cash_short`, or `ready_cash_over` |
| `completed` | `closed_confirmed` |

`ready_balanced` matches `cash_status=balanced`, `ready_cash_short` matches `short`, and `ready_cash_over` matches `over`. `closed_confirmed` does not repeat the cash sign; the frozen evidence and the snapshot do.

These are outcome-level reasons. They are not copies of WorkItem reason codes. An open `cash_difference_review` (`cash_short` / `cash_over`) can exist while the outcome reason is `ready_cash_short` or `ready_cash_over`.

### 4. Identity

Exactly one row for `(business_id, operational_day_id, outcome_type, outcome_version)`, unique constraint `uq_outcome_runs_identity`.

Also `UNIQUE (id, business_id)` and `UNIQUE (id, business_id, operational_day_id)` so composite foreign keys can target them. A second insert for the same day and version MUST fail. Application code looks up before insert and treats the unique violation as "reuse the existing row" only if a concurrent insert won the race inside the same day lock. The day is already locked `FOR UPDATE` by the parent mutation, so the application lookup is sufficient for the single writer.

### 5. Trigger

Create the row only when Daily Close responsibility begins: the first successful `sale.commit@1` that creates or attaches today's OperationalDay, in that same transaction.

Do not create a row for a `ready_to_charge` session, a day with no confirmed sale, or a business date with no OperationalDay. Do not create on read. A later confirmed sale on that day reuses the row.

If the deploy initializer was skipped, the next successful new CashCount or successful close for that open today also ensures the row, at the status the facts have then. That is repair, not a second trigger.

### 6. Owner

`owner_type` is `business` on every row. The merchant business owns confirmation. Lumo owns tracking and preparation through the deterministic hooks. There is no `owner_id`, user, team, or internal-operator assignment.

### 7. Ready predicate

`status=ready` when all of these are true:

- `OperationalDay.status` is `open`;
- confirmed `sale_count` is at least 1;
- a current CashCount exists (`superseded_by_id` NULL);
- derived `cash_status` is `balanced`, `short`, or `over`.

It does not require a zero difference, an accepted exception, Source Coverage, an empty review queue, `payment_required`, or the absence of `cash_difference_review`.

`not_counted` is not ready.

### 8. Short and over stay ready

A short or over day has one open `cash_difference_review` and no `close_confirmation_required` (ADR-023). The outcome is still `ready`. Readiness means the merchant may explicitly confirm. It does not mean the difference is zero.

An open WorkItem does not imply "not ready."

### 9. Completed predicate

`status=completed` only when `closing.confirm@1` has committed in that transaction:

- `OperationalDay.status` is `closed`;
- exactly one ClosingSnapshot exists for that day;
- `closing_snapshot_id` is that snapshot;
- `completed_at` is the close instant;
- `ready_at` is not null;
- `reason_code` is `closed_confirmed`;
- no Daily Close WorkItem for that day is `open`.

A replay or a different-key read-back of an already closed day MUST NOT complete the row again.

### 10. Evidence

`evidence` is a transition-maintained projection, refreshed in the same transaction as the facts. It is not an input to expected cash, `cash_status`, or close. Those stay computed from sales, payments, and the current CashCount. The ClosingSnapshot remains the immutable artifact.

Keys, decimal strings, business currency:

- always: `currency`, `sale_count`, `gross_sales_total`, `expected_cash`, `cash_status`;
- when a current count exists: also `counted_cash`, signed `cash_difference`, `current_cash_count_id`.

Do not store `operational_day_id` or `closing_snapshot_id` inside `evidence`; those are columns. Do not store sale lines, payment rows, or snapshot totals beyond this set. Do not store model prose.

On `completed`, evidence is the close-time values and is not rewritten. Build A has no later writer for a closed day.

A derive-on-read model was rejected because completion must keep the figures that were confirmed even as a projection, and acceptance requires evidence to update when a later sale changes the cash position. The projection is allowed to be refreshed only by the hooks below.

### 11. ClosingSnapshot

The output artifact of `daily_close_ready@1` is the existing ClosingSnapshot. `closing_snapshot_id` is set only in the completing transaction. The outcome row MUST NOT copy the snapshot body. `operations.closing_snapshots` gains no outcome column. This slice adds `UNIQUE (id, business_id, operational_day_id)` on snapshots, named `uq_closing_snapshots_id_business_day`, without dropping the existing unique keys, so the outcome can reference that triple.

### 12. WorkItem link

Add nullable `operations.work_items.outcome_run_id`.

Composite foreign key `fk_work_items_outcome_run` from `(outcome_run_id, business_id, operational_day_id)` to `outcome_runs (id, business_id, operational_day_id)`. A row cannot point at another tenant's run or another day's run.

New WorkItem inserts for a day that has a run set `outcome_run_id`. Existing ids, status, resolution, and evidence history are not rewritten except for this null column on the current day.

### 13. Backfill scope

Migration `0011` inserts nothing and updates no WorkItem.

The deploy initializer, for today's open OperationalDay only:

- ensures the OutcomeRun from that day's facts;
- sets `outcome_run_id` on every `work_items` row for that `operational_day_id` whose column is still null, open or resolved.

Closed days, and open days whose `business_date` is not today, get no OutcomeRun. Their WorkItems stay null. Linking every historical resolved row would require inventing runs for closed days, which this slice does not do.

### 14. State updates

Status is persisted and updated only inside the parent mutation. It is not derived on read and the LLM cannot set it.

Hooks:

- successful `sale.commit@1`, after the day and payment exist;
- successful insert of a new current CashCount;
- successful `closing.confirm@1`, after the snapshot exists and the day is `closed`.

Not hooks: idempotent replay, confirmed read-back, equal-amount cash-count read-back, `closing.prepare@1`, `operational_day.summary@1`, daily sales export, the Next Best Action GET, and `operational_day.next_best_action@1`.

`ready_at` rules:

- an insert whose status is `in_progress` leaves `ready_at` null;
- an insert whose status is `ready` sets `ready_at` to that insertion instant, including the today-only initializer when a current CashCount already exists and a cash-count repair that inserts the missing row already `ready`;
- a later transition into `ready` sets `ready_at` to that transition instant;
- `ready_at` stays set if a later sale only changes the ready reason;
- a repair insert that is born `completed` sets `ready_at` equal to `completed_at`.

### 15. Transaction order

`sale.commit@1`, after the existing day attach, payment, sale audit, optional `operational_day.opened` audit and outbox, and `sale.confirmed` / `payment.recorded` outbox, and before idempotency complete:

1. Sync the OutcomeRun from the locked day's sales and current count.
2. Sync WorkItems, stamping `outcome_run_id` on insert.
3. Set `outcome_run_id` on any of that day's WorkItems that are still null.

`closing.submit_cash_count@1`, after the count insert, cash-count audit, and `cash_count.recorded` outbox, and before idempotency complete: the same three steps. The equal-amount path returns before any of them.

`closing.confirm@1`, after the day lock, token verification, and idempotency reserve, in this order:

1. Insert the ClosingSnapshot.
2. Set `OperationalDay.status` to `closed`.
3. Resolve the open Daily Close WorkItem with `day_closed`, inserting none.
4. Complete the existing OutcomeRun, or insert it already `completed` if it is missing: `closed_confirmed`, `completed_at`, `closing_snapshot_id`, frozen evidence, and `ready_at` equal to `completed_at` on that repair insert.
5. Set `outcome_run_id` on any WorkItems for that operational day whose `outcome_run_id` is still null, including the WorkItem just resolved.
6. Write the existing `closing.confirm@1` audit.
7. Enqueue the existing `closing.confirmed` outbox event.
8. Complete parent idempotency.
9. Commit.

Step 5 is a link-only update. It does not write `work_item.created` or `work_item.resolved`, and it does not change the WorkItem id, status, resolution fields, or evidence. The resolve in step 3 still writes one `work_item.resolved`. Step 5 does not write a second one. A failure before commit leaves no snapshot, no closed day, no completed run, and no outcome audit.

Clarify, stale confirmation, and the already-closed read-back return before these writes.

### 16. Audit

Two actions, only when something material happened:

- `outcome_run.created` on insert. Payload: `outcome_run_id`, `operational_day_id`, `outcome_type`, `outcome_version`, `status`, `reason_code`, `owner_type`, `evidence`, and `closing_snapshot_id` when the insert is already completed.
- `outcome_run.status_changed` when an existing row changes `status` or `reason_code`. Payload includes `previous_status`, `status`, `previous_reason_code`, `reason_code`, and `evidence`. A ready reason change with the same status still uses this action. Completion includes `closing_snapshot_id`.

An evidence-only refresh bumps `updated_at` and writes no audit. An unchanged status, reason, and evidence writes nothing and does not bump `updated_at`.

Separate `outcome_run.ready` and `outcome_run.completed` actions were rejected. Ready can change reason without leaving `ready`, and one status action covers enter-ready and complete without a third taxonomy.

`route_or_tool` is the parent tool (`sale.commit@1`, `closing.submit_cash_count@1`, or `closing.confirm@1`). The initializer uses `outcome_run.bootstrap`, a null actor, and `origin=rollout_bootstrap` on the created payload.

### 17. Outbox

No OutcomeRun outbox event. No consumer exists. `closing.confirmed` remains the operational completion event. `operational_day.opened`, `sale.confirmed`, `payment.recorded`, and `cash_count.recorded` stay as they are.

### 18. Idempotency

No new `operation_type`. Creation and update ride the parent `lumo.message.commit_sale`, `lumo.message.record_cash_count`, or `lumo.message.confirm_close` record. Replay returns the stored body before any outcome write, so it cannot duplicate the run, the audit, the snapshot, or a WorkItem.

### 19. RLS

`business_id` is required. `ENABLE` and `FORCE` ROW LEVEL SECURITY. Policy `tenant_isolation` uses `business_id::text = current_setting('app.current_business_id', true)`. Grant `lumo_app` `SELECT`, `INSERT`, `UPDATE`, and `DELETE`. `lumo_admin` stays `NOBYPASSRLS`; this migration does not grant `BYPASSRLS`.

Foreign keys:

- `(operational_day_id, business_id)` → `operations.operational_days (id, business_id)`
- `(closing_snapshot_id, business_id, operational_day_id)` → `operations.closing_snapshots (id, business_id, operational_day_id)`
- WorkItem link as in decision 12

Index `ix_outcome_runs_business_id` on `business_id`.

### 20. Migration

Revision `0011_daily_close_outcome`, `down_revision` `0010_work_items`.

Upgrade creates `operations.outcome_runs`, the checks and unique keys above, the snapshot unique key `uq_closing_snapshots_id_business_day`, RLS, grants, and nullable `work_items.outcome_run_id` with `fk_work_items_outcome_run`. It does not create schema `workflow` or `memory`, and it does not create definition, evidence, cost, source-coverage, event-memory, or next-best-action tables.

Downgrade aborts when any `outcome_runs` row exists. Otherwise it drops `fk_work_items_outcome_run` and `outcome_run_id`, drops `operations.outcome_runs`, and drops `uq_closing_snapshots_id_business_day`. WorkItem rows may remain.

### 21. Existing open today

Extend the current deploy command (`DATABASE_ADMIN_URL`, not an HTTP route). It still lists businesses by disabling RLS only on `identity.businesses` for that listing transaction. For each business it sets the tenant and, in that transaction, runs outcome ensure and WorkItem sync for the open OperationalDay dated today, then fills null `outcome_run_id` on that day's WorkItems. If that day already has a current CashCount, the inserted row is `ready` and `ready_at` is the insertion instant. If it has no count, the inserted row is `in_progress` and `ready_at` is null. It skips closed days and older open days. It does not grant `BYPASSRLS` and does not write sales, cash counts, snapshots, outbox, or idempotency.

A second run inserts no second OutcomeRun and writes no audit when the row already matches.

### 22. Historical closed days

Do not create completed OutcomeRuns for days that are already closed when `0011` is applied. Pilot evidence of those closes remains the ClosingSnapshot. Their WorkItems stay unlinked.

### 23. Registry

A code registry on the existing `OutcomeEngine` port, not a plugin loader and not a table. Bootstrap registers one definition:

- id `daily_close_ready@1`
- version `1`
- owner `business`
- trigger `first_confirmed_sale`
- output artifact `ClosingSnapshot`
- gate evaluator: the pure predicate in the domain module
- states `in_progress`, `ready`, `completed`

`evaluate` ignores model text. An unknown id, including `daily_sales_operations_ready@1`, returns the evaluation verdict `not_ready` and writes nothing. That verdict is not persisted. The registered id returns `in_progress`, `ready`, or `completed` from the supplied confirmed state and writes nothing. Persisted transitions happen only in the hooks. There is no `daily_close_ready.execute@1` tool.

Contract text, stored as definition data rather than merchant copy:

- scope: one business and one OperationalDay;
- inputs: that OperationalDay, its confirmed sales and payments, and its current CashCount;
- ready gates: decision 7;
- human confirmation: the merchant, through the existing `closing.confirm@1` token;
- limitation: only operations registered in Lumo are represented.

### 24. Public API

No merchant route. In particular, do not add `GET /api/v1/operational-days/current/outcome`. Tests and later slices read the table through the repository. The Next Best Action projection is the only response field that carries `outcome_run_id`.

### 25. Next Best Action

When the projection includes an action, add `outcome_run_id` from the chosen WorkItem, or null when that column is null. Do not change `title`, `reason`, `expected_result`, `actions`, rank, `risk`, `reversible`, or `pending_count`. The GET and the tool remain pure reads: they MUST NOT insert or update an OutcomeRun.

### 26. UI

No new screen, component, or Flutter change. Hoy, preparation, confirmation, and export stay as they are. The client reads NBA fields it already renders; an extra `outcome_run_id` key is not displayed.

### 27. Failed, blocked, and cancelled

All three are excluded. See decision 2. A rolled-back commit, count, or close leaves the previous OutcomeRun unchanged, or absent if this mutation would have created it.

### 28. Ready does not fall back to in_progress

A current CashCount is not deleted. After the first count, another confirmed sale recomputes evidence. If the new expected cash leaves `cash_status` `balanced`, `short`, or `over`, the outcome stays `ready`. The reason changes when the sign changes, and stays when it does not. `ready_at` stays. There is no `ready` → `in_progress` path in this model. A card or transfer sale that does not change `cash_status` updates `sale_count` and `gross_sales_total` in evidence and does not audit.

### 29. Completion integrity

A completed row MUST satisfy decision 9. Tests MUST reject a completed row with no snapshot, a snapshot id that is not that day's snapshot, a null `completed_at`, an open Daily Close WorkItem, or a day that is still `open`.

### 30. ADR-024

Implementation adds `docs/adr/ADR-024-daily-close-outcome.md` with this decision: `daily_close_ready@1`, the three states, the reason codes, the first-sale trigger, the ready gates, short/over readiness, ClosingSnapshot as the artifact, OperationalDay left as `open|closed`, the WorkItem link, the three hooks, RLS, migration `0011` plus the today-only initializer, no generic workflow engine, no outcome outbox event, and no new UI. Do not edit ADR-015 through ADR-023.

## Risks / Trade-offs

- [Skipped initializer] → Today's open day has no run until the next sale, new count, or close. Close repair inserts the row already `completed` instead of inventing `in_progress`.
- [Evidence duplicates live totals] → Close math still reads sales and the count. Evidence is refreshed only in the three hooks, and completion freezes it. A forgotten hook would show a stale projection; it cannot close on stale numbers because confirm recomputes under the day lock.
- [Historical WorkItems stay null] → Accepted. Linking them would invent OutcomeRuns for closed days.
- [Ready reason changes without a status change] → `outcome_run.status_changed` still fires, with `previous_status` equal to `status`, so the audit is not limited to the three status edges.
- [NBA gains a field] → Copy and actions are unchanged. Flutter already treats the payload as a map and renders the existing keys.

## Migration Plan

1. Apply Alembic `0011_daily_close_outcome`. It creates the empty table and the nullable column.
2. Run the existing deploy initializer once before traffic so open today has a run and linked WorkItems.
3. Rolling app deploy. New commits, counts, and closes maintain the row. Reads do not.
4. Rollback of the app without downgrading the database is safe: old code ignores the new table. Downgrade of `0011` is allowed only while `outcome_runs` is empty.

## Open Questions

None. Decisions 1–30 are closed for implementation.
