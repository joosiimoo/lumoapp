# Lumo backend

Python 3.12 FastAPI modular monolith. PostgreSQL is the system of record.

## Roles

| Role | Purpose |
|---|---|
| `postgres` | Compose bootstrap superuser only. Not used by the API. |
| `lumo_admin` | Owns schemas and runs Alembic. `DATABASE_ADMIN_URL`. |
| `lumo_app` | FastAPI runtime. Non-superuser, no `BYPASSRLS`. `DATABASE_URL`. |

## Local Compose

From the repository root:

```bash
docker compose up --build
```

Services: `api` (http://localhost:8000) and `postgres` (host port 5433). There is no worker.

Example environment (local only — do not reuse in production):

```bash
APP_ENV=local
DATABASE_URL=postgresql+psycopg://lumo_app:lumo_app@localhost:5433/lumo
DATABASE_ADMIN_URL=postgresql+psycopg://lumo_admin:lumo_admin@localhost:5433/lumo
DEV_TOKEN_SECRET=local-dev-secret-do-not-use-in-prod
```

## Health

- `GET /health` — liveness, no database
- `GET /health/ready` — readiness, requires PostgreSQL as `lumo_app`

## Migrations

Compose runs `alembic upgrade head` with `DATABASE_ADMIN_URL` before the API starts. To run them locally:

```bash
cd backend
export APP_ENV=local
export DATABASE_URL=postgresql+psycopg://lumo_app:lumo_app@localhost:5433/lumo
export DATABASE_ADMIN_URL=postgresql+psycopg://lumo_admin:lumo_admin@localhost:5433/lumo
export DEV_TOKEN_SECRET=local-dev-secret-do-not-use-in-prod
alembic upgrade head
```

## Tests

```bash
cd backend
python3.12 -m pytest
```
