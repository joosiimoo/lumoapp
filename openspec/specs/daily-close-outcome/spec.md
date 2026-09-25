# daily-close-outcome Specification

## Purpose

`daily_close_ready@1` for one business and one OperationalDay. The first confirmed sale creates the row. A current cash count makes it ready, including short and over. Close completes it against the ClosingSnapshot.

## Requirements
### Requirement: daily_close_ready@1 is the Daily Close contract
The system MUST register OutcomeDefinition `daily_close_ready@1` and no other outcome definition. The definition MUST record version `1`, owner `business`, trigger `first_confirmed_sale`, output artifact `ClosingSnapshot`, the pure gate evaluator, and states `in_progress`, `ready`, and `completed`. Scope MUST be one business and one OperationalDay. Inputs MUST be that OperationalDay, its confirmed sales and payments, and its current CashCount. The limitation MUST be that only operations registered in Lumo are represented. `daily_sales_operations_ready@1` MUST remain unregistered. `ToolRegistry` MUST NOT register `daily_close_ready.execute@1` or any generic outcome-execution tool. Evaluating the definition MUST NOT insert or update an OutcomeRun. The LLM MUST NOT choose the status.

#### Scenario: The registry contains only this definition
- **WHEN** the outcome definition registry is queried after boot
- **THEN** it MUST contain `daily_close_ready@1` and MUST NOT contain `daily_sales_operations_ready@1`

#### Scenario: No execute tool exists
- **WHEN** a caller asks `ToolRegistry` for `daily_close_ready.execute@1`
- **THEN** the registry MUST report the tool as unregistered

#### Scenario: Evaluation does not persist
- **WHEN** a caller evaluates `daily_close_ready@1` with confirmed state and a model claim that the outcome is complete
- **THEN** the engine MUST ignore the model claim, MUST return the deterministic status, and MUST NOT write an OutcomeRun

### Requirement: The first confirmed sale creates the outcome
A successful `sale.commit@1` that creates or attaches today's OperationalDay MUST ensure the OutcomeRun in that same transaction, after the day and payment exist and before idempotency completes. The first confirmed sale MUST insert exactly one row. A later confirmed sale on that day MUST reuse it. A `ready_to_charge` session MUST NOT create an OutcomeRun. A business date with no OperationalDay MUST NOT have an OutcomeRun. No read MUST create one. There MUST be no separate outcome idempotency operation. Replay of the parent commit MUST NOT insert a second row.

#### Scenario: First confirmed sale
- **WHEN** today's first confirmed sale is committed and no CashCount exists
- **THEN** exactly one OutcomeRun MUST exist with `status=in_progress` and `reason_code=awaiting_cash_count`

#### Scenario: Second sale reuses the row
- **WHEN** a second confirmed sale is committed for that same open day
- **THEN** the same OutcomeRun id MUST remain the only row for that day and version

#### Scenario: Ready to charge creates nothing
- **WHEN** the only session today is `ready_to_charge` and no confirmed sale exists
- **THEN** no OperationalDay MUST be required for an outcome and no OutcomeRun MUST exist

#### Scenario: No day creates nothing
- **WHEN** no OperationalDay exists for today's business date
- **THEN** no OutcomeRun MUST exist

### Requirement: Ready means the merchant may confirm
For an open day with `sale_count` at least 1, a current CashCount, and `cash_status` `balanced`, `short`, or `over`, the OutcomeRun MUST be `ready` with `reason_code` `ready_balanced`, `ready_cash_short`, or `ready_cash_over`. An insert whose status is `in_progress` MUST leave `ready_at` null. An insert whose status is `ready` MUST set `ready_at` to that insertion instant, including the today-only initializer when a current CashCount already exists. A later transition into `ready` MUST set `ready_at` to that transition instant. `ready_at` MUST stay set while the row remains `ready`. Readiness MUST NOT require a zero cash difference, an accepted exception, Source Coverage, an empty difference WorkItem, or `payment_required`. No current CashCount MUST leave the row `in_progress`. `OperationalDay.status` MUST remain `open` until `closing.confirm@1`.

