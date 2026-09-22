# ADR-016: Operational day foundation

- Status: Accepted
- Date: 2026-09-21

## Decision

An `OperationalDay` is created lazily inside the confirming `sale.commit@1` transaction, on the first confirmed sale for a business date. Status stays `open`. The runtime membership clock is one injectable UTC reading stored as `sales.sale_sessions.confirmed_at`. `business_date` is that instant in `identity.businesses.timezone` (`zoneinfo` only). The confirmed sale stores `operational_day_id`. Open and `ready_to_charge` sessions stay unattached.

`operational_day.summary@1` is a read. It aggregates confirmed sessions and recorded payments for that day and does not insert a day, audit, outbox, or idempotency row.

Alembic `0005_operational_day` (`down_revision = 0004_confirmed_payment`) backfills already-confirmed sales. `legacy_confirmed_at` is the pre-upgrade `updated_at`. Each distinct `(business_id, business_date)` gets one day whose `created_at` and `updated_at` are the earliest of those timestamps, not the migration clock. Backfill uses ordinary `new_uuid7()` and writes no `operational_day.opened` audit or outbox, no new `sale.commit` audit, no new `sale.confirmed` event, and no idempotency row.

Daily Close stays out of scope.

## Consequences

`operations.operational_days` exists with FORCE RLS. Workflow and memory schemas stay absent. Hoy, cash count, reconciliation, history, and charts are not part of this decision.

`zoneinfo` reads the system IANA database. The Alpine API image installs `tzdata` so a stored business timezone such as `America/Mexico_City` resolves inside the container. The domain does not hardcode that zone.
