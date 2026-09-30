## ADDED Requirements

### Requirement: Day events include sale voids
When `day_events` or recent event reads return business events for a day that has a void, the result MUST include the `sale_voided` event with its typed facts alongside any `sale_confirmed` for the same session. Sales summary and open-day money facts MUST exclude voided sessions and MUST match live `summarize_day` confirmed-only totals.

#### Scenario: Chronology keeps confirm then void
- **WHEN** a sale is confirmed and later voided on the same open day
- **THEN** `day_events` MUST include both `sale_confirmed` and `sale_voided` ordered by `occurred_at`

#### Scenario: Sales summary ignores voided
- **WHEN** one of two sales is voided and `sales_summary` runs for that day
- **THEN** sale count and gross MUST match the remaining confirmed sale only
