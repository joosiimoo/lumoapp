## Purpose

Append-only `CashCount` for daily close preparation: merchant-provided counted cash, one current row per `OperationalDay`, tenant-safe supersede chain, and `closing.submit_cash_count@1`. A closed day refuses another count. Confirmation itself is `daily-close-confirmation`.

## Requirements

### Requirement: CashCount is a persisted append-only count
Persistence MUST create table `operations.cash_counts` in the existing `operations` schema. `CashCount` MUST include `id` (UUIDv7), `business_id`, `operational_day_id`, `actor_id`, `amount` (`numeric(12,2)`), `currency`, `source`, `counted_at` (`timestamptz`), `supersedes_cash_count_id` (nullable), `superseded_by_id` (nullable), `created_at`, and `updated_at`. Domain `CashCount` MUST NOT be a SQLAlchemy model and MUST NOT import SQLAlchemy, FastAPI, or Flutter. `amount` MUST be `Decimal`/`numeric` and MUST NEVER be binary float. A CHECK MUST reject a negative `amount`. `source` MUST be CHECK-constrained to `manual_capture`. `currency` MUST be the business currency at write time. The table MUST NOT store `expected_cash`, `cash_difference`, `cash_status`, denominations, a note, evidence ids, a closing snapshot id, or a close timestamp. Foreign key `(operational_day_id, business_id)` MUST reference `operations.operational_days (id, business_id)`. `UNIQUE (id, business_id)`, `UNIQUE (supersedes_cash_count_id)`, `UNIQUE (superseded_by_id)`, and indexes on `business_id` and `operational_day_id` MUST exist. A row MUST NOT reference itself through either supersede column. Tables `closing_snapshots`, `work_items`, and schemas `workflow` and `memory` MUST NOT be created.

Both supersede columns MUST be enforced by composite tenant-safe foreign keys and MUST NOT be enforced by `id` alone. `(supersedes_cash_count_id, business_id)` MUST reference `operations.cash_counts (id, business_id)` and MUST be immediate. `(superseded_by_id, business_id)` MUST reference `operations.cash_counts (id, business_id)` and MUST be `DEFERRABLE INITIALLY DEFERRED`, because a recount retires the previous row before the new row exists. `UNIQUE (supersedes_cash_count_id)`, `UNIQUE (superseded_by_id)`, and the current-count partial unique index MUST remain immediate. FORCE RLS MUST remain in place as defense in depth and MUST NOT be the only protection against a cross-tenant link.

#### Scenario: Supersede links cannot cross tenants
- **WHEN** a write attempts to set `supersedes_cash_count_id` or `superseded_by_id` on a Carrota row to the id of a `CashCount` belonging to business B
- **THEN** the database MUST reject it because no `(id, business_id)` pair matches under Carrota's `business_id`, and no cross-tenant chain MUST exist after the transaction

#### Scenario: Deferred links are valid at commit
- **WHEN** a recount transaction commits
- **THEN** every `superseded_by_id` MUST reference an existing row of the same `business_id`, and a transaction that ends with a `superseded_by_id` pointing at a non-existent id MUST fail at commit

#### Scenario: First count persists the merchant amount
- **WHEN** the actor records a cash count of `20.00` for today's OperationalDay
- **THEN** exactly one `operations.cash_counts` row MUST exist for that `operational_day_id` with `amount=20.00`, the business currency, `source=manual_capture`, the acting `actor_id`, a non-null `counted_at`, and both supersede columns NULL

#### Scenario: Negative amount is rejected
- **WHEN** an insert or a write request carries `amount = -1.00`
- **THEN** the write MUST fail, and no `operations.cash_counts` row MUST remain for that attempt

#### Scenario: Derived values are not columns
- **WHEN** `operations.cash_counts` is inspected after migration
- **THEN** it MUST NOT contain an `expected_cash`, `cash_difference`, `cash_status`, or denomination column

### Requirement: Exactly one current count per operational day
The **current** `CashCount` for an `OperationalDay` MUST be the single row whose `superseded_by_id` is NULL. A partial unique index `uq_cash_counts_current` on `(operational_day_id) WHERE superseded_by_id IS NULL` MUST enforce that and MUST remain immediate. A superseded row MUST NOT be deleted, and its `amount`, `actor_id`, and `counted_at` MUST NOT be modified. The supersede chain MUST stay linear.

A recount MUST execute in this order inside the write transaction, with today's `operations.operational_days` row already locked `FOR UPDATE`:

1. Read the current `CashCount` (`superseded_by_id IS NULL`).
2. Generate the new count id in the application.
3. `UPDATE` the previous current row to set `superseded_by_id` to the new count id.
4. `INSERT` the new row with that id, `supersedes_cash_count_id` set to the previous row id, and `superseded_by_id` NULL.

