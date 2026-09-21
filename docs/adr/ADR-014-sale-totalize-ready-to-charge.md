# ADR-014: SaleSession open → ready_to_charge via sale.totalize@1

- Status: Accepted
- Date: 2026-09-21

## Decision

`SaleSession` may be `open` or `ready_to_charge`. An explicit totalize (`sale.totalize@1`, conversational synonyms `totalizar` / `total` / `el total`) is the only transition from `open` to `ready_to_charge`. That transition requires at least one persisted `SaleItem`, serializes on `SELECT ... FOR UPDATE` of the session row, and commits status, `sale.totalize@1` audit, `sale.ready_to_charge` outbox, and `lumo.message.totalize_sale` idempotency in one application-owned Unit of Work.

`sale.commit@1` remains unregistered. It is reserved for later payment and financial confirmation. `ready_to_charge` is not PRD `confirmed` and does not record money movement.

Repeat totalize on `ready_to_charge` is a stable read-back of the current `sale_summary@1`. The original idempotency key replays the persisted body. A different key does not insert a second idempotency, transition audit, or outbox row.

## Consequences

Add-item is rejected after totalize; a new `conversation_id` starts a new open session. Payment, cancel, reopen, item edit/remove, Daily Close, and inventory stay out of scope. Flutter renders `sale_summary@1` from server values and does not calculate totals.
