## ADDED Requirements

### Requirement: Void recomputes live cash difference without rewriting the count
After a confirmed sale is voided on an open day that already has a current `CashCount`, live `expected_cash`, `cash_difference`, and `cash_status` MUST recompute from remaining confirmed cash payments while the current `CashCount.amount` MUST stay unchanged. The void path MUST NOT insert a superseding count solely because expected cash changed.

#### Scenario: Counted cash survives void
- **WHEN** counted cash is `22.50`, expected cash was `22.50`, and the cash sale is voided
- **THEN** the current count amount MUST remain `22.50` and live expected cash MUST become `0.00`

#### Scenario: Status leaves balanced when appropriate
- **WHEN** a previously balanced day has expected cash reduced by a void while counted cash stays the same
- **THEN** live `cash_status` MUST no longer be `balanced`
