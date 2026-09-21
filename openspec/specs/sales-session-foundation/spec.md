## Purpose

One open `SaleSession` per interaction context, `SaleItem` persistence, gram→kilogram normalization, deterministic Decimal line totals, and transactional consistency with audit/outbox/idempotency.

## Requirements

### Requirement: Sales schema and session entity
Persistence MUST create PostgreSQL schema `sales` with `sale_sessions` and `sale_items`. `SaleSession` MUST include `id` (UUIDv7), `business_id`, `actor_id`, optional `conversation_id`, `status`, `currency`, `created_at`, and `updated_at`. When the message path supplies `conversation_id`, that value MUST be persisted on the session. Domain entities MUST NOT be SQLAlchemy models. Tenant-scoped sales tables MUST enable RLS.

#### Scenario: Tables exist
- **WHEN** Alembic migrations for this capability complete
- **THEN** `sales.sale_sessions` and `sales.sale_items` MUST exist with `business_id` and `numeric` money/quantity columns

### Requirement: One active session per interaction context
Interaction context MUST be `(business_id, actor_id, conversation_id)` when `conversation_id` is present, otherwise `(business_id, actor_id)`. At most one `SaleSession` with `status=open` MUST exist per interaction context. `sale.start@1` MUST reuse that session when present and MUST create one when absent. A message with a new `conversation_id` MUST NOT reuse an open session that has a different `conversation_id` or a NULL `conversation_id`. Confirmation, void, and completion MUST NOT be implemented here.

#### Scenario: First start creates
- **WHEN** no open session exists for the interaction context and `sale.start@1` runs
- **THEN** a `SaleSession` with `status=open` MUST be persisted and returned with `created=true`

#### Scenario: Second start reuses
- **WHEN** an open session already exists for the same interaction context and `sale.start@1` runs again
- **THEN** the same `sale_session_id` MUST be returned, `created=false`, and no second open session MUST exist

#### Scenario: Conversation id is persisted
- **WHEN** the message path creates or reuses a session with a non-null `conversation_id`
- **THEN** `sales.sale_sessions.conversation_id` MUST equal that value

### Requirement: SaleItem persistence
`SaleItem` MUST include `id`, `business_id`, `sale_session_id`, `product_id`, `product_name_snapshot`, `quantity_input`, `unit_input`, `quantity_normalized`, `unit_normalized`, `unit_price`, `currency`, `line_total`, `created_at`, and `updated_at`. Quantities and money MUST be `numeric`/`Decimal`. A `SaleItem` MUST belong to an `open` session in the same tenant.

#### Scenario: Item stored after add
- **WHEN** `sale.add_item@1` commits for Zanahoria
- **THEN** a `SaleItem` row MUST exist with `product_name_snapshot=Zanahoria` and the server-calculated `line_total`

### Requirement: Quantity positivity and units
Input `quantity` MUST be a positive Decimal string. Supported input units MUST be `gram`, `kilogram`, `unit`, and `package`. `gram` MUST be accepted only when the product `sale_unit` is `kilogram`. Incompatible units MUST be rejected with `UNIT_NOT_SUPPORTED` and MUST NOT persist an item.

#### Scenario: Zero rejected
- **WHEN** add-item is invoked with quantity `0`
- **THEN** the operation MUST fail validation and MUST NOT persist a `SaleItem`

#### Scenario: Gram on unit product rejected
- **WHEN** add-item is invoked with `unit=gram` for a product whose `sale_unit` is `unit`
- **THEN** the operation MUST fail with `UNIT_NOT_SUPPORTED` and MUST NOT persist

### Requirement: Deterministic gram to kilogram normalization
When `unit_input=gram` and product `sale_unit=kilogram`, `quantity_normalized` MUST equal `quantity_input / 1000` using `Decimal` with no binary float. `unit_normalized` MUST be `kilogram`. Kilogram, unit, and package inputs MUST copy quantity to `quantity_normalized` without conversion. The LLM MUST NOT supply `quantity_normalized` or `line_total` as source of truth.

#### Scenario: 900 grams becomes 0.900 kilograms
- **WHEN** add-item receives `quantity=900` and `unit=gram` for Zanahoria
- **THEN** the persisted item MUST have `quantity_normalized=0.900` and `unit_normalized=kilogram`

