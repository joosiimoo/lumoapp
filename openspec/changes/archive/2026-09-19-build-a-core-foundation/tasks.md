## 1. Repository and backend skeleton

- [x] 1.1 Create `backend/` Python 3.12 package layout: `app/{api,agent,application/{commands,queries,workflows},domain/shared,infrastructure,policies,bootstrap}`, plus `migrations/` and `tests/`.
- [x] 1.2 Add backend dependency files (`pyproject.toml` or equivalent) for FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2, Alembic, psycopg, and logging/settings libraries. Do not add Redis, Kafka, or LLM vendor SDKs.
- [x] 1.3 Add a domain import-boundary test that fails if `app.domain` imports FastAPI, SQLAlchemy, Alembic, or LLM SDKs.

## 2. Configuration, Docker, and health

- [x] 2.1 Implement Pydantic settings loaded from environment variables, fail-fast on missing database URL, and reject unknown `APP_ENV` values.
- [x] 2.2 Add Dockerfile for the API image and Compose services `api` and `postgres` only. Do not add a worker service.
- [x] 2.3 Implement `GET /health` (liveness, no DB) and `GET /health/ready` (DB check, 503 when PostgreSQL is down).
- [x] 2.4 Document the local Compose boot command in a short `backend` README without adding product feature docs.

## 3. Persistence conventions

- [x] 3.1 Configure SQLAlchemy 2 engine/session factory in infrastructure only, with UUIDv7, `timestamptz`, and Decimal-only money helpers.
- [x] 3.2 Initialize Alembic and create PostgreSQL schemas `identity`, `audit`, and `platform` only. Do not create `catalog`, `sales`, `operations`, `workflow`, or `memory` schemas.
- [x] 3.3 Add a unit test that rejects `float` as a money value.

## 4. Logging, errors, and API envelope

- [x] 4.1 Add request middleware that reads or generates `X-Correlation-ID`, echoes it, and emits structured JSON logs without tokens, passwords, or full user messages.
- [x] 4.2 Implement the SRS error envelope mapper for `VALIDATION_ERROR`, `FORBIDDEN`, `TENANT_SCOPE_VIOLATION`, `IDEMPOTENCY_CONFLICT`, `DEPENDENCY_UNAVAILABLE`, and `INTERNAL_ERROR`.
- [x] 4.3 Add an API test that invalid JSON yields HTTP 422 with the envelope and a correlation id, and that unhandled exceptions yield HTTP 500 without a stack trace.

## 5. Identity and tenant isolation

- [x] 5.1 Add Alembic migration for `businesses`, `users`, and `memberships` with `business_id`, timestamps, and RLS policies.
- [x] 5.2 Implement `TenantContext` resolution from a signed local/test token; ignore client-supplied `business_id`; refuse the dev token when `APP_ENV=production`.
- [x] 5.3 Implement repositories that require an explicit tenant argument and a session helper that sets `app.current_business_id` for RLS.
- [x] 5.4 Add `GET /api/v1/session` that returns the authenticated actor and business for the session tenant only.
- [x] 5.5 Add an isolation test: actor A cannot read business B resources (`TENANT_SCOPE_VIOLATION` / HTTP 404) and RLS hides cross-tenant rows if the application filter is omitted.
- [x] 5.6 Separate `DATABASE_URL` (`lumo_app` runtime) from `DATABASE_ADMIN_URL` (`lumo_admin` Alembic). Compose provisions both roles; API sessions must not be superuser and must remain subject to RLS.

## 6. Integrity foundation

- [x] 6.1 Add `AuditService` port and infrastructure adapter that writes append-only `audit_events` in the same transaction as the mutation; public APIs must not update or delete audits.
- [x] 6.2 Add `IdempotencyService` port and `idempotency_records` with unique `(business_id, operation_type, key)`, payload hash, and `processing|completed|failed`.
- [x] 6.3 Require `Idempotency-Key` on mutating routes; replay identical key+hash; conflict on same key different hash; serialize concurrent in-flight duplicates.
- [x] 6.4 Add `outbox_events` and an outbox port written in the same transaction. Do not add a worker, poller, or product consumer.
- [x] 6.5 Add a sample tenant-scoped no-op mutation (not sales/catalog/closing) that proves rollback, audit, outbox, and idempotent replay.

## 7. AI-native contracts

