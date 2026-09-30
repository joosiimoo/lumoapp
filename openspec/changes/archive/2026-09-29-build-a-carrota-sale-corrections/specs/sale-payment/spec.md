## ADDED Requirements

### Requirement: Void keeps the recorded Payment
Voiding a confirmed sale MUST NOT delete the `Payment` row and MUST NOT change `Payment.status` away from `recorded`. The payment amount and method MUST remain the historical values from commit. Live operational aggregates MUST exclude the voided session rather than relying on payment deletion.

#### Scenario: Payment survives void
- **WHEN** a confirmed sale with payment `22.50` cash is voided
- **THEN** exactly one `payments` row MUST still exist for that `sale_session_id` with `status=recorded`, `method=cash`, and `amount=22.50`

#### Scenario: Second payment is still forbidden
- **WHEN** a session is `voided`
- **THEN** inserting another payment for that `sale_session_id` MUST fail
