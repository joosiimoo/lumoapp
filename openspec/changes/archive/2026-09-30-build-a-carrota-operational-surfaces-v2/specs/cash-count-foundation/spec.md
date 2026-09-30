## ADDED Requirements

### Requirement: Structured action path reuses RecordCashCount
`closing.submit_cash_count@1` MUST remain the only cash-count write tool and MUST keep input `{ "amount": decimal-string }` without a note field. A structured UiAction path that invokes the same tool MUST produce the same CashCount persistence, supersede chain, idempotency, audit, outbox, and preparation output guarantees as the conversational message path. `operations.cash_counts` MUST still NOT store a merchant note, expected cash, difference, or cash status.

#### Scenario: Structured and conversational counts share persistence
- **WHEN** a counted amount `20.00` is recorded via the structured action path for an open day
- **THEN** exactly one current CashCount with amount `20.00` MUST exist and MUST NOT contain a note column value

#### Scenario: CashCount still rejects notes
- **WHEN** the cash_counts table definition is inspected
- **THEN** it MUST NOT contain a merchant note column
