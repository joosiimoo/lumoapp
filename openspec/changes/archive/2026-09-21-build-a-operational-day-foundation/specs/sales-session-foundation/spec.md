## ADDED Requirements

### Requirement: Confirmed session stores operational day membership
`SaleSession` MUST include nullable `operational_day_id` and `confirmed_at` in addition to its existing fields. `sale.commit@1` MUST set both when it transitions `ready_to_charge` → `confirmed`, and MUST leave them NULL for `open` and `ready_to_charge`. The referenced OperationalDay MUST belong to the same `business_id`. Existing items and the single `Payment` MUST remain. The active-session unique index MUST stay limited to `open` and `ready_to_charge`. `confirmed` MUST still mean operational sale completion, not Daily Close.

#### Scenario: Successful commit attaches the day
- **WHEN** commit records `cash` on a `ready_to_charge` session
- **THEN** that session MUST have `status=confirmed`, a non-null `operational_day_id` and `confirmed_at`, its `SaleItem`s MUST still be visible, and exactly one `Payment` MUST exist for it

#### Scenario: Next open session is not attached
- **WHEN** a product utterance after `confirmed` starts a new `open` session on the same `conversation_id`
- **THEN** the new session MUST have `operational_day_id` NULL until its own confirming commit, and the previous confirmed session MUST keep its original `operational_day_id`
