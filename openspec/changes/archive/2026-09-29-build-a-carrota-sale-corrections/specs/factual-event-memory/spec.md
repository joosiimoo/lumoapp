## MODIFIED Requirements

### Requirement: Build A event types and exact facts
`event_type` MUST be `sale_confirmed`, `sale_voided`, `cash_count_recorded`, or `daily_close_completed`. `sale_confirmed` MUST use `source_entity_type=sale_session` and `occurred_at` equal to the sale `confirmed_at`. Its `facts` MUST be exactly `sale_session_id`, `payment_id`, `payment_method`, `amount`, and `currency`. `sale_session_id` MUST equal `source_entity_id`. `payment_method` MUST be `cash`, `card`, or `transfer`. `sale_voided` MUST use `source_entity_type=sale_session` and `occurred_at` equal to `voided_at`. Its `facts` MUST be exactly `sale_session_id`, `payment_id`, `payment_method`, `amount`, `currency`, `void_reason`, and `voided_by_actor_id`. `sale_session_id` MUST equal `source_entity_id`. `cash_count_recorded` MUST use `source_entity_type=cash_count` and `occurred_at` equal to `counted_at`. Its `facts` MUST be exactly `cash_count_id`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, and `currency`. `cash_count_id` MUST equal `source_entity_id`. `cash_status` MUST be `balanced`, `short`, or `over`. `daily_close_completed` MUST use `source_entity_type=closing_snapshot` and `occurred_at` equal to `closed_at`. Its `facts` MUST be exactly `outcome_run_id`, `closing_snapshot_id`, `sale_count`, `gross_sales_total`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, and `currency`. `closing_snapshot_id` MUST equal `source_entity_id`. `sale_count` MUST be a JSON integer. Money facts MUST be quantized decimal strings with two fraction digits. The close event MUST NOT copy the ClosingSnapshot body and MUST NOT contain a key meaning that all real-world sales were captured. Short and over MUST be `cash_status` on `cash_count_recorded`, not a separate event type.

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

### Requirement: Events are written only with the confirmed parent
`sale_confirmed` MUST be inserted in the successful `sale.commit@1` transaction after the payment and OperationalDay exist. `sale_voided` MUST be inserted in the successful `sale.void@1` transaction after the session is `voided`. `cash_count_recorded` MUST be inserted in the new CashCount transaction. `daily_close_completed` MUST be inserted in the successful `closing.confirm@1` transaction after the snapshot exists and the OutcomeRun is `completed`. A failure before that parent commits MUST leave no business event from that attempt. `ready_to_charge`, totalize, item remove, clarify, a stale token, a closed-day sale refusal, confirmed-sale read-back, and already-closed read-back MUST NOT insert an event. Migration and the open-today initializer MUST NOT insert a business event.

#### Scenario: A failed parent leaves no event
- **WHEN** `sale.commit@1`, `sale.void@1`, a new cash count, or `closing.confirm@1` writes its rows and then fails before commit
- **THEN** no `business_events` row from that attempt MUST remain

#### Scenario: Remove item does not write memory
- **WHEN** `sale.remove_item@1` commits
- **THEN** no business event MUST be inserted for that remove
