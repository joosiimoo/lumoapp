## Purpose

One active `SaleSession` (`open` or `ready_to_charge`) per interaction context; `confirmed` sessions are inactive. `SaleItem` persistence, gram→kilogram normalization, deterministic Decimal line and session totals, row-lock serialization of add-item/totalize/commit, and transactional consistency with audit/outbox/idempotency including `Payment`.
## Requirements
### Requirement: Sales schema and session entity
Persistence MUST create PostgreSQL schema `sales` with `sale_sessions` and `sale_items`. `SaleSession` MUST include `id` (UUIDv7), `business_id`, `actor_id`, optional `conversation_id`, `status`, `currency`, `created_at`, and `updated_at`. When the message path supplies `conversation_id`, that value MUST be persisted on the session. Domain entities MUST NOT be SQLAlchemy models. Tenant-scoped sales tables MUST enable RLS.

#### Scenario: Tables exist
- **WHEN** Alembic migrations for this capability complete
- **THEN** `sales.sale_sessions` and `sales.sale_items` MUST exist with `business_id` and `numeric` money/quantity columns

### Requirement: One active session per interaction context
Interaction context MUST be `(business_id, actor_id, conversation_id)` when `conversation_id` is present, otherwise `(business_id, actor_id)`. At most one `SaleSession` with status `open` or `ready_to_charge` MUST exist per interaction context. `confirmed` sessions MUST NOT count as active. `sale.start@1` MUST reuse the `open` session when present and MUST create one when no active session exists, including when the latest session for that context is `confirmed`. If a `ready_to_charge` session already exists for that context, `sale.start@1` MUST NOT create a second session and MUST NOT treat that session as reusable for add-item. A message with a new `conversation_id` MUST NOT reuse an active session that has a different `conversation_id` or a NULL `conversation_id`. Void remains out of scope.

#### Scenario: First start creates
- **WHEN** no active session exists for the interaction context and `sale.start@1` runs
- **THEN** a `SaleSession` with `status=open` MUST be persisted and returned with `created=true`

#### Scenario: Second start reuses
- **WHEN** an open session already exists for the same interaction context and `sale.start@1` runs again
- **THEN** the same `sale_session_id` MUST be returned, `created=false`, and no second open session MUST exist

#### Scenario: Conversation id is persisted
- **WHEN** the message path creates or reuses a session with a non-null `conversation_id`
- **THEN** `sales.sale_sessions.conversation_id` MUST equal that value

#### Scenario: Ready_to_charge blocks a second session
- **WHEN** a `ready_to_charge` session exists for the interaction context and `sale.start@1` or add-item runs
- **THEN** no new `SaleSession` MUST be created for that context

#### Scenario: Confirmed frees the context for a new sale
- **WHEN** the latest session for the interaction context is `confirmed` and `sale.start@1` or message-path add-item runs
- **THEN** a new `open` `SaleSession` MUST be created, `sale.start@1` output `status` MUST be `open` (MUST NOT be `confirmed`), and the confirmed session MUST NOT be reused or mutated

### Requirement: SaleItem persistence
`SaleItem` MUST include `id`, `business_id`, `sale_session_id`, `source_type`, `product_id`, `product_name_snapshot`, `quantity_input`, `unit_input`, `quantity_normalized`, `unit_normalized`, `unit_price`, `currency`, `line_total`, `catalog_unit_price_snapshot`, `price_override_reason`, `created_at`, and `updated_at`. `source_type` MUST be `catalog` or `free_concept`. A `catalog` item MUST have non-null `product_id` and a non-null `catalog_unit_price_snapshot`. A normal catalog item MUST have `unit_price` equal to that snapshot and `price_override_reason` NULL. An override catalog item MUST have `unit_price` different from that snapshot and a non-empty `price_override_reason`. A `free_concept` item MUST have `product_id` NULL, `catalog_unit_price_snapshot` NULL, `price_override_reason` NULL, and a non-empty `product_name_snapshot`. That snapshot name MUST be the display span defined by `noncatalog-sale-item`, not `normalize_product_name`. Quantities and money MUST be `numeric`/`Decimal`. A new `SaleItem` MUST belong to an `open` session in the same tenant. A `SaleItem` already persisted on a session that later becomes `ready_to_charge` or `confirmed` MUST remain. New items MUST NOT be appended after `ready_to_charge` or onto a `confirmed` session. After `confirmed`, a conversational add-item for the same interaction context MUST attach to a new `open` session. This change MUST NOT add an edit or delete path for either source.

