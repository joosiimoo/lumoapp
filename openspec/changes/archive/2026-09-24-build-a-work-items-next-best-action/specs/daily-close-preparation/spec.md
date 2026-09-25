## MODIFIED Requirements

### Requirement: Preparation does not close the day
Calling `closing.prepare@1` or recording a cash count MUST NOT transition `OperationalDay.status`, MUST NOT persist a close timestamp on the day, and MUST NOT create a `ClosingSnapshot`, a close outbox event, a `NextBestAction` row, or an OutcomeRun. `status=closed` is owned only by `closing.confirm@1`. Preparation state for an open day MUST stay derived from the current `CashCount`. `closing.prepare@1` MUST NOT insert, update, or resolve a WorkItem. A successful insert of a new current `CashCount` MUST run Daily Close WorkItem sync in that same transaction. The equal-amount submission that writes no count MUST NOT run it.

#### Scenario: Day stays open after counting
- **WHEN** a balanced count is recorded for today's open OperationalDay and the actor does not confirm
- **THEN** that day's `status` MUST still be `open`, no close event MUST be emitted, and no `ClosingSnapshot` MUST exist

#### Scenario: Preparation read writes no WorkItem
- **WHEN** the actor posts `preparar el cierre` for an open day that already has the correct WorkItems
- **THEN** `closing.prepare@1` MUST NOT insert or update a WorkItem, an audit row, an outbox row, or an idempotency row

#### Scenario: A new count syncs WorkItems
- **WHEN** the first current `CashCount` is inserted and it is `balanced`
- **THEN** `cash_count_required` MUST be resolved and an open `close_confirmation_required` row MUST exist in that same transaction

## ADDED Requirements

### Requirement: Short and over still prepare without a new block
Recording a short or over count MUST sync exactly one open `cash_difference_review` and MUST NOT open `close_confirmation_required`. It MUST NOT make `closing.confirm@1` reject that `cash_status`. The preparation card's actions MUST stay the actions already specified for `daily_close_preparation@1`.

#### Scenario: Shortage still offers the existing request action
- **WHEN** expected cash is `22.50`, the new count is `20.00`, and the actor has not requested close
- **THEN** `daily_close_preparation@1` `actions` MUST still be exactly `closing.request@1` and the day MUST stay `open`
