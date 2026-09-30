## MODIFIED Requirements

### Requirement: Expected cash is recorded cash payments of the day
`expected_cash` MUST be computed in the backend as the `Decimal` sum of `sales.payments.amount` where `status=recorded` and `method=cash`, for the `SaleSession`s of that `OperationalDay` whose status is `confirmed`. It MUST be quantized to two decimal places, MUST be `0.00` when there are no cash sales, and MUST use the business currency. Card and transfer payments MUST NOT change it. `open`, `ready_to_charge`, and `voided` sessions MUST be excluded. `expected_cash` MUST be produced by the same repository aggregation that computes `cash_total` for `operational_day.summary@1`, and the two values MUST be equal for the same day. Build A MUST NOT include an opening float, cash expenses, withdrawals, deposits, refunds, tips, or rounding adjustments in the formula. Voided sales are excluded by the `confirmed`-only session filter rather than by deleting payments. The client, the interpreter, and the model MUST NOT supply or recompute `expected_cash`.

#### Scenario: Only cash sales count
- **WHEN** today's confirmed sales are one cash sale of `22.50`, one card sale of `10.00`, and one transfer sale of `24.00`
- **THEN** `expected_cash` MUST be `22.50` in the business currency and MUST equal that day's `cash_total` from `operational_day.summary@1`

#### Scenario: No cash sales
- **WHEN** today's OperationalDay has confirmed sales but none paid with cash
- **THEN** `expected_cash` MUST be `0.00` and MUST NOT be null

#### Scenario: Drafts are excluded
- **WHEN** an `open` or `ready_to_charge` session exists for the same business date
- **THEN** it MUST NOT change `expected_cash`

#### Scenario: Voided cash sale is excluded
- **WHEN** a cash sale of `22.50` on the day is `voided` and no other cash sale remains confirmed
- **THEN** `expected_cash` MUST be `0.00`
