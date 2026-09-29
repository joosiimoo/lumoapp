## ADDED Requirements

### Requirement: Trusted business bootstrap does not weaken tenant RLS
Creating the first business MUST generate `business_id` on the server as UUIDv7. The client request MUST NOT include it. The transaction MUST `SET LOCAL app.current_business_id` to that generated id, then insert the business, user, owner membership, and actor link, and MUST roll back every one of those writes on failure. A concurrent second insert for the same `actor_id` MUST fail on the primary key and MUST leave no orphan business, user, or membership. Merchant policies on existing tenant tables MUST stay unchanged. After creation, reads and writes MUST use the normal session `TenantContext`. `actor_business_links.business_id` MUST NOT be unique. Authorization MUST remain membership and tenant context. An actor MUST NOT read another actor's link or another business's onboarding fields.

#### Scenario: Tenant B cannot read tenant A configuration
- **WHEN** an authenticated session for business B queries business A's onboarding fields
- **THEN** the API MUST return HTTP 404 with `error.code` equal to `TENANT_SCOPE_VIOLATION` or an empty RLS result with no business A payload

#### Scenario: Pre-tenant token cannot call sales
- **WHEN** a token without `business_id` calls a sale or daily-close route
- **THEN** the server MUST reject the request and MUST NOT run the sale tool
