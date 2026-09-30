## MODIFIED Requirements

### Requirement: Session status for this slice
`SaleSession.status` MUST be `open` after a successful start and MUST remain `open` after a successful add-item. `sale.totalize@1` MUST transition `open` → `ready_to_charge` when the session has at least one item. `sale.commit@1` MUST transition `ready_to_charge` → `confirmed` when a valid payment method is recorded. `sale.void@1` MUST transition `confirmed` → `voided` when the sale's OperationalDay is open. Allowed statuses MUST be `open`, `ready_to_charge`, `confirmed`, and `voided`. Transitions to `pending_information` or `paid` MUST NOT be implemented. `confirmed` means totalized, payment recorded, and operationally complete. `voided` means a previously confirmed sale that no longer contributes to live operational aggregates. Neither status means Daily Close completed, bank-settled, or accounting-posted.

#### Scenario: Successful add-item keeps session open
- **WHEN** add-item commits on an open session
- **THEN** that session MUST still have `status=open` and the new `SaleItem` MUST be visible

#### Scenario: Successful totalize becomes ready_to_charge
- **WHEN** totalize commits on an open session that has items
- **THEN** that session MUST have `status=ready_to_charge` and its existing `SaleItem`s MUST still be visible

#### Scenario: Successful commit becomes confirmed
- **WHEN** commit records `cash` on a `ready_to_charge` session
- **THEN** that session MUST have `status=confirmed`, its `SaleItem`s MUST still be visible, and exactly one `Payment` MUST exist for it

#### Scenario: Successful void becomes voided
- **WHEN** `sale.void@1` commits on a `confirmed` session whose day is open
- **THEN** that session MUST have `status=voided`, its `SaleItem`s and `Payment` MUST still be visible, and void metadata MUST be non-null

### Requirement: Session mutations lock the SaleSession row
When an existing `SaleSession` is the target of add-item, remove-item, totalize, commit, or void, the repository MUST load it with a row-level lock (`SELECT ... FOR UPDATE` / `with_for_update()`) before the workflow inspects `status`, inserts or deletes items, inserts a `Payment`, or changes status. Concurrent mutations against that row MUST serialize. Add-item vs commit MUST follow CASE A / CASE B in `conversational-sale-runtime`: locking `ready_to_charge` first denies the add; a committed `confirmed` session is no longer active, so a later add-item lookup MAY start a new open session. The unique index MUST remain the expression `(business_id, actor_id, COALESCE(conversation_id, '')) WHERE status IN ('open', 'ready_to_charge')`. `confirmed` and `voided` MUST NOT be added to that predicate.

#### Scenario: Lock before status check
- **WHEN** add-item, remove-item, totalize, commit, or void runs against an existing session
- **THEN** the session row MUST be locked before the workflow accepts or rejects based on `status`

#### Scenario: Unique active index excludes confirmed and voided
- **WHEN** the sale-corrections migration is applied
- **THEN** at most one `open` or `ready_to_charge` session MUST exist per `(business_id, actor_id, COALESCE(conversation_id, ''))`, and multiple `confirmed` or `voided` sessions MUST be allowed for that same context

### Requirement: Confirmed session stores operational day membership
`SaleSession` MUST include nullable `operational_day_id` and `confirmed_at` in addition to its existing fields. `sale.commit@1` MUST set both when it transitions `ready_to_charge` → `confirmed`, and MUST leave them NULL for `open` and `ready_to_charge`. `sale.void@1` MUST keep both non-null when transitioning `confirmed` → `voided`. The referenced OperationalDay MUST belong to the same `business_id`. Existing items and the single `Payment` MUST remain. The active-session unique index MUST stay limited to `open` and `ready_to_charge`. `confirmed` and `voided` MUST still mean operational sale completion or its audited cancellation, not Daily Close.

#### Scenario: Successful commit attaches the day
- **WHEN** commit records `cash` on a `ready_to_charge` session
- **THEN** that session MUST have `status=confirmed`, a non-null `operational_day_id` and `confirmed_at`, its `SaleItem`s MUST still be visible, and exactly one `Payment` MUST exist for it

