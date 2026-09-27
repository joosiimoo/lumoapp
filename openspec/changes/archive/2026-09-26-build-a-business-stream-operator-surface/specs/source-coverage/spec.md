## MODIFIED Requirements

### Requirement: Coverage writes only on confirmed transitions
Coverage inserts MUST run only inside successful `sale.commit@1`, a new `CashCount` insert, successful `closing.confirm@1`, and the open-today initializer described below. Replay of those parents MUST NOT insert a second row. `closing.prepare@1`, `operational_day.summary@1`, daily sales export, `GET /api/v1/operational-days/current/next-best-action`, `GET /api/v1/business-stream/today`, `operational_day.next_best_action@1`, `OutcomeEngine.evaluate`, `FactualMemoryService`, `memory.business_facts@1`, and `GET /api/v1/memory/events` MUST NOT insert or update coverage. There MUST be no coverage HTTP route and no coverage tool. There MUST be no new coverage audit action and no `source_coverage.updated` outbox event.

#### Scenario: Replay does not duplicate coverage
- **WHEN** the actor resubmits the same confirming sale with the same idempotency key and payload hash
- **THEN** exactly one `sales` coverage row MUST exist for that day

#### Scenario: Pure reads do not write coverage
- **WHEN** the actor loads Next Best Action, the business stream, the day summary, close preparation, or the sales export, or a caller evaluates `daily_close_ready@1`, or a caller runs a factual memory query or `GET /api/v1/memory/events`
- **THEN** the coverage row count for that business MUST be unchanged

#### Scenario: Another tenant cannot read coverage
- **WHEN** tenant B queries coverage while tenant A's row exists
- **THEN** tenant B MUST NOT receive tenant A's row

## ADDED Requirements

### Requirement: Business Stream returns the limitation sentence
When `GET /api/v1/business-stream/today` resolves an OperationalDay and the operator state is not `unavailable`, the body MUST include `coverage.limitation_code` `only_lumo_registered_operations` and the merchant sentence `Este cierre considera las operaciones registradas en Lumo.` That object MUST NOT include a percentage, a health score, or a complete flag. A business stream read MUST NOT change a coverage row from `observed` to any other status. The route MUST NOT be a coverage collection route.

#### Scenario: Ready close keeps the limitation
- **WHEN** the business stream is read for a day whose sales coverage is `observed` and the close is ready
- **THEN** the coverage sentence MUST be present and the sales row MUST remain `observed`

#### Scenario: No coverage route
- **WHEN** the API route table is inspected
- **THEN** it MUST NOT contain a source-coverage collection route
