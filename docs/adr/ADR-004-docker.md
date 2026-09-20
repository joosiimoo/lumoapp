# ADR-004: Docker as the deployment unit

- Status: Accepted
- Date: 2026-09-19

## Decision

The API is packaged as a Docker image. Local Compose runs `api` and `postgres` only. A worker process is not started until a later change introduces a real asynchronous consumer.

Compose provisions `lumo_admin` and `lumo_app` at first database init. The API container receives both `DATABASE_ADMIN_URL` (Alembic) and `DATABASE_URL` (runtime).
