## 1. OutcomeRun domain

- [x] 1.1 Add `backend/app/domain/operations/daily_close_outcome.py` with states `in_progress`, `ready`, and `completed`, the five reason codes, owner `business`, and the pure predicate. No FastAPI, SQLAlchemy, or merchant prose. Do not add `blocked`, `failed`, or `cancelled`
- [x] 1.2 Map open day plus no current count to `in_progress` / `awaiting_cash_count`, and `balanced`, `short`, and `over` to `ready` with `ready_balanced`, `ready_cash_short`, and `ready_cash_over`. A closed day with a snapshot maps to `completed` / `closed_confirmed`. An open difference WorkItem MUST NOT change that result

## 2. Migration and persistence

- [x] 2.1 Add Alembic `0011_daily_close_outcome` down from `0010_work_items`: `operations.outcome_runs`, checks, `uq_outcome_runs_identity`, composite foreign keys, `uq_closing_snapshots_id_business_day`, nullable `work_items.outcome_run_id`, FORCE RLS, `tenant_isolation`, and `lumo_app` grants. No backfill and no `workflow` or `memory` schema
- [x] 2.2 Downgrade aborts when any outcome row exists; otherwise it drops the column, the table, and `uq_closing_snapshots_id_business_day`. Reset helpers delete `work_items` before `outcome_runs` before `closing_snapshots`
- [x] 2.3 Add tenant-scoped load, insert, evidence update, and status update methods. Product code never deletes. An unchanged status, reason, and evidence MUST NOT write

## 3. OutcomeDefinition registry

- [x] 3.1 Register only `daily_close_ready@1` on the existing `OutcomeEngine` at bootstrap, with owner `business`, trigger `first_confirmed_sale`, output artifact `ClosingSnapshot`, and the pure predicate. `evaluate` MUST ignore model text and MUST NOT write. An unknown id returns the verdict `not_ready`, which MUST NOT be an `OutcomeRun.status` or a status CHECK value
- [x] 3.2 Leave `daily_sales_operations_ready@1` and `daily_close_ready.execute@1` unregistered. Do not add a merchant outcome route

## 4. Sale-commit creation

- [x] 4.1 On successful `sale.commit@1`, after the day and payment exist and before idempotency completes, ensure one OutcomeRun and then sync WorkItems. The first sale with no count inserts `in_progress` / `awaiting_cash_count`. A later sale reuses the row
- [x] 4.2 Do not create a row for `ready_to_charge`, a missing day, a refused closed-day commit, replay, or confirmed read-back. No new idempotency operation

## 5. Recomputation on sale and cash count

- [x] 5.1 A new current CashCount, after its audit and `cash_count.recorded` outbox and before idempotency completes, recomputes the OutcomeRun. Balanced, short, and over become `ready`. A transition into `ready` sets `ready_at` to that instant. A direct insert that is already `ready` sets `ready_at` to the insertion instant. Do not clear `ready_at`
- [x] 5.2 A later sale that keeps a current count stays `ready`. A reason change writes `outcome_run.status_changed`. An evidence-only change writes no audit. Equal-amount count read-back and `closing.prepare@1` MUST NOT recompute

## 6. Completion on close

- [x] 6.1 On successful `closing.confirm@1`, insert the snapshot, close the day, resolve the open WorkItem with `day_closed`, complete the OutcomeRun or insert it already `completed` with `ready_at` equal to `completed_at`, then set `outcome_run_id` on that day's WorkItems that are still null, including the row just resolved. The link MUST NOT write `work_item.created` or `work_item.resolved` and MUST NOT change id, status, resolution, or evidence
- [x] 6.2 Replay, already-closed read-back, clarify, stale confirmation, and `not_counted` MUST NOT complete the row or write a second snapshot. Do not enqueue an OutcomeRun outbox event. `closing.confirmed` stays the only close event

## 7. WorkItem linking

- [x] 7.1 Stamp `outcome_run_id` on WorkItem insert when the day's run exists, and fill nulls on that day's existing rows in the same transaction. Do not rewrite WorkItem ids, status, resolution, or evidence, and do not audit the link as create or resolve
- [x] 7.2 Add `outcome_run_id` to the Next Best Action projection from the chosen row. Do not change title, reason, expected result, or actions. The GET and `operational_day.next_best_action@1` MUST NOT write an OutcomeRun

## 8. Initializer

- [x] 8.1 Extend the existing `DATABASE_ADMIN_URL` command so open today gets an OutcomeRun and linked WorkItems. No count inserts `in_progress` with `ready_at` null. A current CashCount inserts `ready` with `ready_at` set to the insertion instant. Audit a real insert as `outcome_run.bootstrap` with a null actor and `origin=rollout_bootstrap`. Skip closed days and older open days. Do not grant `BYPASSRLS` or add an HTTP route
- [x] 8.2 A second run MUST NOT insert a duplicate or write audit when the row already matches. Alembic `0011` itself MUST insert nothing

## 9. Audit and integrity tests

- [x] 9.1 Cover first sale, second sale, no count with `ready_at` null, balanced, short, over, a direct `ready` insert with `ready_at` set, open difference while ready, later cash sale staying ready, close linking the snapshot, replay, no day, `ready_to_charge`, and tenant isolation
- [x] 9.2 Cover WorkItem linkage, no open Daily Close WorkItem after completion, registry contents, no execute tool, reads and export writing nothing, unchanged NBA copy, and no workflow, memory, source-coverage, or cost tables
- [x] 9.3 A failed commit, count, or close rolls the OutcomeRun back with the parent transaction
- [x] 9.4 Cover a skipped initializer whose open WorkItem has `outcome_run_id` null: close inserts one `completed` OutcomeRun, the resolved WorkItem points at it, and the link writes no `work_item.created` and no second `work_item.resolved`. An unknown definition id returns `not_ready` and leaves `outcome_runs` without that status

## 10. ADR-024

- [x] 10.1 Add `docs/adr/ADR-024-daily-close-outcome.md` with the closed decisions in design.md. Do not edit ADR-015 through ADR-023
