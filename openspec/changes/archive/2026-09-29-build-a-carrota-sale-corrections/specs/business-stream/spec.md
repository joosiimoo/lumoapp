## ADDED Requirements

### Requirement: Open-day Business Stream excludes voided sales
For open-day `factual_summary` values that come from `summarize_day`, voided sales MUST NOT contribute to `sale_count`, `gross_sales_total`, tender totals, or `expected_cash`. After a void, a Business Stream refresh MUST show the reduced live figures. Closed-day snapshot facts remain unchanged because void is refused after close.

#### Scenario: Hoy gross drops after void
- **WHEN** Hoy showed gross `47.00` from two confirmed sales and one sale of `22.50` is voided
- **THEN** the next `GET /api/v1/business-stream/today` MUST show gross `24.50` and sale count 1

#### Scenario: Operator state leaves ready_to_close when cash breaks
- **WHEN** operator_state was `ready_to_close` because cash was balanced and a void makes cash no longer balanced
- **THEN** the next today projection MUST NOT remain `ready_to_close` solely from the pre-void figures
