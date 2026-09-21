# ADR-015: SaleSession ready_to_charge → confirmed via sale.commit@1

- Status: Accepted
- Date: 2026-09-21

## Decision

A `ready_to_charge` `SaleSession` becomes `confirmed` through `sale.commit@1` with exactly one `Payment`. The confirmed session plus its `SaleItem`s is the durable operational sale. Payment is a separate `sales.payments` row (`method` `cash` | `card` | `transfer`, `status=recorded`, `source=manual_capture`, amount = Decimal sum of locked item totals).

`conversation_id` does not rotate after confirmation. Confirmed sessions are inactive: unique index `uq_sale_sessions_active_context` stays `WHERE status IN ('open', 'ready_to_charge')`. The next product utterance on the same conversation creates a new `open` session. `sale.start@1` output `status` remains `open` | `ready_to_charge` and never returns `confirmed`.

`Payment.business_id` is copied from the trusted `TenantContext` of the locked session. It is never taken from client, interpreter, or tool input. FORCE RLS is defense-in-depth.

## Consequences

Daily Close, OperationalDay, mixed payments, change due, refunds, item edit/remove, catalog CRUD, receipts, and acquirer integrations stay out of scope. Flutter renders `sale_confirmed@1` from server values and does not calculate totals, payment amount, or change.