#### Scenario: Void keeps day membership
- **WHEN** a confirmed session is voided
- **THEN** `operational_day_id` and `confirmed_at` MUST remain the values set at commit

#### Scenario: Next open session is not attached
- **WHEN** a product utterance after `confirmed` starts a new `open` session on the same `conversation_id`
- **THEN** the new session MUST have `operational_day_id` NULL until its own confirming commit, and the previous confirmed session MUST keep its original `operational_day_id`

### Requirement: Sale-mutation reset stays consistent
Test or reset utilities that intentionally remove committed sale mutations MUST delete `payments`, `sale_items`, and `sale_sessions` together with related `audit_events` (`sale.start@1`, `sale.add_item@1`, `sale.remove_item@1`, `sale.totalize@1`, `sale.commit@1`, `sale.void@1`), `outbox_events` (`sale.item.added`, `sale.item.removed`, `sale.ready_to_charge`, `sale.confirmed`, `sale.voided`, `payment.recorded`), related `business_events` (`sale_confirmed`, `sale_voided`), and `idempotency_records` (`lumo.message.add_sale_item`, `lumo.message.remove_sale_item`, `lumo.message.totalize_sale`, `lumo.message.commit_sale`, `lumo.message.void_sale`) in one transaction, or they MUST roll the original transaction back. They MUST NOT delete only sales (and/or only idempotency) rows. After cleanup or rollback, no audit or outbox row MAY reference a `sale_session_id`, `sale_item_id`, or `payment_id` that does not exist.

#### Scenario: Cleanup does not leave orphan integrity
- **WHEN** a test helper removes a tenant's committed sale mutations
- **THEN** related sale audit, sale and payment outbox, business events, and message idempotency rows MUST also be gone, and no remaining audit/outbox payload MAY point at a missing session, item, or payment

## ADDED Requirements

### Requirement: Void metadata columns on SaleSession
A `voided` session MUST store `voided_at`, `voided_by_actor_id`, and non-empty `void_reason`. Non-voided sessions MUST keep those columns NULL. A CHECK MUST reject `voided` without complete void metadata and MUST reject non-voided rows that carry void metadata.

#### Scenario: Open session has no void fields
- **WHEN** a session is `open`, `ready_to_charge`, or `confirmed`
- **THEN** `voided_at`, `voided_by_actor_id`, and `void_reason` MUST be NULL

#### Scenario: Voided session requires reason
- **WHEN** a write attempts `status=voided` with a null or blank `void_reason`
- **THEN** the database or workflow MUST reject the write

### Requirement: Persisted sale_revision on SaleSession
`SaleSession` MUST include a server-authored integer `sale_revision` persisted on `sales.sale_sessions`. New sessions MUST initialize `sale_revision` to `1`. The value MUST be `>= 1` and MUST NOT be supplied by Flutter or the LLM as source of truth. A successful `sale.remove_item@1` MUST set `sale_revision = sale_revision + 1` in the same locked write transaction when the session status before the remove was `ready_to_charge` (including when emptying demotes to `open`). A successful remove from `open` MUST leave `sale_revision` unchanged. Add-item, totalize, commit, and void MUST NOT advance `sale_revision`. This column exists for payment-action cart staleness; it is not a general optimistic lock for every mutation.

#### Scenario: New session starts at revision 1
- **WHEN** a new `SaleSession` is created
- **THEN** persisted `sale_revision` MUST be `1`

#### Scenario: ready_to_charge remove advances revision
- **WHEN** a `ready_to_charge` session with `sale_revision=1` successfully removes an item
- **THEN** persisted `sale_revision` MUST become `2` in the same transaction

#### Scenario: open remove leaves revision unchanged
- **WHEN** an `open` session with `sale_revision=1` successfully removes an item
- **THEN** persisted `sale_revision` MUST remain `1`
