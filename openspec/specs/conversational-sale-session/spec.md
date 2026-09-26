## Purpose

Lumo owns a conversational sale as workflow state: a merchant can add catalog items across turns into one `SaleSession`, see accumulated totals from the server, totalize to `ready_to_charge`, and record one closed-enum payment to `confirmed`. `confirmed` is operational completion, not Daily Close.
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

### Requirement: Workflow state is explicit and server-owned
Application/domain logic MUST know whether a sale is being built (`open`), ready to charge (`ready_to_charge`), or completed (`confirmed` with a recorded payment method). Flutter and the interpreter MUST NOT own that state. Unknown product, missing unit on a kilogram product, unrecognized payment method, and failed mutations MUST leave the existing session unchanged.

#### Scenario: Unknown product does not damage the sale
- **WHEN** an open session already has items and the actor posts `900gr papa`
- **THEN** no `SaleItem` MUST be written, the existing session MUST remain `open` with its prior items and total, and the response MUST clarify that the product was not found

### Requirement: Payment intent confirms a ready_to_charge sale
An explicit payment intent against a `ready_to_charge` session MUST lock that session, persist one `Payment` whose amount equals the current Decimal sale total, transition `ready_to_charge` → `confirmed`, and commit audit, outbox, and message-level idempotency in one application-owned write transaction. Success and `sale_confirmed@1` MUST be produced only after commit. Approved phrases (trim, case-insensitive) MUST be:

- cash: `efectivo`, `pagar en efectivo`, `en efectivo`
- card: `tarjeta`, `pagar con tarjeta`, `con tarjeta`
- transfer: `transferencia`, `pagar por transferencia`, `pagar con transferencia`, `por transferencia`

The actions `sale.pay.cash@1`, `sale.pay.card@1`, and `sale.pay.transfer@1` MUST be the same commit, with the method taken from the action id, and only for the `sale_session_id` inside that action's signed token. They MUST NOT be a second payment implementation. A typed phrase MUST NOT require that token.

`pagar`, `cobrar`, mixed-method phrases, and item+payment utterances MUST NOT commit.

Commit MUST ensure and attach the `OperationalDay` for the confirmation's business date exactly as `operational-day-foundation` requires: the same transaction MUST resolve or lazily create the one open day for that date and MUST set the confirmed session's `operational_day_id`. This supersedes the earlier statement that commit MUST NOT create an `OperationalDay`, which contradicted the implemented baseline.

Commit MUST NOT create a `CashCount` or an invoice, MUST NOT perform a final Daily Close, MUST NOT change `OperationalDay.status`, and MUST NOT compute or persist counted cash or a cash difference. The same transaction MUST ensure the `daily_close_ready@1` OutcomeRun and then run Daily Close WorkItem sync after the day and payment exist, as `daily-close-outcome` and `work-item-foundation` require. When that day has no current `CashCount`, the OutcomeRun MUST be `in_progress` with `reason_code=awaiting_cash_count` and sync MUST leave one open `cash_count_required` row whose `outcome_run_id` is that run. Cash counting is owned by `cash-count-foundation` and requires a separate explicit write. Idempotent replay and a confirmed read-back MUST NOT run sync again and MUST NOT insert a second OutcomeRun.

#### Scenario: Cash completion
- **WHEN** a conversation has added Zanahoria `22.50`, Tomate `10.00`, and Galleta A `24.00`, posted `totalizar`, then posted `efectivo`
- **THEN** the session MUST be `confirmed`, exactly one `Payment` MUST exist with `method=cash` and `amount=56.50`, and the response `ui` MUST include `sale_confirmed@1`

#### Scenario: Card completion
- **WHEN** a `ready_to_charge` session exists and the actor posts `tarjeta`
- **THEN** the session MUST be `confirmed` and the `Payment.method` MUST be `card`

#### Scenario: Transfer completion
- **WHEN** a `ready_to_charge` session exists and the actor posts `transferencia`
- **THEN** the session MUST be `confirmed` and the `Payment.method` MUST be `transfer`

#### Scenario: Cash tap completion
- **WHEN** a `ready_to_charge` session exists and the actor submits `sale.pay.cash@1` whose token `sale_session_id` is that session
- **THEN** that session MUST be `confirmed`, exactly one `Payment` MUST exist with `method=cash`, and the response `ui` MUST include `sale_confirmed@1` with empty `actions`

#### Scenario: Commit attaches the operational day
- **WHEN** the first sale of the business date is confirmed
- **THEN** exactly one open `operations.operational_days` row MUST exist for that business and date and the confirmed session's `operational_day_id` MUST reference it

