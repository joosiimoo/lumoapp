# factual-event-memory Specification

## Purpose

Factual Event Memory answers which confirmed business fact happened. A business event is not audit, outbox, chat memory, model memory, inferred memory, embeddings or vector memory, or generic knowledge storage.

## Requirements

### Requirement: Factual event memory is an append-only business event
The system MUST persist factual Event Memory only in `operations.business_events`. A row MUST store `id`, `business_id`, `operational_day_id`, `event_type`, `occurred_at`, `source_type`, `source_entity_type`, `source_entity_id`, `facts`, and `created_at`. `operational_day_id` MUST be NOT NULL. `source_type` MUST be `manual_capture` and MUST mean the primary operational data source underlying the confirmed business fact. It MUST NOT mean the application component that executed the write, the workflow that produced the event, or the API or tool route that handled the request. `sale_confirmed` MUST use `manual_capture` because its confirmed `Payment` is `manual_capture`. `cash_count_recorded` MUST use `manual_capture` because the merchant `CashCount` is `manual_capture`. `daily_close_completed` MUST use `manual_capture` because the Build A close commits operational facts whose implemented source coverage is `manual_capture`. The proving entity for that close event MUST remain `source_entity_type=closing_snapshot` and `source_entity_id` equal to the `ClosingSnapshot` id. The check MUST reject `lumo_workflow`, `merchant_declared`, `conversation`, `system`, and any other source type. The row MUST NOT store a workflow-origin field. `facts` MUST be a JSON object. The row MUST NOT store `updated_at`, an embedding, a vector, a title, a narrative, a summary, an importance score, a sentiment, a model confidence, an expiry, or editable memory text. It MUST NOT reference `source_coverage_records`. Foreign key `fk_business_events_operational_day` MUST bind `(operational_day_id, business_id)` to `operations.operational_days (id, business_id)`. A `BEFORE UPDATE` trigger `business_events_immutable` MUST raise for every role. `lumo_app` MUST NOT receive `UPDATE`. Product workflows MUST NOT delete a row.

#### Scenario: Close provenance is manual capture proved by the snapshot
- **WHEN** a `daily_close_completed` row is inserted
- **THEN** `source_type` MUST be `manual_capture`, `source_entity_type` MUST be `closing_snapshot`, and `source_entity_id` MUST equal that ClosingSnapshot id

#### Scenario: No embedding or vector column exists
- **WHEN** `operations.business_events` is inspected
- **THEN** it MUST NOT have an embedding column, a vector column, or a vector extension dependency

#### Scenario: Facts reject model prose
- **WHEN** an insert supplies a `facts` key other than the keys required for that event type, including `summary`, `narrative`, `title`, or `confidence`
- **THEN** the database MUST reject the insert

### Requirement: Build A event types and exact facts
`event_type` MUST be `sale_confirmed`, `cash_count_recorded`, or `daily_close_completed`. `sale_confirmed` MUST use `source_entity_type=sale_session` and `occurred_at` equal to the sale `confirmed_at`. Its `facts` MUST be exactly `sale_session_id`, `payment_id`, `payment_method`, `amount`, and `currency`. `sale_session_id` MUST equal `source_entity_id`. `payment_method` MUST be `cash`, `card`, or `transfer`. `cash_count_recorded` MUST use `source_entity_type=cash_count` and `occurred_at` equal to `counted_at`. Its `facts` MUST be exactly `cash_count_id`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, and `currency`. `cash_count_id` MUST equal `source_entity_id`. `cash_status` MUST be `balanced`, `short`, or `over`. `daily_close_completed` MUST use `source_entity_type=closing_snapshot` and `occurred_at` equal to `closed_at`. Its `facts` MUST be exactly `outcome_run_id`, `closing_snapshot_id`, `sale_count`, `gross_sales_total`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, and `currency`. `closing_snapshot_id` MUST equal `source_entity_id`. `sale_count` MUST be a JSON integer. Money facts MUST be quantized decimal strings with two fraction digits. The close event MUST NOT copy the ClosingSnapshot body and MUST NOT contain a key meaning that all real-world sales were captured. Short and over MUST be `cash_status` on `cash_count_recorded`, not a separate event type.

#### Scenario: A confirmed sale writes one sale event
- **WHEN** `sale.commit@1` confirms a cash sale
- **THEN** exactly one `sale_confirmed` row MUST exist for that `sale_session_id`, and `facts` MUST include that session id, the payment id, `payment_method=cash`, the payment amount, and the currency

