## MODIFIED Requirements

### Requirement: Tool sale.start@1
`ToolRegistry` MUST register `sale.start@1` as a write tool. Input MUST be `{ "conversation_id": string|null }`. Output MUST be `{ "sale_session_id": uuid, "status": "open"|"ready_to_charge", "created": boolean, "item_count": integer }`. Permission MUST be `sale.create`. Idempotency MUST be required when start is invoked as its own public operation. When `conversation_id` is present, the tool MUST reuse the open session for `(business_id, actor_id, conversation_id)` and MUST persist that id on `SaleSession`. If a `ready_to_charge` session exists for that context, start MUST NOT create another session. When composed on the message path, start/reuse MUST participate in the workflow write transaction (see message-path transaction requirement) and MUST NOT commit an empty session before add-item.

#### Scenario: Start is idempotent
- **WHEN** `sale.start@1` is invoked twice as its own public operation with the same tenant, actor, conversation, key, and payload
- **THEN** one `SaleSession` MUST exist and both results MUST return the same `sale_session_id`

#### Scenario: Same conversation reuses one session
- **WHEN** two successful message-path add-item mutations use the same tenant, actor, and `conversation_id`
- **THEN** exactly one open `SaleSession` MUST exist for that context and both items MUST belong to it

#### Scenario: Different conversations isolate sessions
- **WHEN** two successful message-path add-item mutations use different `conversation_id`s for the same tenant and actor
- **THEN** two open `SaleSession`s MUST exist and neither mutation MUST reuse the other's session

### Requirement: Tool sale.add_item@1
`ToolRegistry` MUST register `sale.add_item@1` as a write tool. Input MUST be `{ "sale_session_id": uuid, "product_id": uuid, "quantity": decimal-string, "unit": "gram"|"kilogram"|"unit"|"package" }`. Output MUST include `sale_session_id`, `sale_item_id`, `product_id`, `product_name`, `quantity_input`, `unit_input`, `quantity_normalized`, `unit_normalized`, `unit_price`, `line_total`, `session_item_count`, and `session_total` (money as decimal string plus `MXN`). Permission MUST be `sale.create`. Idempotency MUST be required when add-item is invoked as its own public operation. The tool MUST re-read the product, reject inactive/missing products, lock the session row when it exists, reject a session that is not `open`, normalize quantity, calculate `line_total`, persist, and audit. On the message path, those writes MUST share the workflow transaction with session create/reuse.

#### Scenario: Add 900 grams of Zanahoria
- **WHEN** the tool runs with the seeded Zanahoria `product_id`, `quantity=900`, and `unit=gram` on an open session
- **THEN** it MUST persist `quantity_normalized=0.900`, `unit_normalized=kilogram`, `unit_price.amount=25.00`, `line_total.amount=22.50`, and an audit event in the same committed state

#### Scenario: Replay identical add-item
- **WHEN** the same tenant resubmits `sale.add_item@1` with the same idempotency key and payload hash
- **THEN** the original item id and body MUST be returned and a second `SaleItem` MUST NOT be created

#### Scenario: Add two Galleta A
- **WHEN** the tool runs with the seeded Galleta A `product_id`, `quantity=2`, and `unit=unit` on an open session
- **THEN** it MUST persist `quantity_normalized=2`, `unit_normalized=unit`, `unit_price.amount=12.00`, and `line_total.amount=24.00`

### Requirement: Orchestrator delegates; workflow owns the write transaction
For intent `add_sale_item` with a resolvable product and a complete unit (explicit, or inferred only for `unit`/`package` products after unique resolve), the orchestrator MUST request interpretation and policy, then invoke the application add-item workflow. For intent `totalize_sale`, it MUST invoke `TotalizeSaleSession` and MUST NOT run add-item. It MUST NOT open ORM sessions or database transactions. The add-item workflow MUST: (1) run `catalog.resolve_product@1` as a read **before** any write transaction; (2) if unique and the session is `open` or absent, open one write transaction that **locks** the existing active `SaleSession` when present (`SELECT ... FOR UPDATE`), re-reads status, creates or reuses the open session only if still open, and inserts the `SaleItem` using `sale.start@1` / `sale.add_item@1` semantics without an intervening commit; (3) write audit, outbox, and the message-level idempotency record in that same transaction; (4) compose `sale_item_added@1` only after commit. If the locked session is `ready_to_charge`, it MUST deny without writing an item. If resolve is ambiguous or none, or policy is not `allow`, it MUST clarify or deny without opening the write transaction. Committing `sale.start@1` before `sale.add_item@1` on this path is forbidden.