The new row MUST NOT be inserted before the previous row is retired. This ordering keeps the immediate partial unique index satisfied at every statement boundary: step 3 removes the previous row from the index predicate before step 4 adds the new row, so two rows MUST never simultaneously satisfy `superseded_by_id IS NULL` for one `operational_day_id`. A first count for a day MUST be a single insert with both supersede columns NULL.

#### Scenario: Recount succeeds against the immediate current index
- **WHEN** the current count is `20.00` and the actor records `22.50` for the same OperationalDay
- **THEN** the transaction MUST commit, two rows MUST exist, the `20.00` row MUST have `superseded_by_id` equal to the `22.50` row id, the `22.50` row MUST have `supersedes_cash_count_id` equal to the `20.00` row id and `superseded_by_id` NULL, exactly one row for that day MUST have `superseded_by_id` NULL, and the `20.00` row's `amount`, `actor_id`, and `counted_at` MUST be unchanged

#### Scenario: Rollback between retire and insert restores the previous count
- **WHEN** a recount fails after the previous row is updated and before or after the new row is inserted, and the transaction rolls back
- **THEN** the previous row's `superseded_by_id` MUST be NULL again, it MUST be the current count with its original `amount` and `counted_at`, no new row MUST exist, and no compensating write MUST be required

#### Scenario: Two current counts are impossible
- **WHEN** a second row with `superseded_by_id` NULL is inserted for an `operational_day_id` that already has a current count
- **THEN** PostgreSQL MUST reject the row and the transaction MUST roll back

### Requirement: A cash count requires an existing operational day
A `CashCount` MUST reference an existing `OperationalDay` for the current business date. Recording cash MUST NOT insert an `OperationalDay` and MUST NOT change `OperationalDay.status`. When no `OperationalDay` exists for today's business date, the write MUST be refused as a non-mutating clarification under `CLOSE-001` with reason `operational_day_not_started`, and MUST NOT write a cash count, an operational day, an audit row, an outbox row, or an idempotency record. Today's business date MUST be derived from one application clock reading converted to `identity.businesses.timezone` with the existing business-date rule. The domain MUST NOT hardcode a timezone.

#### Scenario: Counting before any sale clarifies
- **WHEN** the actor posts `tengo 120 en caja` and no confirmed sale exists for today's business date
- **THEN** the response MUST be a clarification, `operations.cash_counts` MUST stay empty, `operations.operational_days` MUST NOT gain a row, and no audit, outbox, or idempotency row MUST be written

#### Scenario: Counting with sales attaches to today's day
- **WHEN** a confirmed cash sale already opened today's OperationalDay and the actor records a count
- **THEN** the persisted `CashCount.operational_day_id` MUST equal that day's id and that day's `status` MUST remain `open`

### Requirement: Tool closing.submit_cash_count@1
`ToolRegistry` MUST register `closing.submit_cash_count@1` as a write tool. Input MUST be `{ "amount": decimal-string }` and MUST NOT accept `expected_cash`, `cash_difference`, `counted_cash`, `cash_status`, `operational_day_id`, `business_date`, `currency`, `actor_id`, `source`, or a client timestamp. `amount` MUST be a non-negative decimal string with at most two fraction digits; any other value MUST fail validation without a write. Output MUST be the close-preparation payload plus `cash_count_id` and `supersedes_cash_count_id`. Permission MUST be `closing.submit_cash_count` (SRS §11). Policy MUST be `CLOSE-001`. Side effect MUST be `write`. Idempotency MUST be required. `business_id` and `actor_id` MUST be copied from `TenantContext` and MUST NEVER come from client, interpreter, or tool input.

#### Scenario: Registered write tool shape
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `closing.submit_cash_count@1` as registered with `side_effect=write`, `requires_idempotency=true`, permission `closing.submit_cash_count`, and an input schema whose only property is `amount`

#### Scenario: Model-supplied difference is ignored
- **WHEN** a decision for `closing.submit_cash_count@1` includes an `expected_cash`, `cash_difference`, or `operational_day_id` argument
- **THEN** those values MUST NOT be persisted or returned, and the response MUST still use the backend-computed expected cash and difference under `CLOSE-001`

#### Scenario: Invalid amount does not write
- **WHEN** the submitted amount is `1.005`, `-1`, `abc`, or empty
- **THEN** no `CashCount` MUST be written and the sale, payment, and operational-day rows MUST be unchanged

### Requirement: Cash count write is one transaction
The write MUST run in one application-owned transaction with the following step order, which is normative:

