# ADR-003: PostgreSQL as the system of record

- Status: Accepted
- Date: 2026-09-19

## Decision

PostgreSQL stores confirmed application state. SQLAlchemy 2 and Alembic are infrastructure adapters. Domain entities are not ORM models. Money uses `numeric`/`Decimal`. Identifiers are UUIDv7. Timestamps are `timestamptz` UTC.

Alembic connects with `DATABASE_ADMIN_URL` as `lumo_admin`. The API process connects with `DATABASE_URL` as `lumo_app`. The application role is not a superuser and must not bypass RLS.