#### Scenario: Golden path sequences tools
- **WHEN** Inicio posts `900gr zanahoria` for Carrota
- **THEN** resolve MUST run first, start/reuse and add-item MUST commit together, and a `SaleItem` MUST exist only after that commit

#### Scenario: Ambiguity stops before mutation
- **WHEN** product resolution is `ambiguous` or `none`
- **THEN** `sale.start@1` and `sale.add_item@1` MUST NOT run as a result of that message and no `SaleSession` MUST be created for it

#### Scenario: Failed add-item does not leave a new session
- **WHEN** the message would create a new `SaleSession` and add-item fails before commit
- **THEN** neither the session nor the item MUST remain

#### Scenario: Totalize is a separate workflow
- **WHEN** Inicio posts `totalizar` for an open session with items
- **THEN** `TotalizeSaleSession` MUST run, `sale.add_item@1` MUST NOT run, and `sale_summary@1` MUST be composed only after commit

### Requirement: Scripted interpreter for local and test
Local and test runtimes MUST use a non-vendor interpreter that can produce a valid `AgentDecision` for catalog add-item utterances, unit-only follow-ups, and totalize synonyms `totalizar`, `total`, and `el total` (trimmed, case-insensitive). A real LLM vendor SDK MUST NOT be required for the acceptance tests of this capability. The interpreter MUST remain compatible with a future `LLMProvider` (no repository or DB access). Count-product completion MUST NOT be hardcoded in the interpreter from catalog prices; missing unit for a possible count product MUST still reach application resolve.

#### Scenario: Fake provider still boots
- **WHEN** no vendor LLM is configured
- **THEN** health MAY report fake/non-ready and `POST /api/v1/lumo/messages` MUST still execute the golden path via the scripted interpreter

#### Scenario: Totalize interpretation
- **WHEN** the scripted interpreter receives `totalizar`
- **THEN** `AgentDecision` MUST have `intent=totalize_sale` and `candidate_tool=sale.totalize@1`

### Requirement: Local seed at API boot
When `APP_ENV=local`, API startup MUST run the idempotent Carrota seed (Zanahoria, Tomate, Galleta A) and commit it. Tests MUST call the same seed helper explicitly. Staging and production MUST NOT insert that seed automatically.

#### Scenario: Local boot seeds catalog
- **WHEN** the API starts with `APP_ENV=local` against a migrated database
- **THEN** business Carrota and active products Zanahoria, Tomate, and Galleta A MUST exist for that tenant with the seed prices

### Requirement: Message-level idempotency
`POST /api/v1/lumo/messages` MUST treat `Idempotency-Key` as the key for the whole message workflow. Add-item MUST use `operation_type` `lumo.message.add_sale_item`. Totalize MUST use `operation_type` `lumo.message.totalize_sale`. These MUST NOT share one operation type.

#### Scenario: Replay of the golden message
- **WHEN** the same tenant resubmits `"900gr zanahoria"` with the same message idempotency key and payload hash
- **THEN** the original session id, item id, and body MUST be returned and a second `SaleItem` MUST NOT be created

#### Scenario: Replay of totalize
- **WHEN** the same tenant resubmits `totalizar` with the same message idempotency key and payload hash after a successful totalize
- **THEN** the original session id and `sale_summary@1` body MUST be returned, status MUST remain `ready_to_charge`, and a second `sale.ready_to_charge` outbox row MUST NOT be created

#### Scenario: Different-key totalize does not persist idempotency
- **WHEN** the session is already `ready_to_charge` and the tenant posts `totalizar` with a new idempotency key
- **THEN** current `sale_summary@1` MUST be returned and no new `lumo.message.totalize_sale` row MUST exist for that key

## ADDED Requirements

### Requirement: AgentDecision extension for totalize
`AgentDecision` MUST keep existing add-item fields. Intent `totalize_sale` MUST be used for approved totalize synonyms. `candidate_tool` MUST be `sale.totalize@1` or null. Invalid provider output MUST still be discarded with no mutation.

#### Scenario: Golden totalize interpretation
- **WHEN** the scripted interpreter receives `el total`
- **THEN** `AgentDecision` MUST have `intent=totalize_sale` and `candidate_tool=sale.totalize@1`

