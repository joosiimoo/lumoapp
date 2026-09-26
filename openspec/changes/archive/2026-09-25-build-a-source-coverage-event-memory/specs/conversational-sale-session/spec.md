## ADDED Requirements

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
