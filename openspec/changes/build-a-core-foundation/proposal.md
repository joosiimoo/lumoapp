## Why

Lumo has approved product, software, and architecture contracts for MVP Build A, but the repository contains only documentation. Implementation cannot start with sales, catalog, or closing features until the modular monolith, Flutter shell, tenant isolation, integrity primitives, and AI-native ports exist. This change is Architecture §23 step 1: establish the technical foundation so later Build A changes can add domain logic onto stable boundaries.

## What Changes

- Create a Python 3.12 FastAPI modular monolith with Docker Compose, typed configuration, health endpoints, structured logging, and the public error envelope from SRS §8.5.
- Introduce PostgreSQL as the system of record with SQLAlchemy 2, Alembic, transaction boundaries, and append-only platform tables needed for audit and idempotency.
- Establish multi-tenant isolation with `business_id` and server-derived `TenantContext`.
- Publish contracts only (no product implementations) for `LLMProvider`, `LumoOrchestrator`, `ToolRegistry`, `PolicyEngine`, `OutcomeEngine`, `AuditService`, `IdempotencyService`, backend `GenerativeUIRegistry` / `GenerativeUIComposer`, and Flutter `GenerativeUIRenderer`.
- Scaffold a Flutter application shell with environment configuration, a typed API client, navigation matching the Lumo visual identity, and design-system tokens plus base components from `LUMO_DESIGN_SYSTEM_v1.0.md`.
- Record the ADRs listed in Architecture §21 that this foundation encodes.

## Non-goals

- No sales, catalog, payments, operational-day, closing, consolidations, or export feature logic.
- No real LLM provider integration beyond a non-mutating test/fake adapter behind the port.
- No registered domain tools (`sale.commit`, `catalog.search`, etc.), outcome definitions, or generative widget catalog.
- No inventory, purchasing, replenishment, forecasting, invoicing, banking reconciliation, ecommerce, CRM, or multi-branch.
- No Redis, Kafka, microservices, object storage, or vector database.
- No redesign of Lumo screens, colors, typography, or interaction patterns.
- No production identity-provider selection; auth is a session-to-tenant foundation only.
- No Compose worker process; the outbox table and port exist, but no asynchronous consumer runs until a later change needs one.
- No empty PostgreSQL product schemas (`catalog`, `sales`, `operations`, `workflow`, `memory`).

## Capabilities

### New Capabilities

- `backend-platform`: FastAPI modular monolith, Docker, configuration, health, logging, and error model.
- `persistence`: PostgreSQL, SQLAlchemy 2, Alembic, money/time/ID conventions, and transaction boundaries.
- `tenant-isolation`: Shared-schema multi-tenancy with `business_id` and `TenantContext`.
- `integrity-foundation`: Audit and idempotency contracts, records, and transactional coupling.
- `ai-native-contracts`: Ports for orchestrator, LLM, tools, policy, outcomes, and generative UI.
- `mobile-shell`: Flutter app shell, environment config, API client, and navigation foundation.
- `lumo-design-system`: Tokens and base Flutter components that reproduce the approved visual identity.

### Modified Capabilities

- None. There are no existing OpenSpec specs.

## Impact

- New top-level `backend/` and `mobile/` trees; local Compose for `api` and `postgres` only.
- New public endpoints limited to health plus a stub authenticated ping that proves tenant scoping and the error envelope.
- New platform tables: `businesses`, `users`, `memberships`, `audit_events`, `idempotency_records`, and an internal `outbox_events` table without product consumers.
- Flutter depends on the design-system package/module and a generated-or-hand-typed API client; it must not compute domain totals.
- Downstream Build A changes inherit these ports; they must not bypass them to reach the ORM, LLM SDK, or Flutter widgets directly.
