## MODIFIED Requirements

### Requirement: Outcome writes join the parent transaction only
Outcome sync MUST run only inside successful `sale.commit@1`, a new current CashCount insert, and successful `closing.confirm@1`, in the order `daily-close-outcome` design records. `closing.prepare@1`, `operational_day.summary@1`, daily sales export, the Next Best Action GET, `GET /api/v1/business-stream/today`, `operational_day.next_best_action@1`, an equal-amount cash-count read-back, a clarify, a stale confirmation, an idempotent replay, and an already-closed read-back MUST NOT insert or update an OutcomeRun. A failure before commit MUST leave no new OutcomeRun and no outcome audit from that attempt. Export column names, file bytes, and close phrases MUST stay unchanged.

#### Scenario: Preparation does not write the outcome
- **WHEN** the actor posts `preparar el cierre` for an open day that already has an OutcomeRun
- **THEN** that OutcomeRun MUST be unchanged and no outcome audit MUST be written

#### Scenario: Export does not write the outcome
- **WHEN** a tenant downloads the daily sales export
- **THEN** OutcomeRun, audit, outbox, and idempotency row counts MUST be unchanged by that download

#### Scenario: A rolled-back commit leaves no outcome
- **WHEN** the first commit of the day fails before commit after preparing an OutcomeRun insert
- **THEN** that OutcomeRun MUST NOT remain

#### Scenario: Business Stream does not write the outcome
- **WHEN** `GET /api/v1/business-stream/today` runs for an open day that already has an OutcomeRun
- **THEN** that OutcomeRun MUST be unchanged and no outcome audit MUST be written

### Requirement: No merchant outcome API
The system MUST NOT add `GET /api/v1/operational-days/current/outcome` or any other merchant OutcomeRun resource route. `GET /api/v1/business-stream/today` MAY read today's OutcomeRun id and MUST NOT return the run, its `reason_code`, or its evidence. That GET MUST NOT insert or update an OutcomeRun.

#### Scenario: Outcome route is absent
- **WHEN** the API route table is inspected
- **THEN** it MUST NOT contain an outcome collection or current-outcome route

#### Scenario: Business Stream is not an outcome resource
- **WHEN** `GET /api/v1/business-stream/today` returns for a day that has an OutcomeRun
- **THEN** the body MUST NOT contain `reason_code` or outcome evidence, and the OutcomeRun row MUST be unchanged
