## Purpose

Minimum OperationalDay for Build A: one open business date per business, confirmed sales attached at `sale.commit@1`, and a server-side daily summary. This is not Daily Close.

## Requirements

### Requirement: OperationalDay is one open business date
Persistence MUST create schema `operations` and table `operations.operational_days`. `OperationalDay` MUST include `id` (UUIDv7), `business_id`, `business_date` (`DATE`), `status`, `timezone`, `created_at`, and `updated_at`. Domain `OperationalDay` MUST NOT be a SQLAlchemy model. `status` MUST be `open` only. `timezone` MUST be the IANA name copied from `identity.businesses.timezone` when the row is inserted. `created_at` MUST be the open instant. When runtime `sale.commit@1` inserts the day, `created_at` MUST be that insert's UTC instant and MUST NOT be copied from a session `updated_at`. When the `0005` backfill inserts the day, `created_at` and `updated_at` MUST both equal the minimum pre-upgrade `sale_sessions.updated_at` among the legacy confirmed sessions assigned to that `(business_id, business_date)`, and MUST NOT be the migration execution time. The backfill id MUST be a normal `new_uuid7()` value. That helper embeds the current millisecond and MUST NOT be extended to mint a historical timestamp. The UUID MUST NOT be the source of the historical open instant. The table MUST NOT store sales totals, cash expected, cash counted, or a close timestamp. `UNIQUE (business_id, business_date)` and `UNIQUE (id, business_id)` MUST exist. Schemas `workflow` and `memory` MUST NOT be created. `not_started` MUST be represented by the absence of a row. Statuses `in_progress`, `waiting_for_information`, `ready_to_close`, `closed`, and `failed` MUST NOT be persisted in this change.

#### Scenario: First confirmed sale opens one day
- **WHEN** the first `sale.commit@1` transition for a business date commits
- **THEN** exactly one `operations.operational_days` row MUST exist for that `(business_id, business_date)` with `status=open`, `timezone` equal to the business IANA timezone, and `created_at` equal to that runtime insert instant

#### Scenario: Closing states are rejected
- **WHEN** an insert sets `status=closed` or `status=in_progress`
- **THEN** the database MUST reject the row

### Requirement: Business date comes from confirmed_at in the business timezone
After `0005`, the runtime membership instant MUST be `sales.sale_sessions.confirmed_at`, a timezone-aware UTC `timestamptz` written once on the confirming transition from one injectable clock reading. Runtime `business_date` MUST equal that instant converted with `zoneinfo` to `identity.businesses.timezone`, then the local calendar date. Runtime MUST NOT use `updated_at` or `created_at` as the confirmation clock. The domain MUST NOT hardcode `America/Mexico_City`. The PostgreSQL session `TimeZone` and the device timezone MUST NOT decide the date. Local midnight belongs to the new date: for `America/Mexico_City`, `2026-09-22T05:59:59Z` MUST be `2026-09-21` and `2026-09-22T06:00:00Z` MUST be `2026-09-22`. A sale started on an earlier local date and confirmed after midnight MUST belong to the confirmation date. An invalid IANA timezone MUST fail the commit transition and MUST NOT persist a day, a payment, or `confirmed`.

#### Scenario: Midnight boundary
- **WHEN** one sale is confirmed at `2026-09-22T05:59:59Z` and another at `2026-09-22T06:00:00Z` for a business whose timezone is `America/Mexico_City`
- **THEN** the first sale MUST belong to business date `2026-09-21` and the second MUST belong to `2026-09-22`, as two OperationalDay rows

#### Scenario: Late confirm uses confirmation time
- **WHEN** a session is created before local midnight and `sale.commit@1` confirms it after local midnight
- **THEN** `operational_day_id` MUST reference the business date of `confirmed_at`, not the session `created_at` or `updated_at`

#### Scenario: Runtime does not use updated_at
- **WHEN** `sale.commit@1` confirms a `ready_to_charge` session after `0005`
- **THEN** `confirmed_at` MUST equal the injectable UTC clock reading for that transition and MUST NOT equal `updated_at` unless that column happens to hold the same instant

