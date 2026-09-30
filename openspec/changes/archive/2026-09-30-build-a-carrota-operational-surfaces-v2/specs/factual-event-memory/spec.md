## MODIFIED Requirements

### Requirement: Build A event types and exact facts
`event_type` MUST be `sale_confirmed`, `sale_voided`, `cash_count_recorded`, or `daily_close_completed`. `sale_confirmed` MUST use `source_entity_type=sale_session` and `occurred_at` equal to the sale `confirmed_at`. Its `facts` MUST be exactly `sale_session_id`, `payment_id`, `payment_method`, `amount`, and `currency`. `sale_session_id` MUST equal `source_entity_id`. `payment_method` MUST be `cash`, `card`, or `transfer`. `sale_voided` MUST use `source_entity_type=sale_session` and `occurred_at` equal to `voided_at`. Its `facts` MUST be exactly `sale_session_id`, `payment_id`, `payment_method`, `amount`, `currency`, `void_reason`, and `voided_by_actor_id`. `sale_session_id` MUST equal `source_entity_id`. `cash_count_recorded` MUST use `source_entity_type=cash_count` and `occurred_at` equal to `counted_at`. Its `facts` MUST be exactly `cash_count_id`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, and `currency`. `cash_count_id` MUST equal `source_entity_id`. `cash_status` MUST be `balanced`, `short`, or `over`. `daily_close_completed` MUST use `source_entity_type=closing_snapshot` and `occurred_at` equal to `closed_at`. Its `facts` MUST include `outcome_run_id`, `closing_snapshot_id`, `sale_count`, `gross_sales_total`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, and `currency`, and MUST include `close_note` when the ClosingSnapshot has a non-null note. `closing_snapshot_id` MUST equal `source_entity_id`. `sale_count` MUST be a JSON integer. Money facts MUST be quantized decimal strings with two fraction digits. The close event MUST NOT copy the ClosingSnapshot body beyond those facts and MUST NOT contain a key meaning that all real-world sales were captured. Short and over MUST be `cash_status` on `cash_count_recorded`, not a separate event type.

#### Scenario: A confirmed sale writes one sale event
- **WHEN** `sale.commit@1` confirms a cash sale
- **THEN** exactly one `sale_confirmed` row MUST exist for that `sale_session_id`, and `facts` MUST include that session id, the payment id, `payment_method=cash`, the payment amount, and the currency

#### Scenario: A voided sale writes one void event
- **WHEN** `sale.void@1` voids that cash sale with reason `cobro duplicado`
- **THEN** exactly one `sale_voided` row MUST exist for that `sale_session_id`, `facts.void_reason` MUST be `cobro duplicado`, and the original `sale_confirmed` row MUST still exist

#### Scenario: A short count stores the difference on the count event
- **WHEN** a new CashCount is short, with expected cash `22.50` and counted cash `20.00`
- **THEN** exactly one `cash_count_recorded` row MUST exist for that cash count id, and `facts` MUST include expected `22.50`, counted `20.00`, difference `-2.50`, and `cash_status=short`

#### Scenario: Close references the outcome and the snapshot
- **WHEN** `closing.confirm@1` commits
- **THEN** exactly one `daily_close_completed` row MUST exist whose `source_entity_id` is the new ClosingSnapshot id, and `facts.outcome_run_id` MUST be that day's completed OutcomeRun id

#### Scenario: Close note appears on the close event when present
- **WHEN** `closing.confirm@1` commits with snapshot `close_note` `Faltaron dos billetes`
- **THEN** `facts.close_note` MUST equal that string
