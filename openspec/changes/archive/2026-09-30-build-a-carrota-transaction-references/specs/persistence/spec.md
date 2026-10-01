## ADDED Requirements

### Requirement: Transaction reference migration and counter table
Alembic migration `0018` MUST add `operations.business_transaction_counters` with `business_id` primary key and `last_value BIGINT NOT NULL DEFAULT 0`, FORCE RLS matching other operations tables, nullable-then-constrained `sale_sessions.transaction_sequence` / `void_transaction_sequence`, and `closing_snapshots.transaction_sequence`. Open/`ready_to_charge` sessions and cash counts MUST NOT receive numbers. Migration MUST NOT modify onboarding tables. Migration MUST NOT rewrite persisted pre-0018 idempotency response bodies.

#### Scenario: Counter table is tenant scoped
- **WHEN** the migration is applied
- **THEN** `operations.business_transaction_counters` MUST exist with RLS enabled and forced

#### Scenario: Historical confirmed sale receives a sequence
- **WHEN** a pre-migration confirmed sale exists for a business
- **THEN** after migration that sale MUST have a non-null `transaction_sequence` unique within the business

#### Scenario: Historical void receives two sequences
- **WHEN** a pre-migration voided sale exists
- **THEN** after migration it MUST have both `transaction_sequence` and a different `void_transaction_sequence`

### Requirement: Migration 0018 exact-fact CHECK and backfill order
Migration `0018` MUST follow this order so new fact keys are never required before historical rows are enriched: (1) add counter/sequence columns in a backfill-compatible state; (2) verify RLS/FORCE RLS on the counter table; (3) drop or replace the previous `business_events` exact-shape CHECK before rewriting historical facts; (4) deterministic entity sequence backfill; (5) rewrite matching historical `sale_confirmed` / `sale_voided` / `daily_close_completed` facts (migration-only Event Memory enrichment); (6) install the new exact-shape CHECK only after facts are migrated; (7) apply final NOT NULL/CHECK constraints that depend on completed backfill; (8) initialize counter `last_value` from the assigned maximum per business. Automated tests MUST exercise this ordering through Alembic base→head.

#### Scenario: Old fact CHECK is dropped before enrichment
- **WHEN** migration rewrites a historical `sale_confirmed` facts object to include `transaction_number`
- **THEN** the previous exact-shape CHECK MUST already have been dropped or replaced so the rewrite is not rejected

#### Scenario: New fact CHECK installs after enrichment
- **WHEN** all historical sale/void/close facts for numbered entities have been enriched
- **THEN** the new exact-shape CHECK MUST be installed and MUST accept those enriched rows

#### Scenario: Base to head preserves ordering safety
- **WHEN** tests apply migrations from base through head against a database that has pre-0018 confirmed sales, voids, closes, and business_events rows
- **THEN** migration MUST complete successfully with backfilled sequences, enriched facts, new CHECKs, initialized counters, and intact RLS/FORCE RLS
