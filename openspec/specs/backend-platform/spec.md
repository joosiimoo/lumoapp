## Purpose

Foundation runtime for the Lumo FastAPI modular monolith: layout, typed config, health, logging, public errors, and Compose (`api` + `postgres` only).

## Requirements

### Requirement: Modular monolith layout
The backend MUST be a single deployable FastAPI application whose source tree separates `api`, `agent`, `application`, `domain`, `infrastructure`, `policies`, and `bootstrap`. Domain code MUST NOT import FastAPI, SQLAlchemy, Alembic, LLM SDKs, or Flutter types. Application and agent code MUST NOT import SQLAlchemy models or the database session factory.

#### Scenario: Domain import boundary
- **WHEN** a static or test check scans `backend/app/domain`
- **THEN** it MUST report zero imports of FastAPI, SQLAlchemy, Alembic, or LLM provider SDKs

#### Scenario: Composition root
- **WHEN** the process starts
- **THEN** adapters and ports MUST be wired only in `backend/app/bootstrap`

### Requirement: Typed runtime configuration
The system MUST load configuration from environment variables into a validated Pydantic settings object. Startup MUST fail if a required value is missing or invalid. Secrets MUST NOT be committed to the repository or baked into images.

#### Scenario: Missing database URL
- **WHEN** the API starts without a valid `DATABASE_URL` or `DATABASE_ADMIN_URL`
- **THEN** the process MUST exit before serving traffic

#### Scenario: Environment profiles
- **WHEN** `APP_ENV` is `local`, `test`, `staging`, or `production`
- **THEN** the settings object MUST expose that environment and refuse unknown values

### Requirement: Health endpoints
The system MUST expose a liveness endpoint that does not touch PostgreSQL and a readiness endpoint that verifies the database connection.

#### Scenario: Liveness
- **WHEN** a client calls `GET /health`
- **THEN** the response MUST be HTTP 200 with a JSON body that includes `status: "ok"`

#### Scenario: Readiness success
- **WHEN** PostgreSQL is reachable and a client calls `GET /health/ready`
- **THEN** the response MUST be HTTP 200 and include database readiness as true

#### Scenario: Readiness failure
- **WHEN** PostgreSQL is unreachable and a client calls `GET /health/ready`
- **THEN** the response MUST be HTTP 503 and MUST NOT claim the service is ready

### Requirement: Structured logging and correlation
Every request MUST receive or generate an `X-Correlation-ID`, return it on the response, and emit structured JSON logs containing timestamp, severity, service, environment, correlation_id, request_id, route, duration_ms, and outcome. Logs MUST NOT include access tokens, passwords, or full user messages.

#### Scenario: Correlation propagation
- **WHEN** a client sends `X-Correlation-ID: abc`
- **THEN** the response MUST echo that value and logs for the request MUST include `correlation_id=abc`

#### Scenario: Generated correlation id
- **WHEN** a client omits `X-Correlation-ID`
- **THEN** the server MUST generate an opaque id, return it, and include it in logs

### Requirement: Public error envelope
Unhandled and mapped application errors MUST be returned as JSON UTF-8 with the SRS §8.5 envelope: `error.code`, `error.message`, `error.details`, `error.retryable`, and `error.correlation_id`. Codes used in this foundation MUST include `VALIDATION_ERROR`, `FORBIDDEN`, `TENANT_SCOPE_VIOLATION`, `IDEMPOTENCY_CONFLICT`, `DEPENDENCY_UNAVAILABLE`, and `INTERNAL_ERROR`.

#### Scenario: Validation error shape
- **WHEN** a client submits an invalid JSON payload to a versioned API route
- **THEN** the response MUST be HTTP 422 with `error.code` equal to `VALIDATION_ERROR` and a correlation id

#### Scenario: Internal error does not leak internals
- **WHEN** an unhandled exception occurs
- **THEN** the client MUST receive HTTP 500 with `error.code` equal to `INTERNAL_ERROR` and MUST NOT receive a stack trace

### Requirement: Docker modular monolith
Local development MUST run via Docker Compose with `api` and `postgres` only. The Compose file MUST NOT introduce a worker process, Redis, Kafka, a vector database, or additional application services. A worker MAY be added by a later change when a real asynchronous consumer exists.

#### Scenario: Local compose up
- **WHEN** an operator runs the documented Compose command
- **THEN** the API health endpoint MUST become reachable against the composed PostgreSQL instance

#### Scenario: Forbidden infrastructure absent
- **WHEN** the Compose configuration is inspected
- **THEN** it MUST NOT define a worker, Redis, Kafka, or a vector database service