#### Scenario: No cash count stays in progress
- **WHEN** confirmed sales exist and no current CashCount exists
- **THEN** the OutcomeRun MUST be `in_progress` with `reason_code=awaiting_cash_count` and `ready_at` MUST be null

#### Scenario: A direct ready insert sets ready_at
- **WHEN** an OutcomeRun is inserted with `status=ready`, including by the today-only initializer for an open day that already has a current CashCount and no OutcomeRun
- **THEN** `ready_at` MUST be that insertion instant and MUST NOT be null

#### Scenario: Balanced count is ready
- **WHEN** a new current count equals expected cash
- **THEN** the OutcomeRun MUST be `ready` with `reason_code=ready_balanced`

#### Scenario: Short count is ready
- **WHEN** a new current count is less than expected cash
- **THEN** the OutcomeRun MUST be `ready` with `reason_code=ready_cash_short`

#### Scenario: Over count is ready
- **WHEN** a new current count is greater than expected cash
- **THEN** the OutcomeRun MUST be `ready` with `reason_code=ready_cash_over`

### Requirement: An open difference WorkItem does not block readiness
A short or over day MUST keep exactly one open `cash_difference_review` and MUST NOT open `close_confirmation_required`, and its OutcomeRun MUST remain `ready`. A balanced day MUST keep exactly one open `close_confirmation_required`, and its OutcomeRun MUST be `ready`. Open WorkItem priority MUST NOT be treated as the outcome status.

#### Scenario: Shortage keeps the difference job and stays ready
- **WHEN** the only open WorkItem is `cash_difference_review` for a short count
- **THEN** the OutcomeRun MUST be `ready` with `reason_code=ready_cash_short`

#### Scenario: Balanced close work stays ready
- **WHEN** the only open WorkItem is `close_confirmation_required`
- **THEN** the OutcomeRun MUST be `ready` with `reason_code=ready_balanced`

### Requirement: A later sale does not leave ready
After a current CashCount exists, another confirmed sale MUST recompute evidence and MUST leave `status=ready` while the resulting `cash_status` is `balanced`, `short`, or `over`. `ready_at` MUST NOT change. A reason change MUST write `outcome_run.status_changed` with `previous_status=ready`. There MUST be no `ready` to `in_progress` transition. A sale that does not change `cash_status` MUST update evidence and MUST NOT write `outcome_run.status_changed`.

#### Scenario: A later cash sale can change the ready reason
- **WHEN** the outcome is `ready_balanced` and a later cash sale makes the current count short
- **THEN** the same OutcomeRun MUST stay `ready` with `reason_code=ready_cash_short`, evidence MUST show the new expected cash, and `ready_at` MUST be unchanged

#### Scenario: A non-cash sale refreshes evidence only
- **WHEN** the outcome is `ready_balanced` and a later card sale leaves expected cash unchanged
- **THEN** the same OutcomeRun MUST stay `ready_balanced`, `sale_count` in evidence MUST increase, and no `outcome_run.status_changed` audit MUST be written

### Requirement: Confirmation completes the outcome
Successful `closing.confirm@1` MUST, in the same transaction, insert the ClosingSnapshot, set the day to `closed`, resolve the open Daily Close WorkItem, then complete the OutcomeRun or insert it already `completed` if it is missing, then set `outcome_run_id` on any of that day's WorkItems whose `outcome_run_id` is still null, including the WorkItem just resolved. Completion MUST set `completed_at` to the close instant, `reason_code=closed_confirmed`, `closing_snapshot_id` to that snapshot, and freeze evidence to the close-time figures. A missing-row insert MUST be `completed` with `ready_at` equal to `completed_at` and MUST write `outcome_run.created` only. The link MUST NOT write `work_item.created` or `work_item.resolved` and MUST NOT change the WorkItem id, status, resolution fields, or evidence. It MUST NOT write a second ClosingSnapshot or an OutcomeRun outbox event. A completed row MUST have `OperationalDay.status=closed`, exactly one ClosingSnapshot, `closing_snapshot_id` equal to that snapshot, non-null `ready_at`, non-null `completed_at`, `reason_code=closed_confirmed`, and no open Daily Close WorkItem. Completing an existing row MUST preserve its prior `ready_at`.