#### Scenario: Item stored after add
- **WHEN** `sale.add_item@1` commits for Zanahoria at its catalog price
- **THEN** a `SaleItem` row MUST exist with `source_type=catalog`, `product_name_snapshot=Zanahoria`, a non-null `product_id`, `catalog_unit_price_snapshot` equal to `unit_price`, `price_override_reason` NULL, and the server-calculated `line_total`

#### Scenario: Item refused after totalize
- **WHEN** the session status is `ready_to_charge` and add-item is invoked against that session
- **THEN** the operation MUST fail without inserting a `SaleItem`

#### Scenario: Item refused on confirmed session id
- **WHEN** `sale.add_item@1` is invoked with a `sale_session_id` whose status is `confirmed`
- **THEN** the operation MUST fail without inserting a `SaleItem` and the confirmed session MUST remain unchanged

### Requirement: Quantity positivity and units
Input `quantity` MUST be a positive Decimal string. Supported input units MUST be `gram`, `kilogram`, `unit`, and `package`. For a catalog product, `gram` MUST be accepted only when that product `sale_unit` is `kilogram`. For a free-concept line, `gram` and `kilogram` MUST normalize to `kilogram` as specified by `noncatalog-sale-item`. Incompatible catalog units MUST be rejected with `UNIT_NOT_SUPPORTED` and MUST NOT persist an item. Unsupported unit words MUST NOT be converted into `package` or `unit`.

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
For a normal `catalog` item, `catalog_unit_price_snapshot`, `unit_price`, and `line_total` MUST come from one `Product.current_price` read inside the add-item write transaction. `line_total` MUST be `quantity_normalized *` that price using `Decimal`. For a catalog override, `line_total` MUST be `quantity_normalized * unit_price` where `unit_price` is the override amount, not the snapshot. For a `free_concept` item, `line_total` MUST be `quantity_normalized * unit_price` where `unit_price` is the explicit user amount validated by the domain. Every path MUST use `Money.times`, which quantizes once to two decimal places with `ROUND_HALF_UP`. Flutter MUST NOT recompute the total. The LLM MUST NOT persist or overwrite the total. A line total that quantizes to `0.00` or less MUST NOT be persisted.

#### Scenario: Zanahoria line total
- **WHEN** `quantity_normalized` is `0.900` and Zanahoria `current_price` is `25.00` MXN
- **THEN** persisted and returned `line_total` MUST be `22.50` MXN as a decimal string plus currency `MXN`

#### Scenario: Override line total uses the charged price
- **WHEN** `quantity_normalized` is `0.900`, `catalog_unit_price_snapshot` is `20.00`, and override `unit_price` is `30.00`
- **THEN** persisted `line_total` MUST be `27.00` MXN

#### Scenario: Free-concept line total
- **WHEN** a free-concept line has `quantity_normalized` `2` and explicit unit price `18.00` MXN
- **THEN** persisted and returned `line_total` MUST be `36.00` MXN

### Requirement: Missing essential unit is not inferred
If interpretation of a catalog product lacks a unit, the system MUST clarify and MUST NOT infer `kilogram` from the product's `sale_unit`. A free-concept count default of `unit` after `match=none` is specified by `noncatalog-sale-item` and MUST NOT be applied to a unique or ambiguous catalog match. If product, quantity, or unit is ambiguous, the system MUST preserve unequivocal fields, ask only for the missing or ambiguous field, and MUST NOT persist a `SaleItem`.

#### Scenario: Quantity without unit
- **WHEN** the user message is `900 zanahoria` with no unit
- **THEN** the system MUST return a clarification, MUST NOT start from a guessed unit, and MUST NOT persist a `SaleItem`