### Requirement: Tool sale.totalize@1
`ToolRegistry` MUST register `sale.totalize@1` as a write tool. Input MUST be `{ "conversation_id": string|null }`. Output MUST include `sale_session_id`, `status` (`ready_to_charge`), `item_count`, `currency`, `subtotal`, `total`, and `items` (each with product name, normalized quantity, canonical unit, unit price, and line total). Permission MUST be `sale.create`. Idempotency MUST be required for the **transition** when totalize is invoked as its own public operation. On the message path, a transitioning totalize, audit, outbox, and message idempotency MUST share one application-owned write transaction after locking the session row. The tool MUST lock the active session for the interaction context, then:

- if `status=open` and at least one `SaleItem` exists: sum persisted line totals with Decimal, persist `ready_to_charge`, write transition audit and `sale.ready_to_charge` outbox, complete `lumo.message.totalize_sale`, and MUST NOT record payment;
- if `status=ready_to_charge`: return the current summary as a stable read-back with no status change, no second outbox, no transition audit, and no new idempotency record;
- if no session or zero items: deny without mutation.

`SALE-003` MUST apply `open` + ≥1 item to the **transition** only. Compose `sale_summary@1` after commit on the transition path, and from current persisted items on the read-back path.

#### Scenario: Totalize open session
- **WHEN** `sale.totalize@1` runs for an open Carrota session with Zanahoria `22.50` and Tomate `10.00`
- **THEN** it MUST persist `status=ready_to_charge`, return `total.amount=32.50`, write `sale.totalize@1` audit, and enqueue `sale.ready_to_charge`

#### Scenario: Totalize already ready is a stable read-back
- **WHEN** totalize runs again for a session that is already `ready_to_charge` with a different idempotency key
- **THEN** status MUST stay `ready_to_charge`, item rows MUST be unchanged, a second `sale.ready_to_charge` outbox event MUST NOT be written, a second transition audit MUST NOT be written, and no new `lumo.message.totalize_sale` idempotency row MUST be created

### Requirement: Count-product unit completion after resolve
When interpretation has an unequivocal product query and positive quantity but no unit, the add-item workflow MUST resolve the product as a read before asking. If the unique product `sale_unit` is `unit` or `package`, the workflow MUST complete add-item using that `sale_unit` and MUST NOT ask for a mass unit. If the unique product `sale_unit` is `kilogram`, the workflow MUST keep existing missing-unit clarification and MUST NOT infer `kilogram`. The interpreter MUST NOT write the database.

#### Scenario: Two Galleta A without explicit unit
- **WHEN** a Carrota actor posts `2 galletas A` on an open or absent session
- **THEN** Galleta A MUST be added with `unit=unit`, `quantity_normalized=2`, and `line_total.amount=24.00`

#### Scenario: Two Zanahoria still asks for unit
- **WHEN** a Carrota actor posts `2 zanahoria`
- **THEN** the system MUST ask only for the unit, MUST NOT persist a `SaleItem`, and MUST NOT treat quantity `2` as kilograms

### Requirement: Clarification inside an active sale
Missing-unit clarification MUST continue to work while a sale is `open`. Unequivocal fields MUST be preserved, only the missing field MUST be asked, and nothing MUST be written until resolved. The completed item MUST attach to the existing open session for that `conversation_id`.

#### Scenario: 500 tomate then gr
- **WHEN** an open session already exists and the actor posts `500 tomate` then `gr` with the same `conversation_id`
- **THEN** the first response MUST clarify with no new item, and the second MUST persist Tomate `0.500` kg at `10.00` MXN on that same session

### Requirement: Policies for session state
`PolicyEngine` MUST evaluate `SALE-002` (add-item only while `open`) and `SALE-003` in addition to the existing slice policies. `SALE-003` MUST require an `open` session with at least one item **to allow the status transition**. `SALE-003` MUST allow a `ready_to_charge` totalize only as a stable read-back/no-op. Unregistered `sale.commit@1` MUST remain `deny`.

#### Scenario: Add after ready_to_charge denied
- **WHEN** policy or domain validation evaluates add-item against a `ready_to_charge` session
- **THEN** the decision MUST NOT be `allow` under `SALE-002` and no item MUST persist

#### Scenario: Empty totalize blocked
- **WHEN** totalize is evaluated with no items
- **THEN** the decision MUST NOT be `allow` under `SALE-003` and no status transition MUST occur

#### Scenario: Ready_to_charge totalize is not a second transition
- **WHEN** totalize is evaluated against a `ready_to_charge` session
- **THEN** policy MUST NOT treat it as a forbidden transition; the workflow MUST return the current summary without changing status
