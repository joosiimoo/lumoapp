## MODIFIED Requirements

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
