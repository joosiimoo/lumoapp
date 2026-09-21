## MODIFIED Requirements

### Requirement: Sale integrity rows match live mutations
Committed conversational sale mutations MUST keep `sales.sale_sessions`, `sales.sale_items`, related `audit.audit_events`, `platform.outbox_events`, and `platform.idempotency_records` transactionally consistent. Test/reset helpers that remove those mutations MUST delete the related integrity rows in the same transaction, including `sale.totalize@1` audit, `sale.ready_to_charge` outbox, and `lumo.message.totalize_sale` idempotency.

#### Scenario: No orphan sale outbox
- **WHEN** a `sale.item.added` or `sale.ready_to_charge` outbox row exists for a tenant
- **THEN** the referenced `sale_session_id` and, when present, `sale_item_id` MUST exist unless the entire mutation was rolled back (in which case the outbox row MUST NOT exist)

## ADDED Requirements

### Requirement: SaleSession status persistence
`sales.sale_sessions.status` MUST allow `open` and `ready_to_charge` only. `conversation_id` MUST remain `VARCHAR(128) NULL` as created in `0002_catalog_sales`. Migration `0003` MUST drop `uq_sale_sessions_open_context` and recreate uniqueness with the same expression:

```sql
CREATE UNIQUE INDEX uq_sale_sessions_active_context
ON sales.sale_sessions (business_id, actor_id, COALESCE(conversation_id, ''))
WHERE status IN ('open', 'ready_to_charge');
```

It MUST NOT change the column type, MUST NOT replace `COALESCE(conversation_id, '')` with a UUID coalesce, and MUST NOT add a duplicated mutable total column. Schemas `operations`, `workflow`, and `memory` MUST remain absent.

#### Scenario: Status check
- **WHEN** Alembic migrations for this change complete
- **THEN** inserting a `SaleSession` with `status=confirmed` MUST fail, and two `open` or mixed `open`/`ready_to_charge` rows MUST NOT exist for the same `(business_id, actor_id, COALESCE(conversation_id, ''))`

#### Scenario: Totalize rollback is consistent
- **WHEN** totalize writes a status change, audit, outbox, and idempotency row and the transaction fails before commit
- **THEN** the session MUST remain `open`, and no `sale.ready_to_charge` outbox or successful totalize audit/idempotency completion MUST remain