### Requirement: Confirmed sale stores operational_day_id
A confirming `sale.commit@1` MUST set `operational_day_id` and `confirmed_at` on that `SaleSession`. `open` and `ready_to_charge` sessions MUST keep both NULL. PostgreSQL MUST enforce that `confirmed` rows have both values and that non-confirmed rows have neither. Foreign key `(operational_day_id, business_id)` MUST reference `operations.operational_days (id, business_id)`. There MUST NOT be a separate membership join table. `sale.start@1` and `sale.totalize@1` MUST NOT set either column and MUST NOT insert an OperationalDay.

#### Scenario: Confirmed row is attached
- **WHEN** `sale.commit@1` commits a `ready_to_charge` session
- **THEN** that session MUST have `status=confirmed`, non-null `confirmed_at`, and `operational_day_id` pointing at the OperationalDay for its business date

#### Scenario: Active sale is not attached
- **WHEN** a session is `open` or `ready_to_charge`
- **THEN** `operational_day_id` and `confirmed_at` MUST be NULL

### Requirement: Day ensure is inside the commit transaction
The transition path MUST ensure the OperationalDay in the same application-owned write transaction as the `Payment`, the status change, `sale.commit@1` audit, outbox, and `lumo.message.commit_sale`. Replay of the original idempotency key, a different-key read-back of an already confirmed session, and any clarify or deny path MUST NOT insert an OperationalDay. Success MUST be returned only after that transaction commits.

#### Scenario: Same-key replay does not duplicate the day
- **WHEN** the original `Idempotency-Key` and payload hash of a confirming commit are replayed
- **THEN** the original body MUST be returned, exactly one OperationalDay MUST exist for that business date, and the sale MUST still reference it once

#### Scenario: Read-back does not open a day
- **WHEN** the latest session is already `confirmed` and the actor posts `efectivo` with a new idempotency key
- **THEN** no additional OperationalDay MUST be inserted and `operational_day_id` MUST be unchanged

### Requirement: Concurrent first sales share one day
`INSERT … ON CONFLICT (business_id, business_date) DO NOTHING` MUST be used so a unique violation does not abort the sale transaction. The loser MUST select the winning row and attach its sale to that id. Exactly one `operational_day.opened` audit row and one matching outbox event MUST be written for that insert. A later confirming commit on the same business date MUST reuse the row and MUST NOT emit a second opened event.

#### Scenario: Two first commits
- **WHEN** two different `ready_to_charge` sessions for the same business and business date commit concurrently
- **THEN** exactly one OperationalDay MUST exist and both confirmed sessions MUST reference that id

#### Scenario: Second sale same day
- **WHEN** two sales are confirmed on the same local business date, including a second sale started on the same `conversation_id` after the first confirmation
- **THEN** both MUST reference the same `operational_day_id`

### Requirement: Summary is aggregated from confirmed sales
`operational_day.summary@1` MUST compute `sale_count`, `gross_sales_total`, `cash_total`, `card_total`, and `transfer_total` in the backend from confirmed sessions of that day and their recorded payments. Amounts MUST be `Decimal` quantized to two decimal places. `gross_sales_total` MUST equal the sum of the three method totals and MUST equal the sum of `payments.amount`. Empty aggregates MUST be `0.00`. Currency MUST be the business currency. `open` and `ready_to_charge` sessions MUST be excluded. The client and the interpreter MUST NOT supply or calculate these numbers. A currency mismatch MUST fail the read without returning partial totals.

#### Scenario: Method buckets
- **WHEN** the current business date has one confirmed cash sale of `56.50`, one confirmed card sale of `10.00`, and one confirmed transfer sale of `24.00`
- **THEN** the summary MUST report `sale_count=3`, `gross_sales_total=90.50`, `cash_total=56.50`, `card_total=10.00`, and `transfer_total=24.00` in the business currency

#### Scenario: Drafts are excluded
- **WHEN** the business date also has an `open` or `ready_to_charge` session
- **THEN** that session MUST NOT increase `sale_count` or any total

### Requirement: Zero sales do not create a day
When no OperationalDay exists for today's business date, the summary MUST return `operational_day_id=null`, `status=null`, `sale_count=0`, and `0.00` for every total, with `business_date` equal to today in the business timezone. The read MUST NOT insert a row. Repeating the read MUST NOT insert a row and MUST NOT write audit, outbox, or idempotency records.

