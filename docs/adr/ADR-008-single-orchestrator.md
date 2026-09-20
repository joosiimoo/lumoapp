# ADR-008: Single Lumo Orchestrator in Build A

- Status: Accepted
- Date: 2026-09-19

## Decision

Build A has one `LumoOrchestrator` composition root. It may interpret, select registered tools, ask the policy engine, and compose a response. It must not open ORM sessions or business transactions.
