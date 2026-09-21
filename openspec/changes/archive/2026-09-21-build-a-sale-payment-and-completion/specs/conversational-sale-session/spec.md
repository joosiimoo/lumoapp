## MODIFIED Requirements

### Requirement: Invalid transitions are rejected
Items MAY be added only while the session is `open`. After `ready_to_charge` and before `confirmed`, a product utterance MUST be rejected with a resolution-oriented response, MUST NOT persist a new `SaleItem`, MUST NOT create a second session for that conversation, and MUST NOT silently reopen the session. After `confirmed`, a product utterance on the same `conversation_id` MUST start a new `open` session and MUST NOT append to the confirmed sale. A new `conversation_id` for the same actor and business MUST start a new open session and MUST NOT reuse the previous conversation's `ready_to_charge` or `confirmed` session.

#### Scenario: Item after ready_to_charge
- **WHEN** the session is `ready_to_charge` and the actor posts `900gr zanahoria` with the same `conversation_id`
- **THEN** the response MUST deny the add, item count MUST be unchanged, and status MUST remain `ready_to_charge`

#### Scenario: New conversation is isolated
- **WHEN** the previous conversation's session is `ready_to_charge` or `confirmed` and the same actor posts `900gr zanahoria` with a different `conversation_id`
- **THEN** a new `open` `SaleSession` MUST be created for the new id and MUST NOT reuse the previous session

#### Scenario: Next product after confirmed starts a new sale
- **WHEN** the session is `confirmed` and the actor posts `900gr zanahoria` with the same `conversation_id`
- **THEN** a new `open` `SaleSession` MUST be created, Zanahoria MUST be added to that new session, and the previous confirmed session and its `Payment` MUST remain unchanged

### Requirement: SaleSession mutations serialize on a row lock
For an existing `SaleSession`, `AddCatalogSaleItem`, `TotalizeSaleSession`, and `CommitSaleSession` MUST take a PostgreSQL row lock (`SELECT ... FOR UPDATE` or SQLAlchemy `with_for_update()`) on that session **before** validating mutable workflow status. After the lock, they MUST re-read status. Add-item MUST insert a `SaleItem` only if the session is still `open`; otherwise it MUST reject. Add-item MUST decide from **one** locked active-session lookup in its write transaction.

Commit vs add-item ordering is an intentional Build A transaction-boundary rule:

- **CASE A:** add-item locks the `ready_to_charge` row first → deny under `SALE-002`; no item; no new session; do not re-query to start a next sale in that same request.
- **CASE B:** commit confirms and commits first → add-item's later lookup finds no active session and MAY create a new `open` session (Sale B); Sale A stays immutable.

Totalize MUST still read persisted items while holding the lock. No Redis, conversation epochs, distributed locks, or `conversation_id` rotation.

#### Scenario: Concurrent add-item vs totalize
- **WHEN** add-item and totalize execute concurrently against the same open `SaleSession`
- **THEN** the operations MUST serialize on the session row, the final state MUST be deterministic (either the item commits before totalize and is included in `sale_summary@1`, or totalize commits first and add-item is rejected), a `SaleItem` MUST NOT persist after `ready_to_charge`, and `sale_summary` total MUST equal the sum of items that committed before the transition

#### Scenario: CASE A add-item holds ready_to_charge
- **WHEN** add-item's write transaction locks the `ready_to_charge` session before commit does
- **THEN** add-item MUST reject with no `SaleItem` persisted and MUST NOT create another session

#### Scenario: CASE B commit commits first
- **WHEN** commit confirms Sale A and commits before add-item's write transaction looks up the active session
- **THEN** Sale A MUST stay `confirmed` with its original items and Payment, and the racing add-item MAY belong only to a new `open` Sale B

### Requirement: Workflow state is explicit and server-owned
Application/domain logic MUST know whether a sale is being built (`open`), ready to charge (`ready_to_charge`), or completed (`confirmed` with a recorded payment method). Flutter and the interpreter MUST NOT own that state. Unknown product, missing unit on a kilogram product, unrecognized payment method, and failed mutations MUST leave the existing session unchanged.

