# ADR-007: Deterministic calculation stays on the server

- Status: Accepted
- Date: 2026-09-19

## Decision

Monetary and domain calculations are server-side and use exact decimals. Flutter may format server-provided amounts for display and must not recompute totals, conversions, expected cash, or outcome gates.
