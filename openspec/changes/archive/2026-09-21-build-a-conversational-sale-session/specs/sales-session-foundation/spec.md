## MODIFIED Requirements

### Requirement: One active session per interaction context
Interaction context MUST be `(business_id, actor_id, conversation_id)` when `conversation_id` is present, otherwise `(business_id, actor_id)`. At most one `SaleSession` with status `open` or `ready_to_charge` MUST exist per interaction context. `sale.start@1` MUST reuse the `open` session when present and MUST create one when no active session exists. If a `ready_to_charge` session already exists for that context, `sale.start@1` MUST NOT create a second session and MUST NOT treat that session as reusable for add-item. A message with a new `conversation_id` MUST NOT reuse an active session that has a different `conversation_id` or a NULL `conversation_id`. Confirmation, void, payment, and completion MUST NOT be implemented here.

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

### Requirement: SaleItem persistence
`SaleItem` MUST include `id`, `business_id`, `sale_session_id`, `product_id`, `product_name_snapshot`, `quantity_input`, `unit_input`, `quantity_normalized`, `unit_normalized`, `unit_price`, `currency`, `line_total`, `created_at`, and `updated_at`. Quantities and money MUST be `numeric`/`Decimal`. A new `SaleItem` MUST belong to an `open` session in the same tenant. A `SaleItem` already persisted on a session that later becomes `ready_to_charge` MUST remain; new items MUST NOT be appended after that transition.

#### Scenario: Item stored after add
- **WHEN** `sale.add_item@1` commits for Zanahoria
- **THEN** a `SaleItem` row MUST exist with `product_name_snapshot=Zanahoria` and the server-calculated `line_total`

#### Scenario: Item refused after totalize
- **WHEN** the session status is `ready_to_charge` and add-item is invoked
- **THEN** the operation MUST fail without inserting a `SaleItem`

### Requirement: Session status for this slice
`SaleSession.status` MUST be `open` after a successful start and MUST remain `open` after a successful add-item. `sale.totalize@1` MUST transition `open` → `ready_to_charge` when the session has at least one item. Allowed statuses in this change MUST be only `open` and `ready_to_charge`. Transitions to confirmed, pending_information, voided, or paid MUST NOT be implemented here.

#### Scenario: Successful add-item keeps session open
- **WHEN** add-item commits on an open session
- **THEN** that session MUST still have `status=open` and the new `SaleItem` MUST be visible

#### Scenario: Successful totalize becomes ready_to_charge
- **WHEN** totalize commits on an open session that has items
- **THEN** that session MUST have `status=ready_to_charge` and its existing `SaleItem`s MUST still be visible

### Requirement: Sale-mutation reset stays consistent
Test or reset utilities that intentionally remove committed sale mutations MUST delete `sale_items` and `sale_sessions` together with related `audit_events` (`sale.start@1`, `sale.add_item@1`, `sale.totalize@1`), `outbox_events` (`sale.item.added`, `sale.ready_to_charge`), and `idempotency_records` (`lumo.message.add_sale_item`, `lumo.message.totalize_sale`) in one transaction, or they MUST roll the original transaction back. They MUST NOT delete only sales (and/or only idempotency) rows. After cleanup or rollback, no audit or outbox row MAY reference a `sale_session_id` or `sale_item_id` that does not exist.

#### Scenario: Cleanup does not leave orphan integrity
- **WHEN** a test helper removes a tenant's committed sale mutations
- **THEN** related sale audit, `sale.item.added` and `sale.ready_to_charge` outbox, and message idempotency rows MUST also be gone, and no remaining audit/outbox payload MAY point at a missing session or item

## ADDED Requirements

### Requirement: Session mutations lock the SaleSession row
When an existing `SaleSession` is the target of add-item or totalize, the repository MUST load it with a row-level lock (`SELECT ... FOR UPDATE` / `with_for_update()`) before the workflow inspects `status` or inserts items. Concurrent add-item and totalize against that row MUST serialize. The unique index MUST remain the `0002_catalog_sales` expression `(business_id, actor_id, COALESCE(conversation_id, ''))` because `conversation_id` is `VARCHAR(128) NULL`, not UUID; `0003` MUST only widen `WHERE status IN ('open', 'ready_to_charge')`.

#### Scenario: Lock before status check
- **WHEN** add-item or totalize runs against an existing session
- **THEN** the session row MUST be locked before the workflow accepts or rejects based on `status`

#### Scenario: Unique active index keeps COALESCE
- **WHEN** Alembic `0003` is applied
- **THEN** at most one `open` or `ready_to_charge` session MUST exist per `(business_id, actor_id, COALESCE(conversation_id, ''))`

### Requirement: Session total is derived from items
`session_total` MUST equal the Decimal sum of the session's persisted `SaleItem.line_total` values using the existing money helper. The session row MUST NOT store a separately mutated total. Flutter and the LLM MUST NOT supply or overwrite that total.

#### Scenario: Two-item derived total
- **WHEN** persisted items have line totals `22.50` and `10.00` MXN
- **THEN** `session_total.amount` MUST be `32.50` MXN
