## MODIFIED Requirements

### Requirement: SaleItem persistence
`SaleItem` MUST include `id`, `business_id`, `sale_session_id`, `source_type`, `product_id`, `product_name_snapshot`, `quantity_input`, `unit_input`, `quantity_normalized`, `unit_normalized`, `unit_price`, `currency`, `line_total`, `created_at`, and `updated_at`. `source_type` MUST be `catalog` or `free_concept`. A `catalog` item MUST have non-null `product_id`. A `free_concept` item MUST have `product_id` NULL and a non-empty `product_name_snapshot`. That snapshot MUST be the display span defined by `noncatalog-sale-item`, not `normalize_product_name`. Quantities and money MUST be `numeric`/`Decimal`. A new `SaleItem` MUST belong to an `open` session in the same tenant. A `SaleItem` already persisted on a session that later becomes `ready_to_charge` or `confirmed` MUST remain. New items MUST NOT be appended after `ready_to_charge` or onto a `confirmed` session. After `confirmed`, a conversational add-item for the same interaction context MUST attach to a new `open` session. This change MUST NOT add an edit or delete path for either source.

#### Scenario: Item stored after add
- **WHEN** `sale.add_item@1` commits for Zanahoria
- **THEN** a `SaleItem` row MUST exist with `source_type=catalog`, `product_name_snapshot=Zanahoria`, a non-null `product_id`, and the server-calculated `line_total`

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

### Requirement: Deterministic line total
For a `catalog` item, `line_total` MUST be calculated in backend domain logic as `quantity_normalized * current_price` using `Decimal`. For a `free_concept` item, `line_total` MUST be calculated as `quantity_normalized * unit_price` where `unit_price` is the explicit user amount validated by the domain. Both paths MUST use `Money.times`, which quantizes once to two decimal places with `ROUND_HALF_UP`. Flutter MUST NOT recompute the total. The LLM MUST NOT persist or overwrite the total. A line total that quantizes to `0.00` or less MUST NOT be persisted.

#### Scenario: Zanahoria line total
- **WHEN** `quantity_normalized` is `0.900` and Zanahoria `current_price` is `25.00` MXN
- **THEN** persisted and returned `line_total` MUST be `22.50` MXN as a decimal string plus currency `MXN`

#### Scenario: Free-concept line total
- **WHEN** a free-concept line has `quantity_normalized` `2` and explicit unit price `18.00` MXN
- **THEN** persisted and returned `line_total` MUST be `36.00` MXN

### Requirement: Missing essential unit is not inferred
If interpretation of a catalog product lacks a unit, the system MUST clarify and MUST NOT infer `kilogram` from the product's `sale_unit`. A free-concept count default of `unit` after `match=none` is specified by `noncatalog-sale-item` and MUST NOT be applied to a unique or ambiguous catalog match. If product, quantity, or unit is ambiguous, the system MUST preserve unequivocal fields, ask only for the missing or ambiguous field, and MUST NOT persist a `SaleItem`.

#### Scenario: Quantity without unit
- **WHEN** the user message is `900 zanahoria` with no unit
- **THEN** the system MUST return a clarification, MUST NOT start from a guessed unit, and MUST NOT persist a `SaleItem`

### Requirement: Message-path write transaction
The public conversational operation (`POST /api/v1/lumo/messages` that adds a catalog item or a complete free-concept item) MUST use one application-owned write transaction for creating or reusing the `SaleSession` plus inserting the `SaleItem`, together with that operation's audit, outbox, and idempotency rows. `catalog.resolve_product@1` is read-only and MUST run before that write transaction. The orchestrator MUST NOT open the transaction. A failed logical mutation MUST NOT leave an orphan session created for that message, MUST NOT leave a partial item, and MUST NOT commit success audit/outbox/idempotency rows for that mutation. After a committed mutation, every related audit and `sale.item.added` outbox payload MUST reference `sale_session_id` / `sale_item_id` rows that still exist.

#### Scenario: New session rolled back with failed add-item
- **WHEN** no open session exists for the interaction context, the message workflow creates a session and writes a `SaleItem`, and the transaction fails before commit
- **THEN** neither the new `SaleSession` nor the `SaleItem` MUST remain, and no successful audit or outbox row for that message MUST remain

#### Scenario: Reused session unchanged after failed add-item
- **WHEN** an open session already exists, the message workflow reuses it, writes a `SaleItem`, and the transaction fails before commit
- **THEN** no `SaleItem` from that attempt MUST remain and the existing `SaleSession` MUST be unchanged from its pre-request committed state

#### Scenario: Resolve does not create a session
- **WHEN** product resolution is `ambiguous`, the catalog unit is missing, a grounded catalog price differs from `Product.current_price`, or a free-concept line is missing quantity, a supported unit, an explicit positive price, or a required per-kilogram basis
- **THEN** no write transaction for start/add-item MUST run and no new `SaleSession` MUST be created

#### Scenario: Complete free concept may create a session
- **WHEN** resolution is `none` and the free-concept quantity, supported unit, and explicit positive unit price are present, and a per-kilogram basis is present when the unit is gram or kilogram
- **THEN** one write transaction MUST create or reuse the open session and insert one `free_concept` `SaleItem`

#### Scenario: Committed integrity rows stay consistent
- **WHEN** a message-path add-item commits
- **THEN** the session, item, message idempotency row, `sale.start@1`/`sale.add_item@1` audit rows, and `sale.item.added` outbox row MUST all exist together, and audit/outbox payloads MUST reference those live ids
