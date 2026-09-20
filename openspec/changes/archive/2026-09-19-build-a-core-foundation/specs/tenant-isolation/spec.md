## ADDED Requirements

### Requirement: Tenant context from session
Every authenticated request MUST resolve a `TenantContext` containing `business_id` and `actor_id` from the server-side session or token. The client MUST NOT be allowed to select or override `business_id`.

#### Scenario: Derived tenant
- **WHEN** a valid authenticated request reaches a tenant-scoped route
- **THEN** the resolved `TenantContext.business_id` MUST equal the business bound to the session

#### Scenario: Client-supplied tenant ignored
- **WHEN** a client sends a body or header attempting to set another `business_id`
- **THEN** the server MUST ignore that value and continue using the session tenant, or reject the request as a validation error

### Requirement: business_id on business entities
Every persisted business entity, including `businesses` children, audit events, and idempotency records, MUST include `business_id`. Repositories and queries that read or write tenant data MUST require an explicit tenant argument.

#### Scenario: Repository without tenant
- **WHEN** application code calls a tenant-scoped repository method without a tenant
- **THEN** the call MUST fail before executing SQL

#### Scenario: Insert includes tenant
- **WHEN** a membership row is inserted
- **THEN** it MUST contain the same `business_id` as its parent business

### Requirement: Cross-tenant isolation
Reads and writes for a resource belonging to another business MUST fail without leaking existence. The public error MUST use `TENANT_SCOPE_VIOLATION` and HTTP 404. PostgreSQL Row Level Security MUST be enabled on tenant-scoped tables as a second barrier.

#### Scenario: Cross-tenant read
- **WHEN** an authenticated actor for business A requests a resource id that exists only in business B
- **THEN** the API MUST return HTTP 404 with `error.code` equal to `TENANT_SCOPE_VIOLATION`

#### Scenario: RLS denies even if application filter is bypassed
- **WHEN** a test session is configured for business A and a query omits `business_id` against a tenant-scoped table containing business B rows
- **THEN** PostgreSQL MUST return no business B rows

### Requirement: Runtime database role is subject to RLS
The FastAPI process MUST connect as PostgreSQL role `lumo_app`. That role MUST NOT be a superuser and MUST NOT have `BYPASSRLS`, `CREATEDB`, or `CREATEROLE`. Schema ownership and migrations MUST use `lumo_admin` via `DATABASE_ADMIN_URL`.

#### Scenario: API sessions run as lumo_app
- **WHEN** the API opens a database session
- **THEN** `current_user` MUST be `lumo_app` and `rolsuper` / `rolbypassrls` MUST be false

#### Scenario: Application role cannot bypass RLS
- **WHEN** an API-role session is configured for business A and a query omits `business_id` against a tenant-scoped table containing business B rows
- **THEN** PostgreSQL MUST return no business B rows without switching roles