### Requirement: Session status for this slice
`SaleSession.status` MUST be `open` after a successful start and MUST remain `open` after a successful add-item. `sale.totalize@1` MUST transition `open` → `ready_to_charge` when the session has at least one item. `sale.commit@1` MUST transition `ready_to_charge` → `confirmed` when a valid payment method is recorded. Allowed statuses MUST be `open`, `ready_to_charge`, and `confirmed`. Transitions to `pending_information`, `voided`, or `paid` MUST NOT be implemented. `confirmed` means totalized, payment recorded, and operationally complete. It MUST NOT mean Daily Close completed, bank-settled, or accounting-posted.

#### Scenario: Successful add-item keeps session open
- **WHEN** add-item commits on an open session
- **THEN** that session MUST still have `status=open` and the new `SaleItem` MUST be visible

#### Scenario: Successful totalize becomes ready_to_charge
- **WHEN** totalize commits on an open session that has items
- **THEN** that session MUST have `status=ready_to_charge` and its existing `SaleItem`s MUST still be visible

#### Scenario: Successful commit becomes confirmed
- **WHEN** commit records `cash` on a `ready_to_charge` session
- **THEN** that session MUST have `status=confirmed`, its `SaleItem`s MUST still be visible, and exactly one `Payment` MUST exist for it

### Requirement: Message-path write transaction
The public conversational operation (`POST /api/v1/lumo/messages` that adds a catalog item, completes a catalog price override, or adds a complete free-concept item) MUST use one application-owned write transaction for creating or reusing the `SaleSession` plus inserting the `SaleItem`, together with that operation's audit, outbox, and idempotency rows. `catalog.resolve_product@1` is read-only and MUST run before that write transaction. The orchestrator MUST NOT open the transaction. A failed logical mutation MUST NOT leave an orphan session created for that message, MUST NOT leave a partial item, and MUST NOT commit success audit/outbox/idempotency rows for that mutation. After a committed mutation, every related audit and `sale.item.added` outbox payload MUST reference `sale_session_id` / `sale_item_id` rows that still exist.

#### Scenario: New session rolled back with failed add-item
- **WHEN** no open session exists for the interaction context, the message workflow creates a session and writes a `SaleItem`, and the transaction fails before commit
- **THEN** neither the new `SaleSession` nor the `SaleItem` MUST remain, and no successful audit or outbox row for that message MUST remain

#### Scenario: Reused session unchanged after failed add-item
- **WHEN** an open session already exists, the message workflow reuses it, writes a `SaleItem`, and the transaction fails before commit
- **THEN** no `SaleItem` from that attempt MUST remain and the existing `SaleSession` MUST be unchanged from its pre-request committed state

#### Scenario: Resolve does not create a session
- **WHEN** product resolution is `ambiguous`, the catalog unit is missing, a grounded catalog price differs from `Product.current_price` and the merchant has not yet given a reason, a catalog override is cancelled, or a free-concept line is missing quantity, a supported unit, an explicit positive price, or a required per-kilogram basis
- **THEN** no write transaction for start/add-item MUST run and no new `SaleSession` MUST be created

#### Scenario: Complete free concept may create a session
- **WHEN** resolution is `none` and the free-concept quantity, supported unit, and explicit positive unit price are present, and a per-kilogram basis is present when the unit is gram or kilogram
- **THEN** one write transaction MUST create or reuse the open session and insert one `free_concept` `SaleItem`

#### Scenario: Accepted override reason may create a session
- **WHEN** a `catalog_price_override` pending exists and the reason turn is allowed to commit under `catalog-price-override`
- **THEN** one write transaction MUST create or reuse the open session and insert exactly one catalog `SaleItem`

#### Scenario: Committed integrity rows stay consistent
- **WHEN** a message-path add-item commits
- **THEN** the session, item, message idempotency row, `sale.start@1`/`sale.add_item@1` audit rows, and `sale.item.added` outbox row MUST all exist together, and audit/outbox payloads MUST reference those live ids