- [x] 7.1 Define `LLMProvider` with `interpret`, `compose`, and `health`; ship a fake adapter with no repository or DB access; wire it in bootstrap when no vendor is configured.
- [x] 7.2 Define `AgentDecision` / `AgentResponse` Pydantic schemas and discard invalid provider output before any tool invocation.
- [x] 7.3 Define `LumoOrchestrator` port and a single composition root that cannot open ORM sessions or business transactions directly.
- [x] 7.4 Define `ToolRegistry` with versioned registration metadata and an empty catalog (no `sale.*`, `catalog.*`, `closing.*`, or `export.*`).
- [x] 7.5 Define `PolicyEngine` returning `allow|deny|clarify|confirm` with rule ids and reason codes; register only `SEC-001`, `SEC-002`, and `SEC-003`.
- [x] 7.6 Define `OutcomeEngine` with an empty definition registry that fails closed for unknown outcomes and ignores model claims of completion.
- [x] 7.7 Define backend `GenerativeUIRegistry` and `GenerativeUIComposer` for the versioned contract (`component`, `version`, `data`, `actions`, `fallback_text`). The registry starts empty; the composer refuses unregistered components and does not render UI.
- [x] 7.8 Add tests: unregistered tool is denied; invalid `AgentDecision` causes no persistence; fake provider has no persistence hooks; unknown outcome is not ready; composer refuses unregistered UI components.

## 8. ADRs

- [x] 8.1 Write ADR-002 through ADR-011 as short records under `docs/adr/` (or `backend/adr/`) covering FastAPI, PostgreSQL, Docker, modular monolith, LLM non-mutation, deterministic calc boundary, single orchestrator, generative UI contract, tenancy, and idempotency/outbox.
- [x] 8.2 Write ADR-001 (Flutter client) and ADR-012 (versioned outcomes) as prepared decisions noting that the shell exists and outcome definitions are not registered yet.

## 9. Flutter shell and environments

- [x] 9.1 Create `mobile/` Flutter app with `lib/{app,core,api,lumo,features,shared}` and environment config for `local`, `staging`, and `production` API base URLs.
- [x] 9.2 Implement app bootstrap that loads env at runtime and does not commit secrets.
- [x] 9.3 Add placeholder feature routes for Inicio, Hoy, Memoria, and Negocio inside a 420px `LumoScaffold` canvas `#FCFAF4` with no dark theme.

## 10. Design system tokens and base components

- [x] 10.1 Implement color, gradient, typography, spacing, radius, shadow, and size tokens from `LUMO_DESIGN_SYSTEM_v1.0.md` using documented hex values.
- [x] 10.2 Load Inter 400/500/600/700 and Instrument Serif regular/italic and map the named text styles from the Flutter handoff.
- [x] 10.3 Implement base widgets: scaffold, bottom navigation, composer shell, Lumo mark, assistant message, user bubble, soft card, primary/secondary/text buttons, chips, and toast host. Do not invent search fields, switches, bottom sheets, closing flow, or loading skeletons.
- [x] 10.4 Verify user messages are right-aligned primary bubbles and assistant text is unbubbled with the Lumo mark; motion limited to 150ms color/fill transitions.

## 11. Flutter API client and navigation

- [x] 11.1 Implement a typed API client that attaches `Authorization`, mutation `Idempotency-Key`, and `X-Correlation-ID`, decodes the error envelope, and is the only HTTP access path for views.
- [x] 11.2 Persist and reuse the same idempotency key when retrying a mutation with unknown outcome.
- [x] 11.3 Implement the four-tab bar (Inicio, Hoy, Memoria, Negocio) with accent-pill selected state and muted unselected state; hide tabs on a future onboarding route.
- [x] 11.4 Add a guard or lint/test that feature code does not compute monetary totals or call `Uri` constructors for API paths.
- [x] 11.5 Implement Flutter `GenerativeUIRenderer` that renders backend contracts only, shows `fallback_text` for unknown components/versions/fields/actions, and never executes actions from unknown payloads.

## 12. Cross-stack verification

- [x] 12.1 Export or document the OpenAPI snapshot for health, session, error envelope, and the sample mutation.
- [x] 12.2 Run backend unit/integration tests for health, tenant isolation, idempotency, audit atomicity, and AI contract guards.
- [x] 12.3 Confirm Compose starts with only `api` and `postgres` (no worker, Redis, Kafka, or vector services) and that Flutter local env points at the Compose API.
