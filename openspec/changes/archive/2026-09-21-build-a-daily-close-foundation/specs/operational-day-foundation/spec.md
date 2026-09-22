## MODIFIED Requirements

### Requirement: OperationalDay is one open business date
Persistence MUST create schema `operations` and table `operations.operational_days`. `OperationalDay` MUST include `id` (UUIDv7), `business_id`, `business_date` (`DATE`), `status`, `timezone`, `created_at`, and `updated_at`. Domain `OperationalDay` MUST NOT be a SQLAlchemy model. `status` MUST be `open` only. `timezone` MUST be the IANA name copied from `identity.businesses.timezone` when the row is inserted. `created_at` MUST be the open instant. When runtime `sale.commit@1` inserts the day, `created_at` MUST be that insert's UTC instant and MUST NOT be copied from a session `updated_at`. When the `0005` backfill inserts the day, `created_at` and `updated_at` MUST both equal the minimum pre-upgrade `sale_sessions.updated_at` among the legacy confirmed sessions assigned to that `(business_id, business_date)`, and MUST NOT be the migration execution time. The backfill id MUST be a normal `new_uuid7()` value. That helper embeds the current millisecond and MUST NOT be extended to mint a historical timestamp. The UUID MUST NOT be the source of the historical open instant. The table MUST NOT store sales totals, cash expected, cash counted, a cash difference, or a close timestamp; the merchant's counted cash lives in `operations.cash_counts` and the difference is derived. `UNIQUE (business_id, business_date)` and `UNIQUE (id, business_id)` MUST exist. Schemas `workflow` and `memory` MUST NOT be created. `not_started` MUST be represented by the absence of a row. Statuses `in_progress`, `waiting_for_information`, `ready_to_close`, `closed`, and `failed` MUST NOT be persisted, and recording or revising a cash count MUST NOT introduce one.

#### Scenario: First confirmed sale opens one day
- **WHEN** the first `sale.commit@1` transition for a business date commits
- **THEN** exactly one `operations.operational_days` row MUST exist for that `(business_id, business_date)` with `status=open`, `timezone` equal to the business IANA timezone, and `created_at` equal to that runtime insert instant

#### Scenario: Closing states are rejected
- **WHEN** an insert sets `status=closed` or `status=in_progress`
- **THEN** the database MUST reject the row

#### Scenario: Cash counting does not change day status
- **WHEN** a cash count is recorded and then revised for today's OperationalDay
- **THEN** that day's `status` MUST still be `open` and the day row MUST NOT gain a counted amount, a difference, or a close timestamp

### Requirement: Zero sales do not create a day
When no OperationalDay exists for today's business date, the summary MUST return `operational_day_id=null`, `status=null`, `sale_count=0`, and `0.00` for every total, with `business_date` equal to today in the business timezone. The close-preparation read MUST return its own not-started payload for the same condition. Neither read MUST insert a row. Repeating either read MUST NOT insert a row and MUST NOT write audit, outbox, or idempotency records. A cash-count write MUST also refuse to create the day and MUST leave the table empty for that date.

#### Scenario: Ventas de hoy with no sales
- **WHEN** the actor posts `ventas de hoy` and no confirmed sale exists for today's business date
- **THEN** the response MUST be that zero summary and `operations.operational_days` MUST NOT gain a row

#### Scenario: Repeat read does not mutate
- **WHEN** the actor posts `cómo vamos hoy` twice, with no confirming commit between them
- **THEN** both responses MUST carry the same totals and the second request MUST NOT insert an OperationalDay, audit row, outbox row, or idempotency row

#### Scenario: Preparation read does not open a day
- **WHEN** the actor posts `preparar el cierre` and no confirmed sale exists for today's business date
- **THEN** the response MUST be the not-started preparation payload and `operations.operational_days` MUST NOT gain a row

#### Scenario: Cash count does not open a day
- **WHEN** the actor posts `tengo 120 en caja` and no confirmed sale exists for today's business date
- **THEN** the response MUST clarify, `operations.operational_days` MUST NOT gain a row, and `operations.cash_counts` MUST stay empty

### Requirement: Day creation is audited once
When runtime `sale.commit@1` inserts an OperationalDay, it MUST write audit action `operational_day.opened` and outbox event `operational_day.opened` with `operational_day_id`, `business_date`, `timezone`, and `status`. Reusing a day MUST NOT write those. The confirming `sale.commit@1` audit `after_payload` and the `sale.confirmed` outbox payload MUST include `operational_day_id`. A summary read and a close-preparation read MUST NOT write audit or outbox. A cash-count write MUST NOT write `operational_day.opened` audit or outbox, because it never inserts a day. The `0005` legacy backfill MUST NOT write `operational_day.opened` audit or outbox, MUST NOT write or rewrite `sale.commit` audit or `sale.confirmed` events, and MUST NOT write idempotency records. That backfill is data repair. The exactly-once opened event applies only to a day inserted by `sale.commit` after `0005`.

#### Scenario: Opened event once
- **WHEN** `sale.commit@1` inserts the OperationalDay for a business date and a second sale of that date commits later
- **THEN** exactly one `operational_day.opened` audit row and one `operational_day.opened` outbox row MUST exist, and both sales' `sale.confirmed` payloads MUST include that `operational_day_id`

#### Scenario: Backfilled day is not a runtime open
- **WHEN** `0005` inserts an OperationalDay for a legacy confirmed sale and a later `sale.commit@1` reuses that same day
- **THEN** no `operational_day.opened` audit or outbox row MUST exist for that day

#### Scenario: Cash count emits no day event
- **WHEN** a cash count is recorded for an existing OperationalDay
- **THEN** no additional `operational_day.opened` audit or outbox row MUST exist for that day

## ADDED Requirements

### Requirement: Cash counts belong to an operational day
Every `CashCount` MUST reference exactly one `OperationalDay` of the same business through the composite foreign key `(operational_day_id, business_id)`. An `OperationalDay` MAY have no cash count, one cash count, or a chain of superseded counts with exactly one current count. Deleting an `OperationalDay` MUST NOT be possible while a `CashCount` references it. Membership MUST NOT be re-derived at read time from timestamps, and a `CashCount` MUST NOT move between days.

#### Scenario: Count attaches to today's day
- **WHEN** a cash count is recorded while today's OperationalDay exists
- **THEN** its `operational_day_id` MUST equal that day's id and its `business_id` MUST equal that day's `business_id`

#### Scenario: Day cannot be deleted under a count
- **WHEN** a delete is attempted on an `operations.operational_days` row that still has a `CashCount`
- **THEN** the database MUST reject it unless the cash count is deleted first in the same transaction
