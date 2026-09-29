## ADDED Requirements

### Requirement: Alembic 0015 onboarding columns
Implementation of this change MUST add revision `0015` after `0014`. The revision MUST add `identity.businesses.onboarding_status` with values `in_progress` and `completed`, defaulting to `completed` only so pre-0015 rows stay completed. Application bootstrap MUST insert `in_progress` explicitly and MUST NOT depend on that default. It MUST add `identity.businesses.enabled_payment_methods` as a nullable text array with no empty-array default. A non-null array MUST have cardinality at least 1 and elements only `cash`, `card`, or `transfer`. NULL MUST remain valid. It MUST allow null `currency` and `timezone` for in-progress rows. It MUST NOT update existing business name, currency, timezone, locale, status, catalog, or sales rows, and MUST leave existing `enabled_payment_methods` NULL. This OpenSpec step MUST NOT add the migration file.

#### Scenario: Legacy row unchanged
- **WHEN** revision `0015` is applied to a database that already contains Carrota
- **THEN** Carrota's name, currency, and timezone MUST be unchanged, `onboarding_status` MUST be `completed`, and `enabled_payment_methods` MUST be NULL

### Requirement: Actor business link
Revision `0015` MUST create `identity.actor_business_links` with `actor_id` as primary key and `business_id UUID NOT NULL`. `business_id` MUST NOT be unique. The table MUST enable and force row level security. The policy MUST allow a row only when `actor_id` equals `current_setting('app.current_actor_id', true)`. The link is bootstrap resolution only. Authorization MUST stay on membership and tenant context.

#### Scenario: Actor id is unique
- **WHEN** a second link is inserted for the same `actor_id`
- **THEN** the database MUST reject the insert

#### Scenario: Business id is not unique on the link
- **WHEN** the schema of `identity.actor_business_links` is inspected
- **THEN** there MUST be no unique constraint on `business_id`