#### Scenario: Ventas de hoy with no sales
- **WHEN** the actor posts `ventas de hoy` and no confirmed sale exists for today's business date
- **THEN** the response MUST be that zero summary and `operations.operational_days` MUST NOT gain a row

#### Scenario: Repeat read does not mutate
- **WHEN** the actor posts `cómo vamos hoy` twice, with no confirming commit between them
- **THEN** both responses MUST carry the same totals and the second request MUST NOT insert an OperationalDay, audit row, outbox row, or idempotency row

### Requirement: Closed phrases invoke the read tool
After accent folding, case folding, whitespace collapse, and stripping one surrounding layer of `¿?¡!`, the scripted interpreter MUST map only `como vamos hoy`, `ventas de hoy`, and `cuanto vendimos hoy` to `intent=day_summary` and `candidate_tool=operational_day.summary@1`. The interpreter MUST NOT access a repository. Any other analytics wording, including `ventas de la semana`, `ventas de ayer`, and `ventas de hoy por favor`, MUST follow the existing non-mutating unsupported clarification and MUST NOT call the summary tool.

#### Scenario: Approved phrase
- **WHEN** the scripted interpreter receives `¿Cuánto vendimos hoy?`
- **THEN** the decision MUST be `day_summary` for `operational_day.summary@1`

#### Scenario: Unsupported analytics phrase
- **WHEN** the actor posts `ventas de la semana`
- **THEN** the system MUST clarify without creating an OperationalDay, without a summary card, and without changing any sale

### Requirement: Day creation is audited once
When runtime `sale.commit@1` inserts an OperationalDay, it MUST write audit action `operational_day.opened` and outbox event `operational_day.opened` with `operational_day_id`, `business_date`, `timezone`, and `status`. Reusing a day MUST NOT write those. The confirming `sale.commit@1` audit `after_payload` and the `sale.confirmed` outbox payload MUST include `operational_day_id`. A summary read MUST NOT write audit or outbox. The `0005` legacy backfill MUST NOT write `operational_day.opened` audit or outbox, MUST NOT write or rewrite `sale.commit` audit or `sale.confirmed` events, and MUST NOT write idempotency records. That backfill is data repair. The exactly-once opened event applies only to a day inserted by `sale.commit` after `0005`.

#### Scenario: Opened event once
- **WHEN** `sale.commit@1` inserts the OperationalDay for a business date and a second sale of that date commits later
- **THEN** exactly one `operational_day.opened` audit row and one `operational_day.opened` outbox row MUST exist, and both sales' `sale.confirmed` payloads MUST include that `operational_day_id`

#### Scenario: Backfilled day is not a runtime open
- **WHEN** `0005` inserts an OperationalDay for a legacy confirmed sale and a later `sale.commit@1` reuses that same day
- **THEN** no `operational_day.opened` audit or outbox row MUST exist for that day

### Requirement: OperationalDay is tenant scoped
`operations.operational_days` MUST ENABLE and FORCE ROW LEVEL SECURITY with policy `tenant_isolation` on `business_id`, and MUST grant `lumo_app` the same DML as other tenant tables. `business_id` MUST be copied from `TenantContext`. A summary or select under business B MUST NOT return Carrota's OperationalDay or totals.

#### Scenario: Cross-business summary
- **WHEN** business B requests today's summary after Carrota has confirmed sales
- **THEN** business B MUST receive its own zero or own-day summary and MUST NOT receive Carrota's `operational_day_id`, sale count, or totals

### Requirement: Failed commit does not leave a partial day
If the confirming transaction fails before commit, a day inserted in that transaction MUST NOT remain, the session MUST stay `ready_to_charge`, and `operational_day_id` MUST stay NULL. A day committed by an earlier sale MUST remain when a later sale's transaction rolls back, and that later session MUST stay unattached.

#### Scenario: Rollback of the first sale
- **WHEN** the first commit of a business date writes the day, the payment, and `confirmed`, then fails before commit
- **THEN** no OperationalDay, no `Payment`, and no `confirmed` session MUST remain

#### Scenario: Rollback of a later sale
- **WHEN** a business date already has a committed OperationalDay and a second commit fails before commit
- **THEN** the existing OperationalDay and the first sale MUST remain, and the second session MUST stay `ready_to_charge` with `operational_day_id` NULL