#### Scenario: Close links the snapshot
- **WHEN** `closing.confirm@1` commits for a ready day
- **THEN** the OutcomeRun MUST be `completed` with `reason_code=closed_confirmed` and `closing_snapshot_id` MUST equal the one ClosingSnapshot for that day

#### Scenario: Completion leaves no active Daily Close work
- **WHEN** close commits
- **THEN** no open Daily Close WorkItem MUST remain for that day

#### Scenario: Close repair links the resolved WorkItem
- **WHEN** the initializer was skipped, no OutcomeRun exists, the open Daily Close WorkItem has `outcome_run_id` null, and `closing.confirm@1` commits
- **THEN** the inserted OutcomeRun MUST be `completed`, that resolved WorkItem MUST reference it, and the link MUST NOT write `work_item.created` or a second `work_item.resolved`

### Requirement: Outcome writes join the parent transaction only
Outcome sync MUST run only inside successful `sale.commit@1`, a new current CashCount insert, and successful `closing.confirm@1`, in the order `daily-close-outcome` design records. `closing.prepare@1`, `operational_day.summary@1`, daily sales export, the Next Best Action GET, `operational_day.next_best_action@1`, an equal-amount cash-count read-back, a clarify, a stale confirmation, an idempotent replay, and an already-closed read-back MUST NOT insert or update an OutcomeRun. A failure before commit MUST leave no new OutcomeRun and no outcome audit from that attempt. Export column names, file bytes, and close phrases MUST stay unchanged.

#### Scenario: Preparation does not write the outcome
- **WHEN** the actor posts `preparar el cierre` for an open day that already has an OutcomeRun
- **THEN** that OutcomeRun MUST be unchanged and no outcome audit MUST be written

#### Scenario: Export does not write the outcome
- **WHEN** a tenant downloads the daily sales export
- **THEN** OutcomeRun, audit, outbox, and idempotency row counts MUST be unchanged by that download

#### Scenario: A rolled-back commit leaves no outcome
- **WHEN** the first commit of the day fails before commit after preparing an OutcomeRun insert
- **THEN** that OutcomeRun MUST NOT remain

### Requirement: Today-only initializer and no historical invention
Migration `0011` MUST NOT insert an OutcomeRun. The existing deploy command MUST, for each business's open OperationalDay dated today, ensure the OutcomeRun from that day's facts and set `outcome_run_id` on that day's WorkItems that are still null. An initializer insert for a day with no current CashCount MUST be `in_progress` with `ready_at` null. An initializer insert for a day that already has a current CashCount MUST be `ready` with `ready_at` equal to the insertion instant. It MUST skip closed days and older open days. It MUST NOT be an HTTP route and MUST NOT grant `BYPASSRLS`. An insert MUST audit `outcome_run.created` with a null actor, `route_or_tool` `outcome_run.bootstrap`, and `origin=rollout_bootstrap`. A second run MUST NOT insert another row and MUST NOT write audit when the stored status and reason already match. Already closed days MUST NOT gain a retroactive OutcomeRun.

#### Scenario: Open today is initialized without a read
- **WHEN** an open OperationalDay for today already has confirmed sales and no cash count, migration `0011` has been applied, and the initializer runs
- **THEN** one `in_progress` OutcomeRun MUST exist and that day's WorkItems MUST reference it

#### Scenario: A closed historical day is left alone
- **WHEN** a day is already `closed` with a ClosingSnapshot and the initializer runs
- **THEN** no OutcomeRun MUST be created for that day

#### Scenario: A second initializer run is quiet
- **WHEN** the initializer runs again and today's OutcomeRun already matches
- **THEN** no second OutcomeRun MUST exist and no additional `outcome_run.created` audit MUST be written

### Requirement: No merchant outcome API
This slice MUST NOT add `GET /api/v1/operational-days/current/outcome` or any other merchant OutcomeRun read or mutation route.

#### Scenario: Outcome route is absent
- **WHEN** the API route table is inspected
- **THEN** it MUST NOT contain an outcome collection or current-outcome route
