## MODIFIED Requirements

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
`SaleItem` MUST include `id`, `business_id`, `sale_session_id`, `product_id`, `product_name_snapshot`, `quantity_input`, `unit_input`, `quantity_normalized`, `unit_normalized`, `unit_price`, `currency`, `line_total`, `created_at`, and `updated_at`. Quantities and money MUST be `numeric`/`Decimal`. A new `SaleItem` MUST belong to an `open` session in the same tenant. A `SaleItem` already persisted on a session that later becomes `ready_to_charge` or `confirmed` MUST remain. New items MUST NOT be appended after `ready_to_charge` or onto a `confirmed` session. After `confirmed`, a conversational add-item for the same interaction context MUST attach to a new `open` session.

#### Scenario: Item stored after add
- **WHEN** `sale.add_item@1` commits for Zanahoria
- **THEN** a `SaleItem` row MUST exist with `product_name_snapshot=Zanahoria` and the server-calculated `line_total`

#### Scenario: Item refused after totalize
- **WHEN** the session status is `ready_to_charge` and add-item is invoked against that session
- **THEN** the operation MUST fail without inserting a `SaleItem`

#### Scenario: Item refused on confirmed session id
- **WHEN** `sale.add_item@1` is invoked with a `sale_session_id` whose status is `confirmed`
- **THEN** the operation MUST fail without inserting a `SaleItem` and the confirmed session MUST remain unchanged

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