### Requirement: Sale-mutation reset stays consistent
Test or reset utilities that intentionally remove committed sale mutations MUST delete `payments`, `sale_items`, and `sale_sessions` together with related `audit_events` (`sale.start@1`, `sale.add_item@1`, `sale.totalize@1`, `sale.commit@1`), `outbox_events` (`sale.item.added`, `sale.ready_to_charge`, `sale.confirmed`, `payment.recorded`), and `idempotency_records` (`lumo.message.add_sale_item`, `lumo.message.totalize_sale`, `lumo.message.commit_sale`) in one transaction, or they MUST roll the original transaction back. They MUST NOT delete only sales (and/or only idempotency) rows. After cleanup or rollback, no audit or outbox row MAY reference a `sale_session_id`, `sale_item_id`, or `payment_id` that does not exist.

#### Scenario: Cleanup does not leave orphan integrity
- **WHEN** a test helper removes a tenant's committed sale mutations
- **THEN** related sale audit, sale and payment outbox, and message idempotency rows MUST also be gone, and no remaining audit/outbox payload MAY point at a missing session, item, or payment

### Requirement: Session mutations lock the SaleSession row
When an existing `SaleSession` is the target of add-item, totalize, or commit, the repository MUST load it with a row-level lock (`SELECT ... FOR UPDATE` / `with_for_update()`) before the workflow inspects `status`, inserts items, inserts a `Payment`, or changes status. Concurrent add-item, totalize, and commit against that row MUST serialize. Add-item vs commit MUST follow CASE A / CASE B in `conversational-sale-runtime`: locking `ready_to_charge` first denies the add; a committed `confirmed` session is no longer active, so a later add-item lookup MAY start a new open session. The unique index MUST remain the `0003` expression `(business_id, actor_id, COALESCE(conversation_id, '')) WHERE status IN ('open', 'ready_to_charge')`. Migration `0004` MUST NOT add `confirmed` to that predicate.

#### Scenario: Lock before status check
- **WHEN** add-item, totalize, or commit runs against an existing session
- **THEN** the session row MUST be locked before the workflow accepts or rejects based on `status`

#### Scenario: Unique active index keeps COALESCE and excludes confirmed
- **WHEN** Alembic `0004` is applied
- **THEN** at most one `open` or `ready_to_charge` session MUST exist per `(business_id, actor_id, COALESCE(conversation_id, ''))`, and multiple `confirmed` sessions MUST be allowed for that same context

### Requirement: Session total is derived from items
`session_total` MUST equal the Decimal sum of the session's persisted `SaleItem.line_total` values using the existing money helper. The session row MUST NOT store a separately mutated total. Flutter and the LLM MUST NOT supply or overwrite that total.

#### Scenario: Two-item derived total
- **WHEN** persisted items have line totals `22.50` and `10.00` MXN
- **THEN** `session_total.amount` MUST be `32.50` MXN

### Requirement: Confirmed session stores operational day membership
`SaleSession` MUST include nullable `operational_day_id` and `confirmed_at` in addition to its existing fields. `sale.commit@1` MUST set both when it transitions `ready_to_charge` → `confirmed`, and MUST leave them NULL for `open` and `ready_to_charge`. The referenced OperationalDay MUST belong to the same `business_id`. Existing items and the single `Payment` MUST remain. The active-session unique index MUST stay limited to `open` and `ready_to_charge`. `confirmed` MUST still mean operational sale completion, not Daily Close.

#### Scenario: Successful commit attaches the day
- **WHEN** commit records `cash` on a `ready_to_charge` session
- **THEN** that session MUST have `status=confirmed`, a non-null `operational_day_id` and `confirmed_at`, its `SaleItem`s MUST still be visible, and exactly one `Payment` MUST exist for it

#### Scenario: Next open session is not attached
- **WHEN** a product utterance after `confirmed` starts a new `open` session on the same `conversation_id`
- **THEN** the new session MUST have `operational_day_id` NULL until its own confirming commit, and the previous confirmed session MUST keep its original `operational_day_id`

