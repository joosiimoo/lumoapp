## ADDED Requirements

### Requirement: Sale corrections migration extends sale_sessions
A new Alembic revision after the current head MUST widen `ck_sale_sessions_status` to allow `voided`, adjust the day-membership check so `voided` requires non-null `operational_day_id` and `confirmed_at`, add nullable `voided_at`, `voided_by_actor_id`, and `void_reason` with a CHECK that voided rows have complete metadata and non-voided rows keep those columns NULL, and add `sale_revision INTEGER NOT NULL` with default `1`, `CHECK (sale_revision >= 1)`, and backfill of existing rows to `1`. The migration MUST NOT backfill void metadata, MUST NOT grant `BYPASSRLS`, and MUST keep FORCE RLS on `sales` tables.

#### Scenario: Voided status is accepted
- **WHEN** the corrections migration is applied
- **THEN** inserting a `sale_sessions` row with `status=voided` and complete void metadata plus day membership MUST succeed, and `status=voided` without reason MUST fail

#### Scenario: sale_revision column exists
- **WHEN** the corrections migration is applied
- **THEN** every `sale_sessions` row MUST have non-null `sale_revision >= 1`, new inserts without an explicit revision MUST default to `1`, and a write with `sale_revision = 0` MUST fail the check

#### Scenario: Active unique index unchanged
- **WHEN** the corrections migration is applied
- **THEN** the active-session unique index predicate MUST still be only `open` and `ready_to_charge`
