## Purpose

Audit, idempotency, and transactional outbox contracts for foundation mutations. No worker, poller, or external broker.

## Requirements

### Requirement: AuditService contract
The system MUST expose an `AuditService` port that records append-only `AuditEvent` entries with business_id, actor, action, tool or route, policy decision when present, before/after payload allowed by policy, result, correlation id, idempotency key when present, and timestamp. Critical mutation audits MUST be written in the same transaction as the effect. Build A APIs MUST NOT offer deletion of audit events.

#### Scenario: Audit in same transaction
- **WHEN** a tenant-scoped mutation commits
- **THEN** an `AuditEvent` for that mutation MUST be visible in the same committed state

#### Scenario: Audit is append-only
- **WHEN** a client attempts to delete or update an audit event through a public API
- **THEN** the system MUST reject the request

### Requirement: IdempotencyService contract
Every public mutating endpoint MUST require an `Idempotency-Key` header. The `IdempotencyService` MUST scope keys by `business_id + operation_type + key`, store a normalized request hash, and track state `processing`, `completed`, or `failed`.

#### Scenario: Missing key
- **WHEN** a client calls a mutating endpoint without `Idempotency-Key`
- **THEN** the response MUST be HTTP 422 with `error.code` equal to `VALIDATION_ERROR`

#### Scenario: Replay of identical request
- **WHEN** the same tenant resubmits a completed mutation with the same key and the same payload hash
- **THEN** the system MUST return the original status and body and MUST NOT create a second effect

#### Scenario: Same key different payload
- **WHEN** the same tenant resubmits a key with a different payload hash
- **THEN** the response MUST be HTTP 409 with `error.code` equal to `IDEMPOTENCY_CONFLICT`

#### Scenario: Concurrent duplicate in-flight
- **WHEN** two concurrent requests share the same tenant, operation type, and key
- **THEN** one request MUST execute and the other MUST receive the persisted result without a second effect

### Requirement: Failed operations remain retryable
A mutation that fails before commit MUST leave idempotency state as failed or absent such that a later retry with the same key and payload can execute. Partial domain writes MUST NOT remain.

#### Scenario: Retry after failure
- **WHEN** the first attempt with a key fails and rolls back, and a second attempt uses the same key and payload
- **THEN** the second attempt MUST be allowed to execute exactly once successfully

### Requirement: Transactional outbox table
The system MUST persist `outbox_events` in the same transaction as the originating mutation and MUST expose an outbox port/abstraction for later consumers. This change MUST NOT introduce an external broker and MUST NOT run a worker or poller.

#### Scenario: Outbox row with mutation
- **WHEN** a foundation mutation that emits an event commits
- **THEN** the corresponding `outbox_events` row MUST be committed atomically with the mutation

#### Scenario: No asynchronous consumer yet
- **WHEN** the deployment configuration is inspected
- **THEN** it MUST NOT require Kafka, another external event bus, or a Compose worker to start
