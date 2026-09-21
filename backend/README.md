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

Services: `api` (http://localhost:8000) and `postgres` (host port 5432). There is no worker.

Example environment (local only — do not reuse in production):

```bash
APP_ENV=local
DATABASE_URL=postgresql+psycopg://lumo_app:lumo_app@localhost:5432/lumo
DATABASE_ADMIN_URL=postgresql+psycopg://lumo_admin:lumo_admin@localhost:5432/lumo
DEV_TOKEN_SECRET=local-dev-secret-do-not-use-in-prod
```

Catalog and sales tables use FORCE RLS. A SQL client using `lumo_app` or `lumo_admin` must set the tenant before `SELECT`, or the result is empty even when seed rows exist:

```sql
SELECT set_config('app.current_business_id', '01900000-0000-7000-8000-000000000001', false);
SELECT * FROM catalog.products;
```

Local API startup (`APP_ENV=local`) seeds business Carrota and product Zanahoria. Tests call the same helper explicitly. Staging/production never auto-seed.

## Health

- `GET /health` — liveness, no database
- `GET /health/ready` — readiness, requires PostgreSQL as `lumo_app`

## Migrations

Compose runs `alembic upgrade head` with `DATABASE_ADMIN_URL` before the API starts. To run them locally:

```bash
cd backend
export APP_ENV=local
export DATABASE_URL=postgresql+psycopg://lumo_app:lumo_app@localhost:5432/lumo
export DATABASE_ADMIN_URL=postgresql+psycopg://lumo_admin:lumo_admin@localhost:5432/lumo
export DEV_TOKEN_SECRET=local-dev-secret-do-not-use-in-prod
alembic upgrade head
```

## Tests

```bash
cd backend
python3.12 -m pytest
```
