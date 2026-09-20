# ADR-010: Shared-schema multi-tenancy

- Status: Accepted
- Date: 2026-09-19

## Decision

Tenancy uses a shared PostgreSQL database with `business_id` on business entities. `TenantContext` is derived from the authenticated session. Clients cannot select another tenant. Row Level Security is a second barrier and is enforced for the FastAPI runtime role `lumo_app` (non-superuser, no `BYPASSRLS`). Alembic uses `lumo_admin`. Session-scoped `SET LOCAL app.current_business_id` remains the RLS GUC. Cross-tenant access returns `TENANT_SCOPE_VIOLATION` / HTTP 404.
