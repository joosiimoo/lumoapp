## ADDED Requirements

### Requirement: Factual memory tool may ground void answers
When grounded facts include a `sale_voided` event, assistant text produced through `memory.business_facts@1` MUST be able to state that a sale was anulada using those facts and MUST NOT claim the voided amount remains in today's live gross. The tool remains read-only and MUST NOT invent void reasons absent from facts.

#### Scenario: Void fact can be answered
- **WHEN** the merchant asks about a voided sale and the tool result includes `sale_voided`
- **THEN** grounded assistant text MUST reflect the void and MUST NOT treat that amount as live gross
