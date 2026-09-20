## Context

The repository currently contains only product documentation and an initialized OpenSpec tree. Build A implementation is approved in the PRD, SRS, Technical Architecture, and Design System, but there is no backend, mobile app, or runtime. Architecture §23 step 1 is to establish repository, Docker, configuration, health, PostgreSQL, migrations, tenant, audit, and idempotency before any sales or catalog work.

This change creates that foundation and the AI-native ports required so later changes cannot couple Flutter, FastAPI, the ORM, or an LLM vendor into the domain.

## Goals / Non-Goals

**Goals:**

- Stand up a Python 3.12 FastAPI modular monolith with Compose, typed config, health, structured logs, and the SRS error envelope.
- Make PostgreSQL the system of record with SQLAlchemy 2, Alembic, transaction boundaries, and platform tables.
- Encode multi-tenant isolation with `business_id` and server-derived `TenantContext`.
- Publish contracts for orchestrator, LLM, tools, policy, outcomes, audit, idempotency, and generative UI.
- Scaffold Flutter with env config, API client, four-tab shell, and design-system tokens/base components.
- Resolve directory-structure conflicts between the implementation request and Architecture §5 / §17.

**Non-Goals:**

- Sales, catalog, payments, operational day, closing, consolidations, exports, or real LLM vendor integration.
- Redis, Kafka, microservices, object storage, vector database.
- A Compose worker or any asynchronous outbox consumer.
- Empty PostgreSQL product schemas (`catalog`, `sales`, `operations`, `workflow`, `memory`).
- Production IdP selection, full OIDC flows, or end-user onboarding logic.
- Redesign of Lumo visual identity or new generative cards.

## Decisions

### D1. Authority order

Build A PRD v1.0, SRS v1.0, Technical Architecture v1.0, and Design System v1.0 govern implementation. PRD v0.11 remains the product vision. Where v0.11 Build A omitted catalog and treated Build A as a thinner “Operator Foundation,” Build A v1.0 wins for later feature changes. This foundation change stays inside Architecture §23 step 1 in either reading.

### D2. Backend layout

Use Architecture §17 as the module graph, mapped onto the requested top-level folders:

```text
backend/
  app/
    api/                 # routes, schemas, dependencies
    agent/               # orchestrator, interpretation, providers, GenerativeUIRegistry/Composer
    application/         # commands, queries, workflows
    domain/              # shared kernel now; catalog/sales/operations later
    infrastructure/      # persistence, llm, telemetry
    policies/            # PolicyEngine port and SEC-001..003 only
    bootstrap/           # composition root
  migrations/
  tests/
```

`workflows/` is not a sibling of `application/`. It lives at `application/workflows` so workflow code depends inward on domain and is invoked by the orchestrator, matching Architecture §4 and §17. `policies/` remains a top-level app package because both the request and the architecture place it there.

### D3. Mobile layout

```text
mobile/
  lib/
    app/        # bootstrap, routing, composition
    core/       # env, session, observability
    api/        # typed HTTP client
    lumo/       # design tokens, base components, GenerativeUIRenderer
    features/   # placeholder Inicio, Hoy, Memoria, Negocio
    shared/     # l10n and display formatters only
```

Architecture §5 put `generative_ui/` at `lib/` root. This change places `GenerativeUIRenderer` under `lumo/` so visual identity and rendering live together. Backend `GenerativeUIRegistry` and `GenerativeUIComposer` live under `backend/app/agent/`. Feature folders stay empty of business logic.

### D4. Navigation identity vs Build A surfaces

Design System navigation is Inicio, Hoy, Memoria, Negocio. Build A PRD experience lists Inicio, Hoy, Catálogo, Configuración. Preserve the four-tab visual identity. Catalog and settings will be destinations under Negocio in later changes. Memoria is a placeholder shell now; Event Memory as a product surface is out of scope.

### D5. Runtime processes

