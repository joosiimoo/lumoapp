# source-coverage Specification

## Purpose

Source Coverage answers which Build A domains Lumo has observed for one OperationalDay, and from which operational source. A row does not mean Lumo captured 100% of the real-world business operation. A completed close, balanced, short, or over cash, a completed OutcomeRun, or zero open WorkItems does not imply full source coverage.

## Requirements

### Requirement: Source coverage is one observed row per day, domain, and source
The system MUST persist Source Coverage only in `operations.source_coverage_records`. A row MUST store exactly `id`, `business_id`, `operational_day_id`, `domain`, `source_type`, `status`, `limitation_code`, and `created_at`. `domain` MUST be `sales` or `cash_count`. `source_type` MUST be `manual_capture`. `status` MUST be `observed`. `limitation_code` MUST be `only_lumo_registered_operations`. The database MUST reject any other domain, source type, status, or limitation code. Unique constraint `uq_source_coverage_records_identity` MUST enforce one row for `(business_id, operational_day_id, domain, source_type)`. Foreign key `fk_source_coverage_records_operational_day` MUST bind `(operational_day_id, business_id)` to `operations.operational_days (id, business_id)`. The row MUST NOT store `updated_at`, `last_observed_at`, `observation_count`, freshness, `evidence`, health, prose, an actor, a completeness percentage, or a foreign key to an OutcomeRun. A reuse MUST NOT update the row. `daily_close` MUST NOT be a domain. `lumo_app` MUST NOT receive `UPDATE` on this table.

#### Scenario: First confirmed sale creates sales coverage
- **WHEN** today's first confirmed sale commits and no coverage row exists for that day
- **THEN** exactly one row MUST exist with `domain=sales`, `source_type=manual_capture`, `status=observed`, and `limitation_code=only_lumo_registered_operations`

#### Scenario: Second confirmed sale reuses the sales row
- **WHEN** a second confirmed sale commits for that same operational day
- **THEN** the same coverage id MUST remain the only `sales` / `manual_capture` row, `status` MUST be unchanged, `limitation_code` MUST be unchanged, `created_at` MUST be unchanged, and no row update MUST occur

#### Scenario: A typed payment and a payment action are the same source
- **WHEN** one confirmed sale was committed by a typed payment phrase and another by `sale.pay.cash@1`, `sale.pay.card@1`, or `sale.pay.transfer@1`
- **THEN** both MUST share one `sales` / `manual_capture` row and `source_type` MUST be `manual_capture`

#### Scenario: Ready to charge creates no coverage
- **WHEN** the only session today is `ready_to_charge` and no confirmed sale exists
- **THEN** no `source_coverage_records` row MUST exist

### Requirement: Cash count coverage does not complete sales
A new current `CashCount` MUST ensure one `cash_count` / `manual_capture` row with `status=observed` and `limitation_code=only_lumo_registered_operations` in that same transaction. A later new `CashCount` for that day MUST reuse that row without changing it. `cash_status` `balanced`, `short`, or `over` MUST NOT change the `sales` row's `status`. A successful close MUST NOT change either row's `status` and MUST NOT insert a `daily_close` domain. In that same close transaction it MUST insert a missing `sales` or `cash_count` row for `manual_capture` when that day's confirmed sale or current CashCount already exists, still at `observed`, and it MUST leave an existing row unchanged.

#### Scenario: Balanced cash does not upgrade sales coverage
- **WHEN** a day already has `sales` coverage `observed` and a new cash count is `balanced`
- **THEN** the `sales` row MUST remain `observed` with `limitation_code=only_lumo_registered_operations`, and exactly one `cash_count` / `manual_capture` row MUST exist at `observed`

#### Scenario: A completed close does not mean every real-world sale was observed
- **WHEN** `closing.confirm@1` completes and the OutcomeRun is `completed`
- **THEN** sales coverage MUST remain `observed`, `merchant` completeness MUST NOT be stored, and no row MUST use status `complete` or `declared_complete`

#### Scenario: The limitation stays on the sales row
- **WHEN** sales coverage is read after a short close
- **THEN** `limitation_code` MUST be `only_lumo_registered_operations`

### Requirement: Recorded operations completeness is a declaration, not a percentage
The system MUST derive Recorded Operations Completeness only from that day's coverage rows. The declaration MUST contain `basis=recorded_operations`, the distinct `domains` present, the distinct `sources` present, `limitation_code=only_lumo_registered_operations`, and `merchant_source_declaration=null`. It MUST NOT be a persisted score, a percentage, or a row. `sale_count`, balanced cash, a successful close, a completed OutcomeRun, and zero open WorkItems MUST NOT set a completeness flag or a non-null merchant declaration. The system MUST NOT infer a missing sale. An empty coverage set MUST still return that limitation and a null merchant declaration.

#### Scenario: Two observed domains are not 100 percent
- **WHEN** a day has `sales` and `cash_count` coverage, both `observed`, and the OutcomeRun is `completed`
- **THEN** the declaration MUST list those domains and `manual_capture`, `merchant_source_declaration` MUST be null, and it MUST NOT contain a percentage or a complete flag

#### Scenario: Nothing observed is not external completeness
- **WHEN** a business date has no coverage row
- **THEN** the declaration MUST have empty domains and sources, the same limitation code, and a null merchant declaration

### Requirement: Coverage writes only on confirmed transitions
Coverage inserts MUST run only inside successful `sale.commit@1`, a new `CashCount` insert, successful `closing.confirm@1`, and the open-today initializer described below. Replay of those parents MUST NOT insert a second row. `closing.prepare@1`, `operational_day.summary@1`, daily sales export, `GET /api/v1/operational-days/current/next-best-action`, `operational_day.next_best_action@1`, and `OutcomeEngine.evaluate` MUST NOT insert or update coverage. There MUST be no coverage HTTP route and no coverage tool. There MUST be no new coverage audit action and no `source_coverage.updated` outbox event.

#### Scenario: Replay does not duplicate coverage
- **WHEN** the actor resubmits the same confirming sale with the same idempotency key and payload hash
- **THEN** exactly one `sales` coverage row MUST exist for that day

#### Scenario: Pure reads do not write coverage
- **WHEN** the actor loads Next Best Action, the day summary, close preparation, or the sales export, or a caller evaluates `daily_close_ready@1`
- **THEN** the coverage row count for that business MUST be unchanged

#### Scenario: Another tenant cannot read coverage
- **WHEN** tenant B queries coverage while tenant A's row exists
- **THEN** tenant B MUST NOT receive tenant A's row

### Requirement: Open today may be initialized from current facts
Migration `0012` MUST NOT insert a coverage row. The existing deploy initializer MUST, for each business's open OperationalDay dated today, ensure `sales` coverage when that day has a confirmed sale and `cash_count` coverage when that day has a current CashCount. It MUST skip closed days and older open days. It MUST NOT insert a business event, MUST NOT write audit, MUST NOT be an HTTP route, and MUST NOT grant `BYPASSRLS`. A second run MUST NOT insert another row.

#### Scenario: Initializer covers open today only
- **WHEN** the initializer runs and open today already has one confirmed sale and one current CashCount, while a closed earlier day has a ClosingSnapshot
- **THEN** open today MUST have `sales` and `cash_count` coverage at `observed`, the closed day MUST gain no coverage row, and no business event MUST be inserted

#### Scenario: Migration inserts nothing
- **WHEN** Alembic upgrades to `0012_source_coverage_event_memory` on a database that already has confirmed sales
- **THEN** `operations.source_coverage_records` MUST exist and MUST contain no row