#### Scenario: A short count stores the difference on the count event
- **WHEN** a new CashCount is short, with expected cash `22.50` and counted cash `20.00`
- **THEN** exactly one `cash_count_recorded` row MUST exist for that cash count id, and `facts` MUST include expected `22.50`, counted `20.00`, difference `-2.50`, and `cash_status=short`

#### Scenario: Close references the outcome and the snapshot
- **WHEN** `closing.confirm@1` commits
- **THEN** exactly one `daily_close_completed` row MUST exist whose `source_entity_id` is the new ClosingSnapshot id, and `facts.outcome_run_id` MUST be that day's completed OutcomeRun id

### Requirement: Event identity follows the source fact
Unique constraint `uq_business_events_source` MUST enforce one row for `(business_id, event_type, source_entity_type, source_entity_id)`. A replay of the parent mutation MUST NOT insert a second row. An equal-amount cash-count read-back MUST NOT insert an event. A superseding CashCount MUST insert one new event for the new cash count id and MUST leave the previous event in place. There MUST be no separate event idempotency operation.

#### Scenario: Replaying a sale does not duplicate the event
- **WHEN** the actor resubmits the same confirming sale with the same idempotency key and payload hash
- **THEN** exactly one `sale_confirmed` row MUST exist for that sale session

#### Scenario: An equal cash amount writes no event
- **WHEN** the current CashCount amount is submitted again and the workflow returns the existing count
- **THEN** no additional `cash_count_recorded` row MUST exist

#### Scenario: Close replay does not duplicate the event
- **WHEN** the actor resubmits the same close with the same idempotency key and payload hash
- **THEN** exactly one `daily_close_completed` row MUST exist for that ClosingSnapshot

### Requirement: Events are written only with the confirmed parent
`sale_confirmed` MUST be inserted in the successful `sale.commit@1` transaction after the payment and OperationalDay exist. `cash_count_recorded` MUST be inserted in the new CashCount transaction. `daily_close_completed` MUST be inserted in the successful `closing.confirm@1` transaction after the snapshot exists and the OutcomeRun is `completed`. A failure before that parent commits MUST leave no business event from that attempt. `ready_to_charge`, totalize, clarify, a stale token, a closed-day sale refusal, confirmed-sale read-back, and already-closed read-back MUST NOT insert an event. Migration `0012` and the open-today initializer MUST NOT insert a business event.

#### Scenario: A failed parent leaves no event
- **WHEN** `sale.commit@1`, a new cash count, or `closing.confirm@1` writes its rows and then fails before commit
- **THEN** no `business_events` row from that attempt MUST remain

#### Scenario: Historical closes are not reconstructed
- **WHEN** Alembic applies `0012` and the initializer runs against a database that already has a ClosingSnapshot
- **THEN** no `daily_close_completed` row MUST be inserted for that existing snapshot

### Requirement: Event reads stay on the repository
The operations repository MUST be able to list one tenant's events for one `operational_day_id` ordered by `occurred_at`, then `id`. The system MUST NOT register `memory.query_events`, MUST NOT expose a public memory search route, and MUST NOT answer natural-language history in this slice. Tenant B MUST NOT read tenant A's events.

#### Scenario: Another tenant cannot read events
- **WHEN** tenant B lists events for an operational day that belongs to tenant A
- **THEN** tenant B MUST receive no tenant A event

#### Scenario: Pure reads create no event
- **WHEN** the actor loads Next Best Action, the day summary, close preparation, or the sales export, or a caller evaluates `daily_close_ready@1`
- **THEN** the business event count for that business MUST be unchanged

### Requirement: Event memory is not audit or outbox
Inserting a business event MUST NOT write a new audit action and MUST NOT enqueue `memory.event.created`, `source_coverage.updated`, or any other new outbox type. Existing `sale.confirmed`, `payment.recorded`, `cash_count.recorded`, and `closing.confirmed` outbox rows MUST remain the integration messages they already are. A business event MUST NOT be created by delivering an outbox row. Deleting an outbox row MUST NOT delete a business event.

#### Scenario: Close still has one outbox message and one memory row
- **WHEN** a close commits
- **THEN** exactly one `closing.confirmed` outbox row AND exactly one `daily_close_completed` business event MUST exist, and no `memory.event.created` outbox row MUST exist

#### Scenario: Audit stays on the parent mutation
- **WHEN** a confirmed sale, a new cash count, or a close inserts its business event
- **THEN** no audit action named `business_event.created` or `source_coverage.created` MUST exist
