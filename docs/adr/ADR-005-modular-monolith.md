# ADR-005: Modular monolith for Build A

- Status: Accepted
- Date: 2026-09-19

## Decision

Build A is one deployable FastAPI process with inward-facing modules: `api`, `agent`, `application`, `domain`, `infrastructure`, `policies`, `bootstrap`. Dependencies point toward the domain. Microservices are out of scope.
