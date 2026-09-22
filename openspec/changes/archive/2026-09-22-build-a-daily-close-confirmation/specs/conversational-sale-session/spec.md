## ADDED Requirements

### Requirement: Commit on a closed day does not confirm the sale
When `sale.commit@1` finds today's OperationalDay `closed`, it MUST follow the refusal in `operational-day-foundation`. The payment phrases MUST NOT reopen the day, MUST NOT create a second day for that `business_date`, and MUST NOT leave the session `confirmed`.

#### Scenario: Efectivo after close
- **WHEN** today's OperationalDay is `closed` and a `ready_to_charge` session posts `efectivo`
- **THEN** the session MUST stay `ready_to_charge`, no `Payment` MUST exist for that attempt, and `OperationalDay.status` MUST stay `closed`