1. Peek the `lumo.message.record_cash_count` idempotency record for the tenant and key, without reserving it.
2. Read the business timezone and currency, take one clock reading, and derive today's business date.
3. Lock today's `operations.operational_days` row with `SELECT … FOR UPDATE`.
4. Refuse with a clarification when no day exists.
5. Compute `expected_cash` from persisted confirmed payments under that lock.
6. Read the current `CashCount` and return it as a read-back when its amount equals the submitted amount.
7. Reserve the idempotency record only when persisted state must change.
8. Perform the first count or the recount in the order required by the current-count requirement.
9. Write audit.
10. Enqueue outbox.
11. Complete the idempotency record.
12. Commit, at which point the deferred `superseded_by_id` foreign key MUST be validated.

The idempotency peek MUST happen before the day lock, and the equal-amount read-back check MUST happen before any idempotency record is reserved. Success and the generative UI card MUST be produced only after that transaction commits. A failure before commit MUST leave the previous current `CashCount` unchanged and MUST NOT leave a new row, audit row, outbox row, or completed idempotency record. The write MUST NOT insert or modify a `SaleSession`, `SaleItem`, `Payment`, or `OperationalDay`.

#### Scenario: Rollback preserves the previous count
- **WHEN** a count of `20.00` is already current and a later write of `22.50` fails before commit
- **THEN** the current count MUST still be `20.00` with `superseded_by_id` NULL, no `22.50` row MUST exist, and no `closing.submit_cash_count@1` audit or `cash_count.recorded` outbox row MUST remain for the failed attempt

#### Scenario: Success only after commit
- **WHEN** the request transaction rolls back after the cash-count write
- **THEN** the API MUST NOT return a success payload and MUST NOT emit `daily_close_preparation@1` for that attempt

### Requirement: Concurrent counts serialize on the operational day
Two concurrent cash-count writes for the same `OperationalDay` MUST serialize on `SELECT … FOR UPDATE` of that day's row. The loser MUST re-read the current count after acquiring the lock and MUST either supersede it or return it as a read-back. A lost update MUST NOT occur, exactly one row MUST remain current, and the supersede chain MUST remain linear with both amounts preserved. Advisory locks, Redis, distributed locks, and serializable isolation MUST NOT be introduced.

#### Scenario: Two concurrent recounts
- **WHEN** two writes with different idempotency keys and different amounts run concurrently against the same OperationalDay that already has a current count
- **THEN** exactly one row MUST have `superseded_by_id` NULL, every submitted amount MUST be reachable through the supersede chain, and both successful HTTP responses MUST describe committed state

### Requirement: Cash count audit and outbox
The write MUST record audit action `closing.submit_cash_count@1` in the same transaction, with `before_payload` carrying the previous count id and amount (or null when there was none) and `after_payload` carrying `cash_count_id`, `operational_day_id`, `business_date`, `amount`, `currency`, `expected_cash`, `cash_difference`, `cash_status`, `counted_at`, and `supersedes_cash_count_id`. It MUST enqueue exactly one outbox event `cash_count.recorded` per persisted count, carrying `cash_count_id`, `operational_day_id`, `business_date`, `amount`, `currency`, and `supersedes_cash_count_id`. A same-key replay, an equal-amount read-back, a refused write, and any read MUST write neither audit nor outbox. Audit MUST NOT be the source of truth for a later read. No worker, poller, or external broker MUST be introduced.

#### Scenario: Recount audit shows both amounts
- **WHEN** a count of `20.00` is superseded by `22.50`
- **THEN** exactly two `closing.submit_cash_count@1` audit rows MUST exist, the second MUST show the previous amount `20.00` in `before_payload` and `22.50` with its difference in `after_payload`, and exactly two `cash_count.recorded` outbox rows MUST exist

#### Scenario: Read writes no events
- **WHEN** the actor requests close preparation twice with no count in between
- **THEN** no `closing.submit_cash_count@1` audit row and no `cash_count.recorded` outbox row MUST be written

### Requirement: Cash count idempotency
The message path MUST use `operation_type` `lumo.message.record_cash_count`, distinct from `lumo.message.add_sale_item`, `lumo.message.totalize_sale`, and `lumo.message.commit_sale`.

The key MUST be peeked before the operational day is locked and before any state is read for the decision. A completed record with the same key and payload hash MUST return the stored original body verbatim, with no lock-dependent mutation, no second row, no audit, and no event. The same key with a different payload hash MUST return `IDEMPOTENCY_CONFLICT` with no write. A key that is absent, still processing, or failed MUST fall through to the remaining steps, where reserving the key applies the existing concurrent-duplicate and retry-after-failure rules.