#### Scenario: Unknown product does not damage the sale
- **WHEN** an open session already has items and the actor posts `900gr papa`
- **THEN** no `SaleItem` MUST be written, the existing session MUST remain `open` with its prior items and total, and the response MUST clarify that the product was not found

## ADDED Requirements

### Requirement: Payment intent confirms a ready_to_charge sale
An explicit payment intent against a `ready_to_charge` session MUST lock that session, persist one `Payment` whose amount equals the current Decimal sale total, transition `ready_to_charge` → `confirmed`, and commit audit, outbox, and message-level idempotency in one application-owned write transaction. Success and `sale_confirmed@1` MUST be produced only after commit. Approved phrases (trim, case-insensitive) MUST be:

- cash: `efectivo`, `pagar en efectivo`, `en efectivo`
- card: `tarjeta`, `pagar con tarjeta`, `con tarjeta`
- transfer: `transferencia`, `pagar por transferencia`, `pagar con transferencia`, `por transferencia`

`pagar`, `cobrar`, mixed-method phrases, and item+payment utterances MUST NOT commit. Commit MUST NOT create an `OperationalDay`, CashCount, WorkItem, or invoice.

#### Scenario: Cash completion
- **WHEN** a conversation has added Zanahoria `22.50`, Tomate `10.00`, and Galleta A `24.00`, posted `totalizar`, then posted `efectivo`
- **THEN** the session MUST be `confirmed`, exactly one `Payment` MUST exist with `method=cash` and `amount=56.50`, and the response `ui` MUST include `sale_confirmed@1`

#### Scenario: Card completion
- **WHEN** a `ready_to_charge` session exists and the actor posts `tarjeta`
- **THEN** the session MUST be `confirmed` and the `Payment.method` MUST be `card`

#### Scenario: Transfer completion
- **WHEN** a `ready_to_charge` session exists and the actor posts `transferencia`
- **THEN** the session MUST be `confirmed` and the `Payment.method` MUST be `transfer`

### Requirement: Repeat commit on confirmed is a stable read-back
When the latest session for the interaction context is `confirmed` and no newer active session exists, another semantic payment intent MUST return the current `sale_confirmed@1` and MUST NOT create a second `Payment`, MUST NOT emit another `sale.confirmed` or `payment.recorded` outbox event, and MUST NOT create another transition audit. Replaying the original `Idempotency-Key` and payload hash MUST return the original persisted response. A different `Idempotency-Key` MUST be treated as a non-mutating read-back and MUST NOT insert a new `lumo.message.commit_sale` idempotency record.

#### Scenario: Same-key replay after commit
- **WHEN** the actor resubmits `efectivo` with the same `Idempotency-Key` and payload hash after a successful transition
- **THEN** the original body MUST be returned, status MUST remain `confirmed`, and a second `Payment` or `sale.confirmed` outbox row MUST NOT exist

#### Scenario: Different-key payment after confirmed
- **WHEN** the session is `confirmed`, no newer active session exists, and the actor posts `efectivo` with a new `Idempotency-Key`
- **THEN** the response MUST include current `sale_confirmed@1`, one `Payment` MUST remain, no second outbox or transition audit MUST be written, and no new `lumo.message.commit_sale` idempotency row MUST be created for that key

### Requirement: Invalid payment intents do not mutate
Payment intent against an `open` session MUST return a resolution-oriented clarification that the sale must be totalized first, MUST NOT persist a `Payment`, and MUST NOT change status. Payment intent with no current sale MUST clarify without mutation. An unrecognized payment phrase MUST clarify the three supported methods without mutation.

#### Scenario: Payment before totalize
- **WHEN** an `open` session has items and the actor posts `efectivo`
- **THEN** the system MUST clarify, status MUST remain `open`, and no `Payment` MUST exist

#### Scenario: Payment with no sale
- **WHEN** no `SaleSession` exists for the interaction context and the actor posts `tarjeta`
- **THEN** the system MUST return a resolution-oriented response and MUST NOT create a session, item, or `Payment`

#### Scenario: Unknown payment method
- **WHEN** the actor posts `cheque` or `pagar` with no method
- **THEN** the system MUST clarify that it can record efectivo, tarjeta, or transferencia, and MUST NOT mutate
