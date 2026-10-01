## MODIFIED Requirements

### Requirement: ClosingSnapshot freezes one accepted close
Persistence MUST create `operations.closing_snapshots` in the existing `operations` schema. A `ClosingSnapshot` MUST include `id` (UUIDv7), `business_id`, `operational_day_id`, `cash_count_id`, `actor_id`, `business_date` (`DATE`), `currency` (`VARCHAR(3)`), `sale_count` (`INTEGER`), `gross_sales_total`, `cash_total`, `card_total`, `transfer_total`, `expected_cash`, `counted_cash`, and `cash_difference` as `numeric(12,2)`, `cash_status` (`VARCHAR(16)`), optional nullable `close_note` (`TEXT` or bounded `VARCHAR`, max length defined by migration, blank stored as null), `transaction_sequence` (`BIGINT NOT NULL`) allocated at successful confirm insert, `closed_at` (`timestamptz`), `created_at`, and `updated_at`. Domain `ClosingSnapshot` MUST NOT be a SQLAlchemy model and MUST NOT import SQLAlchemy, FastAPI, or Flutter. Money MUST be `Decimal` / `numeric` and MUST NEVER be binary float. `actor_id` MUST be the closer copied from `TenantContext`. There MUST NOT be a second `closed_by` column. The table MUST NOT store denominations, evidence ids, source coverage, an outcome id, product rows, a tolerance, an opening float, or a version number. `close_note` MUST be optional merchant context only and MUST NOT participate in money CHECKs or preparation fingerprint calculation. `UNIQUE (operational_day_id)`, `UNIQUE (id, business_id)`, `UNIQUE (cash_count_id)`, and `UNIQUE (business_id, transaction_sequence)` MUST exist. Foreign key `(operational_day_id, business_id)` MUST reference `operations.operational_days (id, business_id)`. Foreign key `(cash_count_id, business_id, operational_day_id)` MUST reference `operations.cash_counts (id, business_id, operational_day_id)`, which requires `UNIQUE (id, business_id, operational_day_id)` named `uq_cash_counts_id_business_day`. Existing `uq_cash_counts_id_business` MUST remain. Schemas `workflow` and `memory` MUST NOT be created. `transaction_sequence` MUST be immutable after insert.

#### Scenario: One snapshot per day
- **WHEN** a close confirmation commits for an open OperationalDay
- **THEN** exactly one `operations.closing_snapshots` row MUST exist for that `operational_day_id`, its `business_id` MUST equal the day's `business_id`, and a second snapshot for that day MUST be rejected

#### Scenario: Snapshot cannot point at another day's count
- **WHEN** an insert sets `cash_count_id` to a `CashCount` whose `operational_day_id` or `business_id` differs from the snapshot
- **THEN** the database MUST reject the row

#### Scenario: Optional close note is stored
- **WHEN** confirm succeeds with a non-empty trimmed `close_note`
- **THEN** the snapshot row MUST store that note and money columns MUST remain internally consistent

#### Scenario: Snapshot stores transaction sequence
- **WHEN** confirm succeeds
- **THEN** the snapshot row MUST store a non-null `transaction_sequence` allocated for that business