A new key whose amount equals the current count MUST be a stable read-back: current preparation MUST be returned with no new `CashCount`, no audit, no outbox, and no new idempotency record. A new key whose amount differs from the current count MUST create a recount and MUST reserve and complete exactly one idempotency record.

A same-key replay and a different-key equal-amount read-back MUST NOT be conflated. A same-key replay MUST return the body persisted with the original count, even when `expected_cash` has changed since that count, so `expected_cash`, `cash_difference`, and `cash_status` in a replay MAY be older than current state. A different-key equal-amount read-back MUST return current preparation computed at that moment, including the live `expected_cash`, live `cash_difference`, and live `cash_status`, together with the existing `cash_count_id` and `counted_at`.

#### Scenario: Same-key replay does not duplicate the count
- **WHEN** the actor resubmits `tengo 20 en caja` with the same idempotency key and payload hash after a successful count
- **THEN** the original body MUST be returned, exactly one `CashCount` MUST exist for that day, and a second `cash_count.recorded` outbox row MUST NOT exist

#### Scenario: Different key with the same amount is a read-back
- **WHEN** the current count is `20.00` and the actor posts `tengo 20 en caja` again with a new idempotency key
- **THEN** the response MUST describe the current count, no second row MUST be inserted, no new `lumo.message.record_cash_count` idempotency row MUST exist, and no audit or outbox row MUST be written

#### Scenario: Different key with a new amount recounts
- **WHEN** the current count is `20.00` and the actor posts `conté 22.50` with a new idempotency key
- **THEN** a new current `CashCount` of `22.50` MUST exist, the `20.00` row MUST be superseded, one new audit and one new outbox row MUST exist, and exactly one new completed `lumo.message.record_cash_count` idempotency record MUST exist

#### Scenario: Same key with a different amount conflicts
- **WHEN** the actor resubmits the same idempotency key with `22.50` after a completed count of `20.00`
- **THEN** the response MUST be `IDEMPOTENCY_CONFLICT`, the current count MUST still be `20.00`, and no new `CashCount`, audit, or outbox row MUST exist

#### Scenario: Replay is stale while a new-key read-back is live
- **WHEN** a count of `20.00` is recorded against `expected_cash` `20.00`, another cash sale of `2.50` is then confirmed, and the actor afterwards submits `20.00` once with the original key and once with a new key
- **THEN** the same-key replay MUST return the original body with `expected_cash` `20.00`, `cash_difference` `0.00`, and `cash_status` `balanced`, the new-key read-back MUST return `expected_cash` `22.50`, `cash_difference` `-2.50`, and `cash_status` `short`, and exactly one `CashCount` MUST exist for that day

### Requirement: CashCount is tenant scoped
`operations.cash_counts` MUST ENABLE and FORCE ROW LEVEL SECURITY with policy `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`, and MUST grant `lumo_app` the same DML as `operations.operational_days`. `business_id` MUST be copied from `TenantContext`. Business B MUST NOT read, update, supersede, or delete another business's `CashCount`, and MUST NOT attach a count to another business's `OperationalDay`.

#### Scenario: Cross-business read denied
- **WHEN** business B requests close preparation after Carrota recorded a count of `20.00`
- **THEN** business B MUST receive its own state with `counted_cash` null and MUST NOT receive Carrota's `cash_count_id`, amount, or difference

#### Scenario: Cross-business write denied
- **WHEN** business B attempts to write a `CashCount` referencing Carrota's `operational_day_id`
- **THEN** the write MUST fail and Carrota's current count MUST be unchanged

#### Scenario: Cross-business supersede chain denied at the database
- **WHEN** a statement executed with Carrota's tenant context attempts to link a Carrota `CashCount` to business B's `CashCount` through `supersedes_cash_count_id` or `superseded_by_id`
- **THEN** the composite foreign key MUST reject it independently of row-level security, and no `CashCount` MUST have a supersede link to a row with a different `business_id`

### Requirement: A closed day refuses another cash count
`closing.submit_cash_count@1` MUST lock today's OperationalDay `FOR UPDATE` before appending a count. When that row's `status` is `closed`, the write MUST clarify with reason `operational_day_closed` and the text `La jornada de hoy ya está cerrada. No puedo cambiar el conteo.` It MUST NOT insert a `CashCount`, MUST NOT set `superseded_by_id` on the current row, MUST NOT change the snapshot, and MUST NOT write audit, outbox, or idempotency. The current count MUST remain the count referenced by the `ClosingSnapshot`.

#### Scenario: Recount after close
- **WHEN** today's day is `closed` with a current count of `22.50` and the actor posts `tengo 20 en caja`
- **THEN** the response MUST clarify with `operational_day_closed`, the `22.50` row MUST still have `superseded_by_id` NULL, and no new cash-count, audit, or outbox row MUST exist
