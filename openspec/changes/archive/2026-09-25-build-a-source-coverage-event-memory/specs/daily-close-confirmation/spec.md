## MODIFIED Requirements

### Requirement: Confirm transaction order
The write MUST run in one application-owned transaction in this order: peek `lumo.message.confirm_close`; read timezone and currency; take one clock reading; derive today's business date; lock today's day `FOR UPDATE`; peek again; if `closed`, read back the snapshot; if open and uncounted, clarify; recompute `summarize_day` under the lock; verify the token; reserve idempotency only when a snapshot will be inserted; insert the snapshot while status is still `open`; update status to `closed` only where `status=open`; resolve the open Daily Close WorkItem with `day_closed`; complete the existing OutcomeRun, or insert it already `completed` if it is missing; set `outcome_run_id` on any WorkItems for that operational day whose `outcome_run_id` is still null, including the WorkItem just resolved; ensure the `sales` and `cash_count` coverage rows for `manual_capture` when absent, without changing an existing coverage row and without inserting a `daily_close` domain; insert one `daily_close_completed` business event; write the `closing.confirm@1` audit; enqueue one `closing.confirmed` outbox event; complete parent idempotency; commit. The `outcome_run_id` update MUST NOT write `work_item.created` or `work_item.resolved` and MUST NOT change that WorkItem's id, status, resolution fields, or evidence. Success and `daily_close_confirmed@1` MUST be produced only after commit. A failure before commit MUST leave the day `open` and MUST leave no snapshot, no completed OutcomeRun, no coverage row created by that attempt, no `daily_close_completed` event, no `closing.confirm@1` audit, no outcome audit, and no `closing.confirmed` event.

#### Scenario: Rollback leaves the day open
- **WHEN** a confirm writes the snapshot and the status change and then fails before commit
- **THEN** the day MUST remain `open`, no snapshot MUST remain, no OutcomeRun MUST be `completed`, no coverage row inserted by that attempt MUST remain, no `daily_close_completed` event MUST remain, and no close audit or outbox row MUST remain

### Requirement: Close idempotency audit and outbox
The message path MUST use `operation_type` `lumo.message.confirm_close`. The request hash MUST cover the raw message, `conversation_id`, and the token string. The same key and hash MUST return the stored body and MUST NOT insert a second snapshot, a second outcome completion, a second business event, an audit row, or an outbox event. The same key and a different hash MUST return `IDEMPOTENCY_CONFLICT` and MUST NOT write. A different key after the day is already `closed` MUST return the existing snapshot as `daily_close_confirmed@1` and MUST NOT insert a snapshot, a business event, an audit row, an outbox row, an idempotency row, or a second outcome completion. A clarify MUST NOT reserve a key. The successful close MUST write one audit action `closing.confirm@1` whose `before_payload` has `status=open`, `operational_day_id`, and `cash_count_id`, and whose `after_payload` has the snapshot id, the cash count id, the frozen totals, `cash_status`, `closed_at`, `previous_status=open`, and `new_status=closed`. It MUST enqueue exactly one `closing.confirmed` outbox event with those frozen values. It MUST NOT enqueue an OutcomeRun event, a `memory.event.created` event, or a `source_coverage.updated` event. A later read MUST use the snapshot row, not the audit row. Confirmed close text MUST stay unchanged.

#### Scenario: Same-key replay
- **WHEN** the actor resubmits the same confirm message, token, and idempotency key after a successful close
- **THEN** the original body MUST be returned and exactly one snapshot, one completed OutcomeRun, one `daily_close_completed` event, and one `closing.confirmed` event MUST exist

#### Scenario: Different key after close
- **WHEN** the day is already `closed` and the actor posts `confirmar cierre` with a new idempotency key
- **THEN** the response MUST describe the existing snapshot, and no second snapshot, business event, audit, outbox, outcome completion, or `lumo.message.confirm_close` row MUST be created

#### Scenario: Close audit and outbox once
- **WHEN** a confirm commits
- **THEN** exactly one `closing.confirm@1` audit row and exactly one `closing.confirmed` outbox row MUST exist for that snapshot, no OutcomeRun outbox row MUST exist, and no `memory.event.created` outbox row MUST exist

## ADDED Requirements

### Requirement: Close does not declare that every real-world sale was captured
A successful close MUST insert one `daily_close_completed` event whose facts reference that OutcomeRun and that ClosingSnapshot, as `factual-event-memory` requires. It MUST leave sales and cash-count coverage at `observed` with `limitation_code=only_lumo_registered_operations`. It MUST NOT insert a coverage domain `daily_close`. It MUST NOT change `OperationalDay` states, the closing token, short/over closability, or confirmed-close copy. The event MUST NOT state that all business sales were closed.

#### Scenario: Short close still closes and stays observed
- **WHEN** expected cash is `22.50`, the current count is `20.00`, and the actor confirms with a matching token
- **THEN** the day MUST be `closed`, the snapshot `cash_status` MUST be `short`, sales coverage MUST remain `observed`, and the close event `facts.cash_status` MUST be `short`