### Requirement: Deterministic line total
`line_total` MUST be calculated in backend domain logic as `quantity_normalized * current_price` using `Decimal`. MXN amounts MUST round to two decimal places in a single money helper. Flutter MUST NOT recompute the total. The LLM MUST NOT persist or overwrite the total.

#### Scenario: Zanahoria line total
- **WHEN** `quantity_normalized` is `0.900` and Zanahoria `current_price` is `25.00` MXN
- **THEN** persisted and returned `line_total` MUST be `22.50` MXN as a decimal string plus currency `MXN`

### Requirement: Missing essential unit is not inferred
If interpretation lacks a unit, the system MUST clarify and MUST NOT infer `kilogram` from the product's `sale_unit`. If product, quantity, or unit is ambiguous, the system MUST preserve unequivocal fields, ask only for the missing or ambiguous field, and MUST NOT persist a `SaleItem`.

#### Scenario: Quantity without unit
- **WHEN** the user message is `900 zanahoria` with no unit
- **THEN** the system MUST return a clarification, MUST NOT start from a guessed unit, and MUST NOT persist a `SaleItem`

### Requirement: Session status for this slice
`SaleSession.status` MUST be `open` after a successful start and MUST remain `open` after a successful add-item. Transitions to confirmed, pending_information, or voided MUST NOT be implemented here.

#### Scenario: Successful add-item keeps session open
- **WHEN** add-item commits on an open session
- **THEN** that session MUST still have `status=open` and the new `SaleItem` MUST be visible

### Requirement: Message-path write transaction
The public conversational operation (`POST /api/v1/lumo/messages` that adds a catalog item) MUST use one application-owned write transaction for creating or reusing the `SaleSession` plus inserting the `SaleItem`, together with that operation's audit, outbox, and idempotency rows. `catalog.resolve_product@1` is read-only and MUST run before that write transaction. The orchestrator MUST NOT open the transaction. A failed logical mutation MUST NOT leave an orphan session created for that message, MUST NOT leave a partial item, and MUST NOT commit success audit/outbox/idempotency rows for that mutation. After a committed mutation, every related audit and `sale.item.added` outbox payload MUST reference `sale_session_id` / `sale_item_id` rows that still exist.

#### Scenario: New session rolled back with failed add-item
- **WHEN** no open session exists for the interaction context, the message workflow creates a session and writes a `SaleItem`, and the transaction fails before commit
- **THEN** neither the new `SaleSession` nor the `SaleItem` MUST remain, and no successful audit or outbox row for that message MUST remain

#### Scenario: Reused session unchanged after failed add-item
- **WHEN** an open session already exists, the message workflow reuses it, writes a `SaleItem`, and the transaction fails before commit
- **THEN** no `SaleItem` from that attempt MUST remain and the existing `SaleSession` MUST be unchanged from its pre-request committed state

#### Scenario: Resolve does not create a session
- **WHEN** product resolution is `ambiguous` or `none`, or the unit is missing
- **THEN** no write transaction for start/add-item MUST run and no new `SaleSession` MUST be created

#### Scenario: Committed integrity rows stay consistent
- **WHEN** a message-path add-item commits
- **THEN** the session, item, message idempotency row, `sale.start@1`/`sale.add_item@1` audit rows, and `sale.item.added` outbox row MUST all exist together, and audit/outbox payloads MUST reference those live ids

### Requirement: Sale-mutation reset stays consistent
Test or reset utilities that intentionally remove committed sale mutations MUST delete `sale_items` and `sale_sessions` together with related `audit_events` (`sale.start@1`, `sale.add_item@1`), `outbox_events` (`sale.item.added`), and `idempotency_records` (`lumo.message.add_sale_item`) in one transaction, or they MUST roll the original transaction back. They MUST NOT delete only sales (and/or only idempotency) rows. After cleanup or rollback, no audit or outbox row MAY reference a `sale_session_id` or `sale_item_id` that does not exist.

#### Scenario: Cleanup does not leave orphan integrity
- **WHEN** a test helper removes a tenant's committed sale mutations
- **THEN** related sale audit, `sale.item.added` outbox, and message idempotency rows MUST also be gone, and no remaining audit/outbox payload MAY point at a missing session or item
