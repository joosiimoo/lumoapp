## MODIFIED Requirements

### Requirement: OperationalDay is one open business date
Persistence MUST create schema `operations` and table `operations.operational_days`. `OperationalDay` MUST include `id` (UUIDv7), `business_id`, `business_date` (`DATE`), `status`, `timezone`, `created_at`, and `updated_at`. Domain `OperationalDay` MUST NOT be a SQLAlchemy model. `status` MUST be `open` or `closed` only. `timezone` MUST be the IANA name copied from `identity.businesses.timezone` when the row is inserted. `created_at` MUST be the open instant. When runtime `sale.commit@1` inserts the day, `created_at` MUST be that insert's UTC instant and MUST NOT be copied from a session `updated_at`. When the `0005` backfill inserts the day, `created_at` and `updated_at` MUST both equal the minimum pre-upgrade `sale_sessions.updated_at` among the legacy confirmed sessions assigned to that `(business_id, business_date)`, and MUST NOT be the migration execution time. The backfill id MUST be a normal `new_uuid7()` value. That helper embeds the current millisecond and MUST NOT be extended to mint a historical timestamp. The UUID MUST NOT be the source of the historical open instant. The day table MUST NOT store sales totals, cash expected, cash counted, a cash difference, or a close timestamp. Those accepted figures live on `operations.closing_snapshots` after confirmation. The merchant's counted cash lives in `operations.cash_counts`. `UNIQUE (business_id, business_date)` and `UNIQUE (id, business_id)` MUST exist. Schemas `workflow` and `memory` MUST NOT be created. `not_started` MUST be represented by the absence of a row. Statuses `in_progress`, `waiting_for_information`, `ready_to_close`, `failed`, `closed_with_exceptions`, and `reopened` MUST NOT be persisted. Recording or revising a cash count MUST NOT change `status`. Only `closing.confirm@1` MAY set `status` from `open` to `closed`, and it MUST NOT insert the day.

#### Scenario: First confirmed sale opens one day
- **WHEN** the first `sale.commit@1` transition for a business date commits
- **THEN** exactly one `operations.operational_days` row MUST exist for that `(business_id, business_date)` with `status=open`, `timezone` equal to the business IANA timezone, and `created_at` equal to that runtime insert instant

#### Scenario: Intermediate states are rejected
- **WHEN** an insert sets `status=in_progress`, `status=ready_to_close`, or `status=failed`
- **THEN** the database MUST reject the row

#### Scenario: Cash counting does not change day status
- **WHEN** a cash count is recorded and then revised for today's open OperationalDay
- **THEN** that day's `status` MUST still be `open` and the day row MUST NOT gain a counted amount, a difference, or a close timestamp

#### Scenario: Close does not create a day
- **WHEN** the actor requests a close and no OperationalDay exists for today's business date
- **THEN** `operations.operational_days` MUST NOT gain a row

## ADDED Requirements

### Requirement: Commit refuses a closed operational day
On the mutating `sale.commit@1` path, after the session row is locked and before idempotency is reserved, the workflow MUST lock the existing OperationalDay for that confirmation's business date with `SELECT … FOR UPDATE` when the row exists. If `status=closed`, the workflow MUST clarify with reason `operational_day_closed` and the text `La jornada de hoy ya está cerrada. No puedo registrar otra venta en ese día.` It MUST NOT insert a `Payment`, MUST NOT set the session to `confirmed`, MUST NOT change `operational_day_id`, MUST NOT insert another day for that date, MUST NOT reopen the day, and MUST NOT reserve an idempotency row. If no day row exists, commit MUST keep the existing `ensure_open_day` insert. A confirm that already holds the day lock MUST be waited on; after it commits, this commit MUST see `closed` and refuse. A commit that holds the lock first MUST attach the sale to the still-open day, and the waiting confirm MUST recompute before it closes.

#### Scenario: Sale after close is refused
- **WHEN** today's OperationalDay is `closed` and the actor posts `efectivo` for a `ready_to_charge` session
- **THEN** the session MUST remain `ready_to_charge`, no `Payment` MUST be inserted, the day MUST remain `closed`, and no second OperationalDay MUST exist for that date

#### Scenario: Confirm and commit cannot both attach
- **WHEN** `sale.commit@1` and `closing.confirm@1` run concurrently for the same open day
- **THEN** a sale MUST NOT end `confirmed` with `operational_day_id` pointing at a day whose close transaction has already committed, and exactly one of the two writes MUST observe the other's committed state

#### Scenario: Next local date can still open
- **WHEN** a sale is confirmed after local midnight on the business calendar following a closed day
- **THEN** that sale MUST attach to a new open OperationalDay for the new business date and the previous closed day MUST remain `closed`

### Requirement: Summary of a closed day stays a live aggregate
`operational_day.summary@1` MUST keep computing totals from confirmed sales and recorded payments of that day. When the day is `closed`, `status` MUST be `closed`. The read MUST NOT substitute `ClosingSnapshot` totals, MUST NOT return expected cash or a cash difference, and MUST NOT write audit, outbox, or idempotency.

#### Scenario: Closed summary reports the day status
- **WHEN** today's OperationalDay is `closed` and its confirmed sales gross is `56.50`
- **THEN** `operational_day.summary@1` MUST return `status=closed` and `gross_sales_total` `56.50` from the live rows, and MUST NOT read those figures from `operations.closing_snapshots`
