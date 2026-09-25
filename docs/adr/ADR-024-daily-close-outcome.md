# ADR-024: Daily Close is the OutcomeRun daily_close_ready@1

- Status: Accepted
- Date: 2026-09-24

## Decision

Daily Close progress is one `operations.outcome_runs` row, `daily_close_ready` version `1`, owned by `business`. Persisted status is only `in_progress`, `ready`, or `completed`. Reason codes are only `awaiting_cash_count`, `ready_balanced`, `ready_cash_short`, `ready_cash_over`, and `closed_confirmed`. `not_ready` is an OutcomeEngine verdict for an unknown definition id. It is not a stored status, reason, or check value. `blocked`, `failed`, and `cancelled` are not stored.

The row is created on the first successful `sale.commit@1` for the open day and recomputed inside that same transaction, inside a new current CashCount, and inside `closing.confirm@1`. Reads do not create or update it. A missing row is repaired by the next new CashCount or by close, not by a read. Close inserts the ClosingSnapshot, closes the day, resolves the open Daily Close WorkItem, completes or inserts the OutcomeRun, then fills null `outcome_run_id` values, including the row just resolved. That link does not change WorkItem identity, status, resolution, or evidence and does not audit create or resolve.

`ready` requires an open day, at least one confirmed sale, and a current CashCount of `balanced`, `short`, or `over`. An open `cash_difference_review` does not remove `ready`. An insert that is already `ready` sets `ready_at` to that instant. A later entry into `ready` sets `ready_at` then. A later ready reason change keeps `ready_at`. There is no `ready` to `in_progress` path. A repair insert born `completed` sets `ready_at` equal to `completed_at`. Completion requires the day `closed`, exactly one ClosingSnapshot, `closing_snapshot_id` pointing at it, both timestamps, `closed_confirmed`, and no open Daily Close WorkItem.

Evidence is a projection of live cash and sale totals. It is not an input to expected cash, cash status, or close math. It freezes when the row is `completed`. The output artifact remains the ClosingSnapshot. WorkItems stay the merchant task list. Next Best Action copies `outcome_run_id` from the chosen WorkItem and stays a pure read. The model cannot supply `outcome_run_id`.

Audit is `outcome_run.created` and `outcome_run.status_changed`. Evidence-only and no-op writes are silent. There is no OutcomeRun outbox event and no new idempotency operation. Migration `0011_daily_close_outcome` does not backfill. The existing initializer covers open today only. Closed days and older open days are not given a retroactive row. The registry contains `daily_close_ready@1` only. `daily_sales_operations_ready@1` and `daily_close_ready.execute@1` stay unregistered.

ADR-015 through ADR-023 are unchanged.

## Consequences

Daily Close has one durable outcome beside the WorkItem the merchant sees. Short and over remain closable. A skipped initializer is repaired by the next count or by close, and historical closes stay on their ClosingSnapshot alone.
