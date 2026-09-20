# ADR-006: The LLM cannot mutate domain state

- Status: Accepted
- Date: 2026-09-19

## Decision

`LLMProvider` is a port with a fake adapter. It has no database session, repository, or credentials. Interpretation output is schema-validated. Unregistered tools cannot run. Policy `SEC-001` forbids LLM mutation.
