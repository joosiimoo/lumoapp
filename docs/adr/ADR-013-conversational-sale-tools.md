# ADR-013: Conversational sale tools as the first registered catalog

- Status: Accepted
- Date: 2026-09-20

## Decision

The first product tool catalog is the conversational add-item slice: `catalog.resolve_product@1`, `sale.start@1`, and `sale.add_item@1`. `sale.commit@1` stays unregistered. Tools are not public HTTP resources; `POST /api/v1/lumo/messages` is the only conversational entry. The scripted interpreter may interpret only. Product resolution is a read that happens before the write transaction. Start/reuse, add-item, audit, outbox, and message-level idempotency (`lumo.message.add_sale_item`) commit in one application-owned Unit of Work. The orchestrator does not open ORM sessions. Flutter renders `sale_item_added@1` from server strings and does not calculate quantity or money.

## Consequences

Payment, sale confirmation, operational day, closing, cash count, history, export, overrides, discounts, inventory, purchasing, multi-product interpretation, unknown-product sales, voice, camera, and a vendor LLM remain out of scope for later changes.