Compose runs `api` and `postgres` only. The transactional outbox table and port exist, but this change does not run a worker or poller. A later change that introduces a real asynchronous consumer MAY add a worker, optionally reusing the API image. No Redis or broker.

### D6. Persistence and tenancy

Shared database with PostgreSQL schemas `identity`, `audit`, and `platform` only. Product schemas `catalog`, `sales`, `operations`, `workflow`, and `memory` are created by the OpenSpec changes that own those capabilities. UUIDv7 identifiers, `timestamptz` UTC, `numeric` money. Tenant-scoped tables enable RLS. `TenantContext` is derived from the authenticated principal, never from client-selected `business_id`. FastAPI uses `DATABASE_URL` as role `lumo_app` (non-superuser, no `BYPASSRLS`). Alembic uses `DATABASE_ADMIN_URL` as role `lumo_admin`.

### D7. Auth foundation, not an IdP

Local and test use a signed development token that encodes `user_id` and `business_id`. Production will replace the issuer with OIDC-compatible tokens later (Architecture §14). The session port stays stable.

### D8. Integrity

Mutations require `Idempotency-Key`. Records unique on `(business_id, operation_type, key)`. Audit and outbox rows for a mutation share the business transaction. Success is post-commit only.

### D9. AI-native ports

One orchestrator. `LLMProvider` is a port with a fake adapter. `ToolRegistry` starts empty. Backend generative UI is split: `GenerativeUIRegistry` holds allowed versioned contracts; `GenerativeUIComposer` validates and emits only registered contracts. Flutter `GenerativeUIRenderer` is the only renderer and must show `fallback_text` for unknown components. `PolicyEngine` ships only `SEC-001`, `SEC-002`, `SEC-003`. `OutcomeEngine` has no Build A outcome definitions yet and fails closed.

### D10. ADRs this change establishes

The implementation MUST add short ADR files for Architecture §21 items that the foundation actually encodes: ADR-002 FastAPI/Python, ADR-003 PostgreSQL, ADR-004 Docker, ADR-005 modular monolith, ADR-006 LLM cannot mutate, ADR-007 deterministic calculation boundary, ADR-008 single orchestrator, ADR-009 generative UI contract, ADR-010 shared-schema tenancy, ADR-011 idempotency and transactional outbox. ADR-001 Flutter and ADR-012 versioned outcomes are prepared (Flutter shell exists; outcome definitions are not registered yet).

### D11. Language and package versions

Python 3.12, Pydantic v2, SQLAlchemy 2.x, Alembic, FastAPI. Flutter current stable at implementation time, targeting the two latest major iOS and Android versions as required by RNF-A-016.

## Risks / Trade-offs

- [Empty product registries look unfinished] → That is required; later changes register tools, widgets, and outcomes explicitly.
- [Dev token is not production auth] → Confine it to local/test; fail closed if used when `APP_ENV=production`.
- [RLS plus application filters can be awkward in SQLAlchemy] → Keep a session-scoped `SET app.current_business_id` helper and prove isolation with a negative test.
- [Four-tab shell vs Build A PRD screens] → Documented in D4; do not invent a Catalog tab that the design system does not have.
- [Outbox without a worker] → Persist events transactionally now; add a Compose worker only when a real consumer exists.
- [Fake LLM could be wired into a mutating path] → Composition tests assert the provider has no repository and unregistered tools cannot run.

## Migration Plan

Greenfield. Apply Alembic migrations on empty PostgreSQL. No data backfill. Rollback is `alembic downgrade` plus Compose down. Do not deploy this foundation to a production tenant until a later hardening change.

## Open Questions

1. Production identity provider (Cognito, Auth0, Keycloak, or other OIDC) — deferred.
2. Exact Flutter SDK version pin — choose current stable at apply time.
3. Whether the typed Dart client is hand-written or generated from OpenAPI — default: hand-written foundation client plus OpenAPI export from FastAPI, generation optional later.