#### Scenario: Commit does not count cash or close
- **WHEN** a sale is confirmed with `efectivo` or with `sale.pay.cash@1` and no `CashCount` exists
- **THEN** `operations.cash_counts` MUST NOT gain a row, no invoice MUST be created, no Daily Close MUST be performed, the day's `status` MUST remain `open`, exactly one OutcomeRun MUST be `in_progress` with `reason_code=awaiting_cash_count`, and exactly one open `cash_count_required` WorkItem MUST exist for that day

#### Scenario: First confirmed sale opens one outcome
- **WHEN** the first sale of the business date is confirmed and no CashCount exists
- **THEN** exactly one OutcomeRun MUST exist for that operational day and a second confirmed sale on that day MUST NOT insert another

### Requirement: Repeat commit on confirmed is a stable read-back
When the latest session for the interaction context is `confirmed` and no newer active session exists, another semantic payment intent, including a payment action, MUST return the current `sale_confirmed@1` and MUST NOT create a second `Payment`, MUST NOT emit another `sale.confirmed` or `payment.recorded` outbox event, MUST NOT create another transition audit, and MUST NOT insert or update an OutcomeRun. Replaying the original `Idempotency-Key` and payload hash MUST return the original persisted response. A different `Idempotency-Key` MUST be treated as a non-mutating read-back and MUST NOT insert a new `lumo.message.commit_sale` idempotency record.

#### Scenario: Same-key replay after commit
- **WHEN** the actor resubmits `efectivo` with the same `Idempotency-Key` and payload hash after a successful transition
- **THEN** the original body MUST be returned, status MUST remain `confirmed`, and a second `Payment`, `sale.confirmed` outbox row, or OutcomeRun MUST NOT exist

#### Scenario: Different-key payment after confirmed
- **WHEN** the session is `confirmed`, no newer active session exists, and the actor posts `efectivo` with a new `Idempotency-Key`
- **THEN** the response MUST include current `sale_confirmed@1`, one `Payment` MUST remain, no second outbox or transition audit MUST be written, no OutcomeRun MUST be inserted or updated, and no new `lumo.message.commit_sale` idempotency row MUST be created for that key

#### Scenario: Stale payment action does not double-charge
- **WHEN** the token-bound session is already `confirmed`, no newer active session exists, and `sale.pay.card@1` is submitted with a new idempotency key
- **THEN** one `Payment` MUST remain and the response MUST be that session's `sale_confirmed@1`

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

### Requirement: Commit on a closed day does not confirm the sale
When `sale.commit@1` finds today's OperationalDay `closed`, it MUST follow the refusal in `operational-day-foundation`. The payment phrases MUST NOT reopen the day, MUST NOT create a second day for that `business_date`, and MUST NOT leave the session `confirmed`.

#### Scenario: Efectivo after close
- **WHEN** today's OperationalDay is `closed` and a `ready_to_charge` session posts `efectivo`
- **THEN** the session MUST stay `ready_to_charge`, no `Payment` MUST exist for that attempt, and `OperationalDay.status` MUST stay `closed`

### Requirement: A payment action cannot move to a later sale
A payment action MUST confirm only the session named by its token. A completed same key and hash MUST return the stored body before any newer-session comparison. When that session is already `confirmed` and no newer `open` or `ready_to_charge` session exists, a fresh key MUST return that session's `sale_confirmed@1` without a new payment, audit, outbox, or idempotency row. When a newer `open` or `ready_to_charge` session exists, a fresh key MUST return reason `ui_action_stale`, text `Esta acción ya no aplica a la venta en curso.`, and empty `ui`, and MUST NOT compose the bound session's `sale_confirmed@1` or confirm the newer session. Flutter disabled controls MUST NOT be required for this outcome.

#### Scenario: Unused Sale A button is stale while Sale B is active
- **WHEN** session A was confirmed by typing `efectivo`, session B is `ready_to_charge` in the same conversation, and the unused payment token bound to A is submitted
- **THEN** the response MUST be `ui_action_stale` with empty `ui`, session A MUST keep exactly one `Payment`, session B MUST remain `ready_to_charge` with no `Payment`, and no audit, outbox, or idempotency row MUST be written

#### Scenario: Same-key replay stays on Sale A
- **WHEN** a completed `sale.pay.cash@1` key for session A is repeated after session B is `ready_to_charge`
- **THEN** the stored session A response MUST be returned and session B MUST gain no `Payment`

#### Scenario: Confirmed read-back when the conversation has no newer sale
- **WHEN** the token-bound session is `confirmed`, the conversation has no newer `open` or `ready_to_charge` session, and a fresh payment action key is submitted
- **THEN** the response MUST include that session's `sale_confirmed@1` and MUST NOT create a second `Payment`

### Requirement: Mixed catalog and free-concept lines
An `open` `SaleSession` MUST accept catalog lines and free-concept lines together. Totalize MUST include every persisted line. A later confirmation MUST keep both. The session status machine MUST stay `open`, `ready_to_charge`, and `confirmed`.

