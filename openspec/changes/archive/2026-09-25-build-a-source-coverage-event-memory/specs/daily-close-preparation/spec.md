## ADDED Requirements

### Requirement: A new cash count records cash coverage and count memory
A successful insert of a new current `CashCount` MUST, in that same transaction, after OutcomeRun sync and WorkItem sync and before parent idempotency completes, ensure the `cash_count` / `manual_capture` coverage row and insert one `cash_count_recorded` business event, as `source-coverage` and `factual-event-memory` require. The equal-amount read-back that writes no count MUST NOT ensure coverage and MUST NOT insert an event. `closing.prepare@1` MUST NOT insert or update coverage, a business event, audit, outbox, or idempotency. A short or over count MUST remain preparable and closable. Preparation card actions and copy MUST stay unchanged. The new count MUST NOT change an existing `sales` coverage row to any status other than `observed`.

#### Scenario: The first count writes coverage and one event
- **WHEN** the first current CashCount for an open day is inserted with a short amount
- **THEN** one `cash_count` coverage row MUST exist at `observed`, and one `cash_count_recorded` event MUST include `cash_status=short`

#### Scenario: An equal amount writes nothing new
- **WHEN** the actor submits the current counted amount again
- **THEN** no second CashCount, no second coverage row, and no second business event MUST exist

#### Scenario: Preparation does not write coverage or memory
- **WHEN** the actor posts `preparar el cierre`
- **THEN** `closing.prepare@1` MUST NOT insert or update a coverage row or a business event
