## ADDED Requirements

### Requirement: Tool sale.remove_item@1
`ToolRegistry` MUST register `sale.remove_item@1` as a write tool. Input MUST include `sale_session_id` and `sale_item_id` and MUST NOT accept a client-supplied total or remaining-item list. Output MUST expose the updated session status, remaining items, and derived total. Permission MUST follow the existing sale mutation permission family. Idempotency MUST be required. `business_id` and `actor_id` MUST come from `TenantContext`.

#### Scenario: Registered remove tool
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `sale.remove_item@1` with `side_effect=write` and `requires_idempotency=true`

#### Scenario: Missing item does not invent a delete
- **WHEN** `sale_item_id` is not on the locked session
- **THEN** the tool MUST fail without deleting other items and without changing status

### Requirement: Tool sale.void@1
`ToolRegistry` MUST register `sale.void@1` as a write tool. Input MUST include `sale_session_id` and, on the mutate path, `void_reason`, and MUST NOT accept amounts, expected cash, or a client status. Output MUST expose voided status, void metadata, and server before/after impact fields used by confirmation UI when relevant. Idempotency MUST be required. Behavior MUST be: `confirmed` on an open day mutates to `voided`; already `voided` returns a non-mutating read-back; any other status or a `confirmed` sale on a closed day fails without mutation.

#### Scenario: Registered void tool
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `sale.void@1` with `side_effect=write` and `requires_idempotency=true`

#### Scenario: Blank reason does not void a confirmed sale
- **WHEN** the session is `confirmed` on an open day and `void_reason` is empty or whitespace
- **THEN** no status change MUST occur

#### Scenario: Already voided is read-back not refuse
- **WHEN** the session is already `voided` and `sale.void@1` runs with a new key
- **THEN** the tool MUST return the voided sale read-back without a second `sale_voided` event or transition audit

### Requirement: Remove and void share message-level idempotency
Message and UI paths for remove and void MUST use idempotency operation types `lumo.message.remove_sale_item` and `lumo.message.void_sale` (and matching UI action keys). Same-key same-hash replay MUST return the original body. Different-key after a successful void MUST be a non-mutating voided read-back with no new audit/outbox/memory side effects. Different-key after a successful remove of an already-absent item MUST NOT recreate the item.

#### Scenario: Void replay is stable
- **WHEN** the same void idempotency key and body are posted twice
- **THEN** exactly one `voided` transition and one `sale_voided` event MUST exist for that session

#### Scenario: Different-key void after voided is read-back
- **WHEN** the session is `voided` and a different void idempotency key is posted
- **THEN** exactly one `sale_voided` event MUST still exist and no additional void transition audit MUST be written

### Requirement: Orchestrator delegates remove and void writes
The orchestrator MUST NOT open the remove or void write transaction. `RemoveSaleItem` and `VoidSaleSession` workflows MUST own the lock and outcome selection. Only the void mutate path MAY write audit, outbox, memory, and daily-close maintenance. The voided read-back path MUST NOT write those side effects. Idempotency completion for a first successful mutate MUST follow existing patterns; read-back MUST NOT insert a new void transition idempotency record when treated as current-state read-back with a different key.

#### Scenario: Failed void leaves no partial void
- **WHEN** void writes status then fails before commit
- **THEN** the session MUST remain `confirmed`, void metadata MUST be absent, and no `sale_voided` event MUST remain