#### Scenario: Second line joins the open session
- **WHEN** an open session already contains Zanahoria and the actor adds a free-concept line on the same `conversation_id`
- **THEN** both items MUST belong to that same session and the session MUST stay `open`

### Requirement: Free-concept clarification does not duplicate
A price or quantity clarification that completes a free concept MUST insert one `SaleItem`. It MUST NOT insert one item for the incomplete turn and another for the completing turn.

#### Scenario: One line after the price
- **WHEN** the actor clarifies the price of a pending free concept
- **THEN** the session MUST contain exactly one new line for that concept

### Requirement: Post-close commit guard is unchanged
A free-concept line MAY be added on a new `open` session after the operational day is `closed`, because add-item does not consult the day. `sale.commit@1` MUST still refuse to confirm that session into the closed day and MUST NOT insert an OutcomeRun for that refusal.

#### Scenario: Commit after close refuses
- **WHEN** the day is `closed` and a `ready_to_charge` session contains a free-concept line
- **THEN** commit MUST NOT record a `Payment`, MUST NOT set the session to `confirmed`, and MUST NOT insert an OutcomeRun

### Requirement: Override reason completes one session line
A catalog price-override reason that `catalog-price-override` allows to commit MUST insert one `SaleItem` on the open session for that interaction context, creating the session when none exists. It MUST NOT insert a line on the question turn and another on the reason turn. `sale.totalize@1` and `sale.commit@1` MUST keep their current session rules and MUST sum persisted `line_total` values. Cash, card, and transfer MUST confirm that session without a pricing branch. Commit into a closed operational day MUST still refuse.

#### Scenario: Reason then totalize
- **WHEN** a Carrota actor completes the Tomate override at `27.00` and then posts `totalizar`
- **THEN** the open session MUST contain that one Tomate line and the summary total MUST include `27.00`

#### Scenario: Question turn leaves no session
- **WHEN** no session exists and the actor posts `900gr tomate a 30`
- **THEN** no `SaleSession` MUST exist after that turn

### Requirement: A new sale replaces a pending override
If `catalog_price_override` is pending and the actor sends a complete sale utterance, that pending MUST be cleared and the new utterance MUST follow normal add-item rules. The pending text MUST NOT be stored as `price_override_reason`.

#### Scenario: Galleta replaces a pending Tomate override
- **WHEN** a Tomate override question is pending and the actor posts `2 galletas A`
- **THEN** no Tomate override line MUST exist and the Galleta utterance MUST be interpreted on its own

### Requirement: Existing close and payment behavior stays in force
A confirming commit MUST still record exactly one `Payment` with `status=recorded`. It MUST NOT leave a confirmed sale without a payment. `ready_to_charge` MUST remain unattached to an OperationalDay and MUST NOT create an OutcomeRun. This requirement does not add `payment_required`.

#### Scenario: Ready to charge stays off the day
- **WHEN** a session is `ready_to_charge` and no confirmed sale exists for today
- **THEN** its `operational_day_id` MUST be NULL, no Daily Close WorkItem MUST reference that session, and no OutcomeRun MUST exist

### Requirement: A confirming commit records sales coverage and sale memory
Successful `sale.commit@1` MUST, in the same transaction, after the payment, the OperationalDay, the OutcomeRun ensure, and WorkItem sync, and before parent idempotency completes, ensure the `sales` / `manual_capture` coverage row and insert one `sale_confirmed` business event, as `source-coverage` and `factual-event-memory` require. A typed payment phrase and `sale.pay.cash@1`, `sale.pay.card@1`, or `sale.pay.transfer@1` MUST share that coverage identity. The commit MUST NOT create `cash_count` coverage. `ready_to_charge`, totalize, clarify, a closed-day refusal, idempotent replay, and a confirmed read-back MUST NOT insert coverage or a business event. Existing sale confirmation text MUST stay unchanged.

#### Scenario: First confirming phrase writes coverage and one event
- **WHEN** a `ready_to_charge` session is confirmed with `efectivo`
- **THEN** the session MUST be `confirmed`, one `sales` coverage row MUST exist at `observed`, and one `sale_confirmed` event MUST exist for that session

#### Scenario: A payment tap uses the same sales source
- **WHEN** a `ready_to_charge` session is confirmed with `sale.pay.card@1`
- **THEN** coverage `source_type` MUST be `manual_capture` and the event `facts.payment_method` MUST be `card`

#### Scenario: Ready to charge writes neither row
- **WHEN** the actor posts `totalizar` and does not confirm payment
- **THEN** no coverage row and no business event MUST exist

#### Scenario: Commit replay writes neither row again
- **WHEN** the actor resubmits the same payment with the same idempotency key and payload hash
- **THEN** a second coverage row and a second `sale_confirmed` event MUST NOT exist
