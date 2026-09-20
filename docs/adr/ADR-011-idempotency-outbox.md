# ADR-011: Idempotency and transactional outbox

- Status: Accepted
- Date: 2026-09-19

## Decision

Mutations require `Idempotency-Key`, scoped by `business_id + operation_type + key`. Replay returns the original result; a different payload is `IDEMPOTENCY_CONFLICT`. Audit and outbox rows share the business transaction. No worker or broker is deployed in this change.
