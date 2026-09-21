## Purpose

Lumo owns a conversational sale as workflow state: a merchant can add catalog items across turns into one `SaleSession`, see accumulated totals from the server, and explicitly totalize to `ready_to_charge` without recording payment.

## Requirements

### Requirement: Multi-item sale stays on one session
Successful add-item messages that share `business_id`, `actor_id`, and `conversation_id` MUST append independent `SaleItem` rows to the same `SaleSession` while that session is `open`. Session totals MUST be the deterministic Decimal sum of persisted `line_total` values. The backend MUST remain the source of truth. `SaleSession` MUST NOT persist a mutable duplicated total column.

#### Scenario: Zanahoria then Tomate
- **WHEN** a Carrota actor posts `900gr zanahoria` and then `500gr tomate` with the same `conversation_id`
- **THEN** exactly one `SaleSession` MUST exist for that context, it MUST contain two `SaleItem`s, `session_item_count` MUST be `2`, and `session_total.amount` MUST be `32.50`

### Requirement: Totalize transitions to ready_to_charge
An explicit totalize intent (`totalizar`, `total`, or `el total`) against an `open` session with at least one `SaleItem` MUST lock that session, calculate the total from persisted items while locked, and atomically transition `open` → `ready_to_charge`. The **transition** MUST persist with audit, outbox event `sale.ready_to_charge`, and message-level idempotency in one application-owned write transaction. Success and `sale_summary@1` MUST be produced only after commit. Totalize MUST NOT record payment, create a `Payment`, or invoke `sale.commit@1`.

`SALE-003` MUST require `open` and ≥1 item **for the transition**. `ready_to_charge` MUST be allowed only as a stable read-back/no-op (see the following requirement), not as a second transition.

#### Scenario: Totalize a multi-item sale
- **WHEN** an open session has Zanahoria `22.50` MXN and Tomate `10.00` MXN and the actor posts `totalizar`
- **THEN** the session status MUST become `ready_to_charge`, the response `ui` MUST include `sale_summary@1` whose `data.total.amount` is `32.50`, and no payment row MUST exist

#### Scenario: Totalize empty or missing sale
- **WHEN** the actor posts `totalizar` with no session or with an open session that has zero items
- **THEN** the system MUST return a resolution-oriented clarification, MUST NOT create a session, MUST NOT change status, and MUST NOT write a successful totalize audit or `sale.ready_to_charge` outbox row

### Requirement: Repeat totalize on ready_to_charge is a stable read-back
When the active session is already `ready_to_charge`, another semantic `totalizar` MUST return the current `sale_summary@1` and MUST NOT transition state, MUST NOT emit another `sale.ready_to_charge` outbox event, and MUST NOT create another transition audit event (`sale.totalize@1` committed). Replaying the original `Idempotency-Key` and payload hash MUST return the original persisted response. A different `Idempotency-Key` MUST be treated as a non-mutating read-back of current state and MUST NOT insert a new `lumo.message.totalize_sale` idempotency record.

#### Scenario: Same-key replay after totalize
- **WHEN** the actor resubmits `totalizar` with the same `Idempotency-Key` and payload hash after a successful transition
- **THEN** the original body MUST be returned, status MUST remain `ready_to_charge`, and a second `sale.ready_to_charge` outbox row MUST NOT exist

#### Scenario: Different-key totalize after ready_to_charge
- **WHEN** the session is `ready_to_charge` and the actor posts `totalizar` with a new `Idempotency-Key`
- **THEN** the response MUST include current `sale_summary@1`, status MUST stay `ready_to_charge`, item rows MUST be unchanged, no second `sale.ready_to_charge` outbox or transition audit MUST be written, and no new `lumo.message.totalize_sale` idempotency row MUST be created for that key

### Requirement: SaleSession mutations serialize on a row lock
For an existing `SaleSession`, both `AddCatalogSaleItem` and `TotalizeSaleSession` MUST take a PostgreSQL row lock (`SELECT ... FOR UPDATE` or SQLAlchemy `with_for_update()`) on that session **before** validating mutable workflow status. After the lock, they MUST re-read status. Add-item MUST insert a `SaleItem` only if the session is still `open`; otherwise it MUST reject. Totalize MUST read the persisted items used for the summary while holding the lock, calculate the Decimal total, and only then transition. No Redis, distributed lock, or new infrastructure MAY be introduced.

#### Scenario: Concurrent add-item vs totalize
- **WHEN** add-item and totalize execute concurrently against the same open `SaleSession`
- **THEN** the operations MUST serialize on the session row, the final state MUST be deterministic (either the item commits before totalize and is included in `sale_summary@1`, or totalize commits first and add-item is rejected), a `SaleItem` MUST NOT persist after `ready_to_charge`, and `sale_summary` total MUST equal the sum of items that committed before the transition

### Requirement: Invalid transitions are rejected
Items MAY be added only while the session is `open`. After `ready_to_charge`, a product utterance MUST be rejected with a resolution-oriented response, MUST NOT persist a new `SaleItem`, MUST NOT create a second session for that conversation, and MUST NOT silently reopen the session. A new `conversation_id` for the same actor and business MUST start a new open session and MUST NOT reuse the previous conversation's `ready_to_charge` session.

#### Scenario: Item after ready_to_charge
- **WHEN** the session is `ready_to_charge` and the actor posts `900gr zanahoria` with the same `conversation_id`
- **THEN** the response MUST deny the add, item count MUST be unchanged, and status MUST remain `ready_to_charge`

#### Scenario: New conversation is isolated
- **WHEN** the previous conversation's session is `ready_to_charge` and the same actor posts `900gr zanahoria` with a different `conversation_id`
- **THEN** a new `open` `SaleSession` MUST be created for the new id and MUST NOT reuse the previous session

### Requirement: Workflow state is explicit and server-owned
Application/domain logic MUST know whether a sale is in progress, its item count and total, and whether it is ready to charge. Flutter and the interpreter MUST NOT own that state. Unknown product, missing unit on a kilogram product, and failed mutations MUST leave the existing session unchanged.

#### Scenario: Unknown product does not damage the sale
- **WHEN** an open session already has items and the actor posts `900gr papa`
- **THEN** no `SaleItem` MUST be written, the existing session MUST remain `open` with its prior items and total, and the response MUST clarify that the product was not found
