# Acceptance notes

Manual acceptance PASS:

- first confirmed cash sale of 12.00 MXN created one OutcomeRun `in_progress` / `awaiting_cash_count` with `ready_at` null
- `cash_count_required` was open and its `outcome_run_id` pointed at that OutcomeRun
- Hoy behavior was unchanged
- balanced cash count of 12.00 moved the same OutcomeRun to `ready` / `ready_balanced` and set `ready_at`
- `close_confirmation_required` was open, the earlier `cash_count_required` was resolved, and both WorkItems referenced the same OutcomeRun
- no ClosingSnapshot existed yet
- explicit close moved the same OutcomeRun to `completed` / `closed_confirmed`, preserved `ready_at`, set `completed_at`, and linked the ClosingSnapshot
- the OperationalDay was closed, open WorkItems were 0, and the post-close Next Best Action was null
- a later confirmed cash sale of 12.00 with a cash count of 10.00 left `cash_difference_review` open and the OutcomeRun `ready` / `ready_cash_short`
- `pending_count` was 1, no `close_confirmation_required` was open, and close remained available
- the Next Best Action returned that same `outcome_run_id`
- pure reads wrote nothing
- export remained unchanged

An open `cash_difference_review` does not block OutcomeRun readiness. That coexistence is expected.

Non-blocking UX note:

- A raw UTC timestamp remains in the Cierre confirmado card. This is an existing UX issue and is not a blocker.

Evidence limitation:

The final retained database contains the short-path state only. The completed happy-path OutcomeRun was accepted in the UI and the database before the controlled reset used to run the short-path acceptance. Later-sale ready-to-ready behavior, skipped-initializer repair, and rollback atomicity were verified through implementation and tests rather than the final retained live row. This is an evidence-retention limitation, not a product failure.
