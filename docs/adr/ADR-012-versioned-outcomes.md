# ADR-012: Versioned outcome definitions

- Status: Prepared
- Date: 2026-09-19

## Decision

`OutcomeEngine` is a port with an empty definition registry. Unknown outcomes fail closed. Model text cannot mark an outcome ready. Build A outcome definitions (`daily_sales_operations_ready@1`, `daily_close_ready@1`) will be registered in a later change.
