## Purpose

Agent message API, registered catalog/sale/day/closing tools including `sale.totalize@1`, `sale.commit@1`, `operational_day.summary@1`, `closing.submit_cash_count@1`, `closing.prepare@1`, and `closing.confirm@1`, policies, scripted local interpreter, and application workflows that resolve then commit start/reuse + add-item, totalize to `ready_to_charge`, record payment to `confirmed`, record a cash count, prepare a close, or confirm today's open day.
## Requirements
### Requirement: Agent message endpoint
The API MUST expose `POST /api/v1/lumo/messages` under `/api/v1`. The body MUST accept `message` and MAY accept `conversation_id` and `client_context`. Inicio MUST send `conversation_id` on every request. The route MUST authenticate, derive `TenantContext` from the session, require `Idempotency-Key`, and propagate `X-Correlation-ID`. The handler MUST invoke the single `LumoOrchestrator` and MUST NOT contain catalog or pricing rules.

#### Scenario: Authenticated send
- **WHEN** a Carrota actor posts `{"message": "900gr zanahoria", "conversation_id": "<uuid>"}` with a valid session and idempotency key
- **THEN** the orchestrator MUST run and the HTTP handler MUST NOT calculate `line_total`

#### Scenario: Conversation id is forwarded
- **WHEN** Inicio posts a message with a client-generated `conversation_id`
- **THEN** the orchestrator context MUST include that same `conversation_id`

### Requirement: AgentDecision extension for add-item
`AgentDecision` MUST keep existing fields and MAY add optional `product_query`, `quantity` (decimal string), and `unit` (`gram` | `kilogram` | `unit` | `package`). Intent for this slice MUST be `add_sale_item` when those fields are present. `candidate_tool` MUST be a registered tool id or null. Invalid provider output MUST be discarded with no mutation.

#### Scenario: Golden interpretation
- **WHEN** the scripted interpreter receives `900gr zanahoria`
- **THEN** `AgentDecision` MUST have `intent=add_sale_item`, `product_query` matching zanahoria, `quantity=900`, `unit=gram`, and `candidate_tool=sale.add_item@1`

#### Scenario: Invalid decision discarded
- **WHEN** the provider returns a payload that fails `AgentDecision`
- **THEN** no tool MUST run and no `SaleItem` MUST be persisted

### Requirement: LLM cannot mutate
No `LLMProvider` implementation MUST write PostgreSQL, call repositories, or invoke tools. The orchestrator MUST validate the decision and request policy, then invoke the application workflow. Tool arguments MUST be revalidated server-side (`SEC-003`) from tenant, catalog, and parsed entities — not from model-supplied totals or product ids the catalog did not return.

#### Scenario: Model total ignored
- **WHEN** a decision includes a response hint or entity claiming total `99.00`
- **THEN** persisted `line_total` MUST still be the backend value `22.50` MXN for the golden Zanahoria path

### Requirement: Tool catalog.resolve_product@1
`ToolRegistry` MUST register `catalog.resolve_product@1` as a read tool. Input MUST be `{ "query": string }`. Output MUST be `{ "match": "unique"|"ambiguous"|"none", "product": object|null, "candidates": array }`. Unique `product` MUST include `product_id`, `name`, `normalized_name`, `sale_unit`, `pricing_type`, `current_price` `{amount, currency}`, and `product_status`. Permission MUST be `sale.create`. Side effect MUST be `read`. Idempotency MUST NOT be required.

#### Scenario: Resolve Zanahoria
- **WHEN** the tool runs with `query=zanahoria` for the Carrota tenant
- **THEN** `match` MUST be `unique` and `product.name` MUST be `Zanahoria`

### Requirement: Tool sale.start@1
`ToolRegistry` MUST register `sale.start@1` as a write tool. Input MUST be `{ "conversation_id": string|null }`. Output MUST be `{ "sale_session_id": uuid, "status": "open"|"ready_to_charge", "created": boolean, "item_count": integer }`. Output `status` MUST NOT be `confirmed`. A `confirmed` session is historical/inactive and MUST NOT be returned as the started or reused session. Permission MUST be `sale.create`. Idempotency MUST be required when start is invoked as its own public operation. When `conversation_id` is present, the tool MUST reuse the open session for `(business_id, actor_id, conversation_id)` and MUST persist that id on `SaleSession`. If a `ready_to_charge` session exists for that context, start MUST NOT create another session and MUST return that active session with `status=ready_to_charge` and `created=false` without treating it as reusable for add-item. If only a `confirmed` session exists for that context, start MUST create a new `open` session and MUST return `status=open` and `created=true`. When composed on the message path, start/reuse MUST participate in the workflow write transaction (see message-path transaction requirement) and MUST NOT commit an empty session before add-item.

#### Scenario: Start is idempotent
- **WHEN** `sale.start@1` is invoked twice as its own public operation with the same tenant, actor, conversation, key, and payload
- **THEN** one `SaleSession` MUST exist and both results MUST return the same `sale_session_id`

#### Scenario: Same conversation reuses one session
- **WHEN** two successful message-path add-item mutations use the same tenant, actor, and `conversation_id`
- **THEN** exactly one open `SaleSession` MUST exist for that context and both items MUST belong to it

#### Scenario: Different conversations isolate sessions
- **WHEN** two successful message-path add-item mutations use different `conversation_id`s for the same tenant and actor
- **THEN** two open `SaleSession`s MUST exist and neither mutation MUST reuse the other's session

#### Scenario: Start after confirmed creates a new session
- **WHEN** the latest session for the context is `confirmed` and `sale.start@1` runs
- **THEN** a new `open` session MUST be returned with `created=true` and `status=open`, the confirmed session MUST remain unchanged, and the output MUST NOT use the confirmed session id or `status=confirmed`

#### Scenario: Start output never reports confirmed
- **WHEN** `sale.start@1` runs against an `open` session, a `ready_to_charge` session, or a context whose only prior session is `confirmed`
- **THEN** output `status` MUST be `open` or `ready_to_charge` and MUST NOT be `confirmed`

### Requirement: Tool sale.add_item@1
`ToolRegistry` MUST register `sale.add_item@1` as a write tool. Input MUST include `sale_session_id`, `quantity` (decimal string), `unit` (`gram` | `kilogram` | `unit` | `package`), and `source_type` (`catalog` | `free_concept`). When `source_type` is `catalog`, `product_id` MUST be required and `concept_name` and `unit_price` MUST NOT be used as the price. When `source_type` is `free_concept`, `product_id` MUST be null or absent, `concept_name` MUST be required, and `unit_price` MUST be required as `{amount, currency}`. The tool id `sale.add_free_item@1` MUST NOT be registered. Output MUST include `sale_session_id`, `sale_item_id`, `source_type`, `product_id` (string or null), `product_name`, `quantity_input`, `unit_input`, `quantity_normalized`, `unit_normalized`, `unit_price`, `line_total`, `session_item_count`, and `session_total` (money as decimal string plus `MXN`). Permission MUST be `sale.create`. Idempotency MUST be required when add-item is invoked as its own public operation. The tool MUST re-read a catalog product, reject inactive or missing products, lock the session row when it exists, reject a session that is not `open`, normalize quantity, calculate `line_total`, persist, and audit. On the message path, those writes MUST share the workflow transaction with session create/reuse. A `free_concept` write MUST resolve `normalize_product_name(concept_name)` before any write and MUST persist the display `concept_name` after trim and whitespace collapse. It MUST NOT persist when that match is `unique` or `ambiguous`.

#### Scenario: Add 900 grams of Zanahoria
- **WHEN** the tool runs with `source_type=catalog`, the seeded Zanahoria `product_id`, `quantity=900`, and `unit=gram` on an open session
- **THEN** it MUST persist `source_type=catalog`, `quantity_normalized=0.900`, `unit_normalized=kilogram`, `unit_price.amount=25.00`, `line_total.amount=22.50`, and an audit event in the same committed state

#### Scenario: Replay identical add-item
- **WHEN** the same tenant resubmits `sale.add_item@1` with the same idempotency key and payload hash
- **THEN** the original item id and body MUST be returned and a second `SaleItem` MUST NOT be created

#### Scenario: Add two Galleta A
- **WHEN** the tool runs with `source_type=catalog`, the seeded Galleta A `product_id`, `quantity=2`, and `unit=unit` on an open session
- **THEN** it MUST persist `quantity_normalized=2`, `unit_normalized=unit`, `unit_price.amount=12.00`, and `line_total.amount=24.00`

#### Scenario: Add a free concept through the same tool
- **WHEN** the tool runs with `source_type=free_concept`, `concept_name=bolsas de hielo`, `product_id` null, `quantity=2`, `unit=package`, and `unit_price.amount=18.00` after resolution of normalized `bolsas de hielo` is `none`
- **THEN** it MUST persist one row with `product_id` NULL, `product_name_snapshot=bolsas de hielo`, and `line_total.amount=36.00`

#### Scenario: Accented concept_name is not the lookup key
- **WHEN** the tool runs with `source_type=free_concept` and `concept_name=Café Orgánico` and `normalize_product_name` of that name matches nothing
- **THEN** the persisted `product_name_snapshot` MUST be `Café Orgánico` and the resolution query MUST have been `cafe organico`

#### Scenario: Accented concept_name that matches stays catalog
- **WHEN** the tool runs with `source_type=free_concept` and `concept_name=Café Orgánico` and normalized `cafe organico` is a unique active product
- **THEN** no free-concept row MUST be persisted

### Requirement: Orchestrator delegates; workflow owns the write transaction
For intent `add_sale_item` with a resolvable product and a complete unit (explicit, or inferred only for `unit`/`package` products after unique resolve), and with no grounded price or a grounded price `Decimal`-equal to `Product.current_price`, the orchestrator MUST request interpretation and policy, then invoke the application add-item workflow. A unique match whose grounded price differs from `Product.current_price` MUST clarify under `CAT-001` and MUST NOT open the write transaction. For intent `add_sale_item` whose resolution is `none` and whose free-concept quantity, unit, and explicit grounded price are complete, including a per-kilogram basis when the unit is gram or kilogram, the orchestrator MUST invoke that same add-item workflow and MUST NOT invoke a second tool. For intent `totalize_sale`, it MUST invoke `TotalizeSaleSession` and MUST NOT run add-item. For intent `commit_sale`, it MUST invoke `CommitSaleSession` and MUST NOT run add-item or totalize. It MUST NOT open ORM sessions or database transactions. The add-item workflow MUST: (1) run `catalog.resolve_product@1` as a read **before** any write transaction; (2) if the match is unique, the grounded price is absent or `Decimal`-equal to `Product.current_price`, and the session is `open` or absent (including when only `confirmed` sessions exist), or the match is `none` and the free-concept facts are complete, including a per-kilogram basis for gram or kilogram, open one write transaction that **locks** the existing active `SaleSession` when present (`SELECT ... FOR UPDATE`), re-reads status, creates or reuses the open session only if still open, and inserts the `SaleItem` using `sale.start@1` / `sale.add_item@1` semantics without an intervening commit; (3) write audit, outbox, and the message-level idempotency record in that same transaction; (4) compose `sale_item_added@1` only after commit. If the locked session is `ready_to_charge` (CASE A), it MUST deny under `SALE-002` without writing an item and MUST NOT start a second lookup in that same request to create a new sale. If that lookup finds no active session because a concurrent commit already confirmed (CASE B), the same request MAY create a new `open` session. If resolve is ambiguous, or a free-concept fact or per-kilogram basis is missing, or a unique catalog price mismatches, or policy is not `allow`, it MUST clarify or deny without opening the write transaction. Committing `sale.start@1` before `sale.add_item@1` on this path is forbidden. `match=none` alone MUST NOT skip a complete free-concept write. A gram or kilogram free concept without a per-kilogram basis MUST NOT open that write.

#### Scenario: Golden path sequences tools
- **WHEN** Inicio posts `900gr zanahoria` for Carrota
- **THEN** resolve MUST run first, start/reuse and add-item MUST commit together, and a `SaleItem` MUST exist only after that commit

#### Scenario: Ambiguity stops before mutation
- **WHEN** product resolution is `ambiguous`
- **THEN** `sale.start@1` and `sale.add_item@1` MUST NOT run as a result of that message and no `SaleSession` MUST be created for it

#### Scenario: Complete unknown concept still adds
- **WHEN** Inicio posts `2 bolsas de hielo a 18 cada una` and resolution is `none`
- **THEN** resolve MUST run first and one free-concept `SaleItem` MUST exist only after the add-item commit

#### Scenario: Failed add-item does not leave a new session
- **WHEN** the message would create a new `SaleSession` and add-item fails before commit
- **THEN** neither the session nor the item MUST remain

#### Scenario: Totalize is a separate workflow
- **WHEN** Inicio posts `totalizar` for an open session with items
- **THEN** `TotalizeSaleSession` MUST run, `sale.add_item@1` MUST NOT run, and `sale_summary@1` MUST be composed only after commit

#### Scenario: Commit is a separate workflow
- **WHEN** Inicio posts `efectivo` for a `ready_to_charge` session
- **THEN** `CommitSaleSession` MUST run, add-item and totalize MUST NOT run, and `sale_confirmed@1` MUST be composed only after commit

### Requirement: Message-level idempotency
`POST /api/v1/lumo/messages` MUST treat `Idempotency-Key` as the key for the whole message workflow. Add-item MUST use `operation_type` `lumo.message.add_sale_item`. Totalize MUST use `operation_type` `lumo.message.totalize_sale`. Commit MUST use `operation_type` `lumo.message.commit_sale`. Recording a cash count MUST use `operation_type` `lumo.message.record_cash_count`. Confirming a close MUST use `operation_type` `lumo.message.confirm_close`. These MUST NOT share one operation type. Read-only message paths (`operational_day.summary@1`, `closing.prepare@1`, and `request_close`) MUST NOT insert an idempotency record. The cash-count path MUST peek its key before locking the operational day and MUST reserve the key only when persisted state changes, so an equal-amount submission with a new key MUST NOT insert a `lumo.message.record_cash_count` row. The confirm path MUST peek its key before locking the day and MUST reserve the key only when a snapshot will be inserted.

#### Scenario: Replay of the golden message
- **WHEN** the same tenant resubmits `"900gr zanahoria"` with the same message idempotency key and payload hash
- **THEN** the original session id, item id, and body MUST be returned and a second `SaleItem` MUST NOT be created

#### Scenario: Replay of totalize
- **WHEN** the same tenant resubmits `totalizar` with the same message idempotency key and payload hash after a successful totalize
- **THEN** the original session id and `sale_summary@1` body MUST be returned, status MUST remain `ready_to_charge`, and a second `sale.ready_to_charge` outbox row MUST NOT be created

#### Scenario: Different-key totalize does not persist idempotency
- **WHEN** the session is already `ready_to_charge` and the tenant posts `totalizar` with a new idempotency key
- **THEN** current `sale_summary@1` MUST be returned and no new `lumo.message.totalize_sale` row MUST exist for that key

#### Scenario: Replay of commit
- **WHEN** the same tenant resubmits `efectivo` with the same message idempotency key and payload hash after a successful commit
- **THEN** the original session id, payment id, and `sale_confirmed@1` body MUST be returned, status MUST remain `confirmed`, and a second `Payment` or `sale.confirmed` outbox row MUST NOT be created

#### Scenario: Replay of a cash count
- **WHEN** the same tenant resubmits `tengo 20 en caja` with the same message idempotency key and payload hash after a successful count
- **THEN** the original body MUST be returned even if cash sales changed since the count, exactly one `CashCount` MUST exist for that day, and a second `cash_count.recorded` outbox row MUST NOT be created

#### Scenario: Different-key cash count with the same amount does not persist idempotency
- **WHEN** the current count is `20.00` and the tenant posts `tengo 20 en caja` with a new idempotency key
- **THEN** current preparation MUST be returned with live `expected_cash` and `cash_difference`, and no new `lumo.message.record_cash_count` row MUST exist for that key

#### Scenario: Preparation read writes no idempotency row
- **WHEN** the tenant posts `preparar el cierre` with a fresh idempotency key
- **THEN** no `lumo.message.record_cash_count` row and no other idempotency row MUST be created for that message

#### Scenario: Request close writes no idempotency row
- **WHEN** the tenant posts `cerrar el día` with a fresh idempotency key
- **THEN** no `lumo.message.confirm_close` row MUST be created

### Requirement: Minimum policies for these tools
`PolicyEngine` MUST evaluate `SEC-001`, `SEC-002`, `SEC-003`, `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, `SALE-001`, `SALE-002`, `SALE-003`, `SALE-004`, `SALE-005`, `PAY-001`, `DAY-001`, `CLOSE-001`, `CLOSE-002`, and `CLOSE-003` for this slice. Unregistered tools MUST be `deny`. Missing essential fields or low-confidence mutation MUST be `clarify`. An inactive product MUST be `deny` or `clarify` without persist. `match=none` without a complete explicit free-concept price and quantity MUST be `clarify` without persist. For gram or kilogram, `match=none` without an explicit per-kilogram basis MUST be `clarify` with reason `price_basis_required` and without persist. `match=none` with those facts, including the basis when the unit is mass, MUST be `allow` under `SALE-005`. A unique catalog match whose grounded price differs from `Product.current_price` MUST be `clarify` under `CAT-001` reason `catalog_price_mismatch` and MUST NOT be routed through `SALE-005`. An ambiguous match MUST stay `clarify` under `CAT-001` and MUST NOT be allowed as a free concept. Unknown payment method MUST be `clarify` under `PAY-001`. A cash count with no `OperationalDay` for today MUST be `clarify` under `CLOSE-001` without persisting anything. `CLOSE-003` MUST deny `closing.confirm@1` when the arguments include a server-owned total, difference, status, day id, snapshot id, or `closed_at`. Evaluation order MUST remain security, integrity, tenant and permissions, workflow gates, business rules, catalog and pricing, confidence, then user experience.

#### Scenario: Unregistered reopen denied
- **WHEN** a decision names `closing.reopen@1`
- **THEN** policy MUST `deny` under `SEC-002` and no close or reopen MUST occur

#### Scenario: Positive quantity policy
- **WHEN** add-item arguments include a non-positive quantity
- **THEN** policy or domain validation MUST block the mutation under `SALE-001`

#### Scenario: Free concept without a price clarifies
- **WHEN** resolution is `none` and no explicit unit price was parsed
- **THEN** policy MUST NOT be `allow` and no `SaleItem` MUST be persisted

#### Scenario: Mass basis missing clarifies
- **WHEN** resolution is `none`, the unit is `gram` or `kilogram`, a positive price is present, and no per-kilogram basis was grounded
- **THEN** policy MUST clarify with reason `price_basis_required` and no `SaleItem` MUST be persisted

#### Scenario: Catalog price mismatch is not a free concept
- **WHEN** resolution is `unique` and the grounded price differs from `Product.current_price`
- **THEN** policy MUST clarify under `CAT-001` with reason `catalog_price_mismatch`, MUST NOT allow `SALE-005`, and MUST NOT reserve idempotency

#### Scenario: Cash count without a started day clarifies
- **WHEN** a decision names `closing.submit_cash_count@1` and no `OperationalDay` exists for today's business date
- **THEN** policy MUST NOT be `allow`, the response MUST clarify, and no `CashCount` or `OperationalDay` MUST be persisted

#### Scenario: CLOSE-003 rejects model-supplied close figures
- **WHEN** policy evaluates `closing.confirm@1` with arguments carrying `expected_cash`, `cash_difference`, or `operational_day_id`
- **THEN** the decision MUST be `deny` under `CLOSE-003` and no snapshot MUST be written

### Requirement: Scripted interpreter for local and test
Local and test runtimes MUST use a non-vendor interpreter that can produce a valid `AgentDecision` for catalog add-item utterances, unit-only follow-ups, totalize synonyms `totalizar`, `total`, and `el total`, the closed payment phrases for cash, card, and transfer (trimmed, case-insensitive), the closed day-summary phrases, the closed cash-count phrases, the closed close-preparation phrases, the closed request-close phrases, and the closed confirm-close phrases. A real LLM vendor SDK MUST NOT be required for the acceptance tests of this capability. The interpreter MUST remain compatible with a future `LLMProvider` (no repository or DB access). Count-product completion MUST NOT be hardcoded in the interpreter from catalog prices; missing unit for a possible count product MUST still reach application resolve. The interpreter MUST NOT write domain state. Day-summary matching MUST run after payment and totalize matching. Cash-count, close-preparation, request-close, and confirm-close matching MUST run after day-summary matching and before product parsing. After accent folding, case folding, whitespace collapse, and stripping one surrounding layer of `¿?¡!`, only `como vamos hoy`, `ventas de hoy`, and `cuanto vendimos hoy` MUST map to `intent=day_summary` and `candidate_tool=operational_day.summary@1`.

#### Scenario: Fake provider still boots
- **WHEN** no vendor LLM is configured
- **THEN** health MAY report fake/non-ready and `POST /api/v1/lumo/messages` MUST still execute the golden path via the scripted interpreter

#### Scenario: Totalize interpretation
- **WHEN** the scripted interpreter receives `totalizar`
- **THEN** `AgentDecision` MUST have `intent=totalize_sale` and `candidate_tool=sale.totalize@1`

#### Scenario: Cash interpretation
- **WHEN** the scripted interpreter receives `pagar en efectivo`
- **THEN** `AgentDecision` MUST have `intent=commit_sale`, `payment_method=cash`, and `candidate_tool=sale.commit@1`

#### Scenario: Day summary interpretation
- **WHEN** the scripted interpreter receives `¿Cómo vamos hoy?`
- **THEN** `AgentDecision` MUST have `intent=day_summary` and `candidate_tool=operational_day.summary@1`

#### Scenario: Cash count interpretation
- **WHEN** the scripted interpreter receives `tengo 120 en caja`
- **THEN** `AgentDecision` MUST have `intent=record_cash_count`, `counted_amount=120`, and `candidate_tool=closing.submit_cash_count@1`

#### Scenario: Close preparation interpretation
- **WHEN** the scripted interpreter receives `preparar el cierre`
- **THEN** `AgentDecision` MUST have `intent=close_preparation` and `candidate_tool=closing.prepare@1`

#### Scenario: Request close interpretation
- **WHEN** the scripted interpreter receives `cerrar el día`
- **THEN** `AgentDecision` MUST have `intent=request_close` and MUST NOT have `candidate_tool=closing.confirm@1`

#### Scenario: Confirm close interpretation
- **WHEN** the scripted interpreter receives `confirmar cierre`
- **THEN** `AgentDecision` MUST have `intent=confirm_close` and `candidate_tool=closing.confirm@1`

#### Scenario: Sale utterances keep their path
- **WHEN** the scripted interpreter receives `900gr zanahoria`
- **THEN** the decision MUST still be `add_sale_item` for `sale.add_item@1` and MUST NOT be a cash count

### Requirement: Pending missing-unit clarification
When a message yields an unequivocal product query and quantity but no unit, the runtime MUST ask only for the unit and MUST store those parsed fields keyed by `(business_id, actor_id, conversation_id)`. Inicio MUST use its stable client UUID as `conversation_id` (not null). It MUST NOT create a `SaleSession` or `SaleItem` on that turn. A later unit-only reply in the same scope (`gr`, `g`, `gramos`, `kg`, `kilogramo`, `kilogramos`) MUST reuse the pending product and quantity and complete the normal add-item workflow against the same `conversation_id`. A new complete add-item utterance MUST replace pending state. This MUST NOT be general-purpose memory and MUST NOT create schema `memory`.

#### Scenario: Two-turn 900 zanahoria then gr
- **WHEN** a Carrota actor posts `"900 zanahoria"` and then `"gr"` with the same `conversation_id`
- **THEN** the first response MUST clarify with no session or item, and the second MUST persist exactly one open `SaleSession` with that `conversation_id` and one `SaleItem` for 0.900 kg Zanahoria at `22.50` MXN

#### Scenario: Unit-only without pending state
- **WHEN** the actor posts `"gr"` with no pending missing-unit clarification for that `conversation_id`
- **THEN** the runtime MUST clarify and MUST NOT persist a sale

### Requirement: Local seed at API boot
When `APP_ENV=local`, API startup MUST run the idempotent Carrota seed (Zanahoria, Tomate, Galleta A) and commit it. Tests MUST call the same seed helper explicitly. Staging and production MUST NOT insert that seed automatically.

#### Scenario: Local boot seeds catalog
- **WHEN** the API starts with `APP_ENV=local` against a migrated database
- **THEN** business Carrota and active products Zanahoria, Tomate, and Galleta A MUST exist for that tenant with the seed prices

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
`PolicyEngine` MUST evaluate `SALE-002` (add-item only while `open`), `SALE-003` (totalize transition vs read-back), `SALE-004` (commit transition vs read-back), and `PAY-001` (explicit method from the closed enum; do not infer cash) in addition to the existing slice policies. `SALE-004` MUST require `ready_to_charge` **to allow the status transition**. `SALE-004` MUST allow a `confirmed` commit only as a stable read-back/no-op. Commit against `open` or missing sale MUST be blocked. Registered `sale.commit@1` MUST be executable only through this policy path.

#### Scenario: Add after ready_to_charge denied
- **WHEN** policy or domain validation evaluates add-item against a `ready_to_charge` session
- **THEN** the decision MUST NOT be `allow` under `SALE-002` and no item MUST persist

#### Scenario: Empty totalize blocked
- **WHEN** totalize is evaluated with no items
- **THEN** the decision MUST NOT be `allow` under `SALE-003` and no status transition MUST occur

#### Scenario: Ready_to_charge totalize is not a second transition
- **WHEN** totalize is evaluated against a `ready_to_charge` session
- **THEN** policy MUST NOT treat it as a forbidden transition; the workflow MUST return the current summary without changing status

#### Scenario: Open sale cannot commit
- **WHEN** commit is evaluated against an `open` session
- **THEN** the decision MUST NOT be `allow` under `SALE-004` and no `Payment` MUST persist

### Requirement: Dev and debug surfaces are local/test only
`GET /api/v1/dev/carrota-token` MUST be unavailable in staging and production. Header `X-Debug-Fail-After-Write` MUST force a write rollback only when `APP_ENV` is `local` or `test`; it MUST be ignored otherwise.

#### Scenario: Dev token rejected outside local/test
- **WHEN** `APP_ENV` is `staging` or `production` and a client calls `GET /api/v1/dev/carrota-token`
- **THEN** the API MUST NOT issue a token (`FORBIDDEN`)

#### Scenario: Debug fail header ignored in production
- **WHEN** `APP_ENV` is `production` and `POST /api/v1/lumo/messages` includes `X-Debug-Fail-After-Write: 1`
- **THEN** a successful golden add-item MUST still commit

### Requirement: AgentDecision extension for commit
`AgentDecision` MUST keep existing add-item and totalize fields and MAY add optional `payment_method` (`cash` | `card` | `transfer`). Intent `commit_sale` MUST be used for approved payment phrases. `candidate_tool` MUST be `sale.commit@1` or null. Invalid provider output MUST still be discarded with no mutation.

#### Scenario: Golden card interpretation
- **WHEN** the scripted interpreter receives `con tarjeta`
- **THEN** `AgentDecision` MUST have `intent=commit_sale`, `payment_method=card`, and `candidate_tool=sale.commit@1`

### Requirement: Tool sale.commit@1
`ToolRegistry` MUST register `sale.commit@1` as a write tool. Input MUST be `{ "conversation_id": string|null, "payment_method": "cash"|"card"|"transfer" }`. Input MUST NOT include amount, change, a client-calculated total, or `operational_day_id`. Output MUST include `sale_session_id`, `payment_id`, `status` (`confirmed`), `item_count`, `currency`, `total`, `payment` (`method`, `amount`, `status=recorded`), and `items`. Permission MUST be `sale.create`. Idempotency MUST be required for the **transition** when commit is invoked as its own public operation. On the message path, a transitioning commit, OperationalDay ensure, `Payment`, audit, outbox, and message idempotency MUST share one application-owned write transaction after locking the session row. The tool MUST lock the active session for the interaction context, then:

- if `status=ready_to_charge`: compute `business_date` from one `confirmed_at` clock reading and the business timezone, ensure that OperationalDay, Decimal-sum persisted items, insert one `Payment` with that total and `business_id` copied from the locked session / `TenantContext` (never from client or tool input), persist `confirmed` with `operational_day_id` and `confirmed_at`, write `sale.commit@1` audit including `operational_day_id`, enqueue `sale.confirmed` (including `operational_day_id`) and `payment.recorded`, enqueue `operational_day.opened` only when this transaction inserted the day, and complete `lumo.message.commit_sale`;
- if no active session and the latest session is `confirmed`: return the current confirmation as a stable read-back with no status change, no second `Payment`, no second outbox, no transition audit, no new idempotency record, and no new OperationalDay;
- if `status=open`: deny without mutation;
- if no session: deny without mutation.

Compose `sale_confirmed@1` after commit on the transition path, and from current persisted rows on the read-back path. Catalog prices MUST NOT be re-read in this change; the ready-to-charge item snapshots remain the financial truth.

#### Scenario: Commit ready_to_charge session
- **WHEN** `sale.commit@1` runs for a ready Carrota session totaling `56.50` with `payment_method=cash`
- **THEN** it MUST persist `status=confirmed`, one `Payment` of `56.50` cash, a non-null `operational_day_id` for that business date, return that total, write `sale.commit@1` audit, and enqueue `sale.confirmed` and `payment.recorded`

#### Scenario: Commit already confirmed is a stable read-back
- **WHEN** commit runs again for a conversation whose latest session is `confirmed` with a different idempotency key
- **THEN** status MUST stay `confirmed`, a second `Payment` MUST NOT be written, a second `sale.confirmed` outbox event MUST NOT be written, no new `lumo.message.commit_sale` idempotency row MUST be created, and no additional OperationalDay MUST be inserted

### Requirement: Tool operational_day.summary@1
`ToolRegistry` MUST register `operational_day.summary@1` as a read tool. Input MUST be an empty object and MUST NOT accept a client business date, sale count, or totals. Output MUST be the daily summary payload from persisted confirmed sales. Permission MUST be `sale.create`. Side effect MUST be `read`. Idempotency MUST NOT be required and the message path MUST NOT insert an idempotency row for this read. The orchestrator MUST route `day_summary` to the read workflow and MUST NOT open a business transaction. The workflow MUST NOT insert or update an OperationalDay, sale, or payment.

#### Scenario: Summary does not write
- **WHEN** `operational_day.summary@1` runs for a tenant
- **THEN** it MUST return the server summary and MUST NOT insert `operations.operational_days`, audit, outbox, or `idempotency_records` rows

### Requirement: Concurrent commit serializes on the session row
Two concurrent commit requests against the same `ready_to_charge` session MUST serialize on `SELECT ... FOR UPDATE` of that row. Exactly one `Payment` and one `confirmed` transition MUST persist. The loser MUST observe `confirmed` after the lock and follow same-key replay or different-key read-back. Concurrent totalize against `confirmed` MUST NOT find an active session and MUST NOT mutate.

Add-item vs commit is decided by the transaction that first commits its locked view of the active session. Add-item MUST perform **one** active-session `FOR UPDATE` lookup in its write transaction and MUST decide from that result. It MUST NOT lock a `ready_to_charge` row, deny, then re-query in the same request to start a new sale. It MUST NOT wait for a concurrent commit and then reinterpret a `ready_to_charge` lock as a new sale.

- **CASE A — add-item obtains the `ready_to_charge` lock first:** it sees `ready_to_charge`, MUST deny under `SALE-002`, MUST persist no `SaleItem`, and MUST NOT create a second session. Commit waits, then confirms Sale A after add-item releases the row.
- **CASE B — commit obtains the lock, confirms, and commits first:** Sale A is `confirmed` and immutable. When add-item then performs its transactional active-session lookup, no `open`/`ready_to_charge` row exists, so **the same add-item request MAY create Sale B** as a new `open` session. The new item belongs only to Sale B.

This CASE B outcome is intentional Build A behavior. Do not introduce conversation epochs, Redis, distributed locks, explicit "nueva venta", or `conversation_id` rotation.

#### Scenario: Two payment requests race
- **WHEN** two `efectivo` requests with different idempotency keys run concurrently against the same `ready_to_charge` session
- **THEN** exactly one `Payment` and one `sale.confirmed` outbox row MUST exist, and both successful HTTP responses MUST describe that same confirmed sale

#### Scenario: CASE A add-item locks ready_to_charge first
- **WHEN** add-item and commit race and add-item's write transaction obtains `FOR UPDATE` on the `ready_to_charge` session first
- **THEN** add-item MUST be rejected with no new `SaleItem` and no new session, and commit MUST then confirm that same session

#### Scenario: CASE B commit confirms before add-item lookup
- **WHEN** add-item and commit race and commit transitions the session to `confirmed` and commits before add-item's write transaction performs its active-session lookup
- **THEN** Sale A MUST remain `confirmed` with its original items and one `Payment`, and add-item MAY persist a new `open` Sale B whose only new item is the racing add, never attached to Sale A

### Requirement: AgentDecision extension for cash count and preparation
`AgentDecision` MUST keep existing add-item, totalize, and payment fields and MAY add one optional `counted_amount` (decimal string). Intent `record_cash_count` MUST be used for approved cash-count phrases, and `close_preparation` for approved preparation phrases. `candidate_tool` MUST be `closing.submit_cash_count@1`, `closing.prepare@1`, or null. `counted_amount` MUST be a non-negative decimal string with at most two fraction digits, normalized to `.` as the decimal separator. Invalid provider output MUST be discarded with no mutation. The decision MUST NOT carry `expected_cash`, `cash_difference`, `cash_status`, `operational_day_id`, or `business_date`.

#### Scenario: Decimal comma is normalized
- **WHEN** the scripted interpreter receives `conté 22,50`
- **THEN** `AgentDecision.counted_amount` MUST be `22.50` and the intent MUST be `record_cash_count`

#### Scenario: Invalid cash decision discarded
- **WHEN** a provider returns `record_cash_count` with `counted_amount` `-5` or `1.005`
- **THEN** no tool MUST run, no `CashCount` MUST be persisted, and the response MUST NOT claim a count was recorded

### Requirement: Closed cash-count phrases
After accent folding, case folding, whitespace collapse, and stripping one surrounding layer of `¿?¡!`, the scripted interpreter MUST map exactly these shapes to `intent=record_cash_count` with `candidate_tool=closing.submit_cash_count@1`:

```text
tengo <amount> en caja
hay <amount> en caja
conte <amount>
caja <amount>
```

`<amount>` MUST match an optional `$`, digits, and an optional one- or two-digit fraction using `.` or `,`. Thousands separators MUST NOT be accepted. A bare amount such as `120` MUST NOT be a cash count. No currency word or symbol MUST change the currency, which is always the business currency. Any other cash wording MUST follow the existing non-mutating unsupported clarification and MUST NOT call the cash-count tool. The interpreter MUST NOT access a repository and MUST NOT compute a difference.

#### Scenario: Approved capture phrases
- **WHEN** the actor posts `tengo 120 en caja`, `hay 120 en caja`, `conté 120`, or `caja 120`
- **THEN** each MUST produce `intent=record_cash_count` with `counted_amount=120`

#### Scenario: Decimal amount captured
- **WHEN** the actor posts `conté 22.50`
- **THEN** `counted_amount` MUST be `22.50`

#### Scenario: Ambiguous thousands separator clarifies
- **WHEN** the actor posts `tengo 1,200 en caja`
- **THEN** the system MUST clarify, MUST NOT call `closing.submit_cash_count@1`, and MUST NOT persist a `CashCount`

#### Scenario: Bare amount is not a count
- **WHEN** the actor posts `120`
- **THEN** the decision MUST NOT be `record_cash_count` and no `CashCount` MUST be persisted

### Requirement: Closed close-preparation phrases and no-close guard
After the same normalization, the scripted interpreter MUST map exactly `preparar el cierre`, `preparar cierre`, `cuanto deberia haber en caja`, and `efectivo esperado` to `intent=close_preparation` with `candidate_tool=closing.prepare@1`. It MUST map exactly `cerrar el dia`, `cerrar la jornada`, and `cerrar caja` to `intent=request_close` without `candidate_tool=closing.confirm@1`. It MUST map exactly `confirmar cierre`, `si, cerrar`, and `confirmar` to `intent=confirm_close` with `candidate_tool=closing.confirm@1`. No other wording MAY select those intents. `preparar el cierre` MUST NOT issue a confirmation token by itself. The interpreter MUST NOT access a repository.

#### Scenario: Approved preparation phrase
- **WHEN** the scripted interpreter receives `¿Cuánto debería haber en caja?`
- **THEN** the decision MUST be `close_preparation` for `closing.prepare@1`

#### Scenario: Request-close phrases do not confirm
- **WHEN** the actor posts `cerrar la jornada` or `cerrar caja`
- **THEN** the decision MUST be `request_close` and MUST NOT select `closing.confirm@1`

#### Scenario: Confirm phrases select the confirm tool
- **WHEN** the actor posts `sí, cerrar` or `confirmar`
- **THEN** the decision MUST be `confirm_close` for `closing.confirm@1`

#### Scenario: Unsupported cash wording clarifies
- **WHEN** the actor posts `cuánto falta en caja la semana pasada`
- **THEN** the system MUST clarify, MUST NOT call a closing tool, and MUST NOT mutate any row

### Requirement: Orchestrator routes cash intents to their workflows
For intent `record_cash_count`, the orchestrator MUST request policy and then invoke the cash-count write workflow, and MUST NOT run add-item, totalize, commit, or the day-summary read. For intent `close_preparation`, it MUST invoke the preparation read workflow and MUST NOT run any write workflow. For intent `request_close` and for action `closing.request@1`, it MUST invoke the preparation read and, only when that read is confirmable, attach a confirmation token. It MUST NOT call `closing.confirm@1` for `request_close` or for `closing.request@1`. For intent `confirm_close`, it MUST pass `client_context.confirmation_token` into `closing.confirm@1` and MUST ignore a model-supplied token. For action `closing.confirm@1`, it MUST pass that action's `context_token` into the same confirm workflow argument and MUST ignore any other token. The orchestrator MUST NOT open ORM sessions or database transactions and MUST NOT calculate expected cash or a difference. The write workflows MUST own one application transaction as specified by `cash-count-foundation` and `daily-close-confirmation`. `daily_close_preparation@1` MUST be composed only after a cash-count commit, or immediately for a non-writing preparation or request-close. `daily_close_confirmed@1` MUST be composed only after a confirm commit or from a committed snapshot read. The read workflow MUST NOT open a write transaction.

#### Scenario: Cash count is its own workflow
- **WHEN** Inicio posts `tengo 20 en caja` for a tenant whose OperationalDay exists
- **THEN** the cash-count workflow MUST run, `sale.add_item@1` / `sale.totalize@1` / `sale.commit@1` MUST NOT run, and `daily_close_preparation@1` MUST be composed only after commit

#### Scenario: Preparation is a read workflow
- **WHEN** Inicio posts `preparar el cierre`
- **THEN** the preparation read workflow MUST run, no write workflow MUST run, and no row MUST be inserted or updated

#### Scenario: Cash count does not touch the sale in progress
- **WHEN** an `open` `SaleSession` with items exists for the conversation and the actor posts `tengo 20 en caja`
- **THEN** that session MUST remain `open` with its items and total unchanged, and no `Payment` MUST be created

#### Scenario: Confirm uses the client token
- **WHEN** Inicio posts `confirmar cierre` with `client_context.confirmation_token` and the model decision also contains a different token
- **THEN** the workflow MUST receive only the client token

#### Scenario: Confirm action uses the action token
- **WHEN** Inicio posts action `closing.confirm@1` whose `context_token` is the server close JWT
- **THEN** the confirm workflow MUST receive that token and MUST NOT read a model-supplied token

### Requirement: UI actions bypass interpretation
`POST /api/v1/lumo/actions` MUST enter the orchestrator without `LLMProvider.interpret`. A registered action MUST call the same handler as the matching typed intent: payment actions call the commit handler, `closing.request@1` calls the request-close handler, and `closing.confirm@1` calls the confirm handler. The action path MUST still evaluate policy and MUST revalidate tenant, actor, permission, and current state. An unregistered action MUST NOT call a tool.

#### Scenario: Payment action skips the interpreter
- **WHEN** `sale.pay.transfer@1` is posted with a valid `ui_action` token
- **THEN** `LLMProvider.interpret` MUST NOT run and `CommitSaleSession` MUST run with method `transfer`

#### Scenario: Unregistered action fails closed
- **WHEN** the action id is not in `UiActionRegistry`
- **THEN** no tool MUST run and no domain row MUST change

### Requirement: AgentDecision carries an explicit unit price candidate
`AgentDecision` MAY include optional `unit_price` as a decimal string. The interpreter MUST set it only when the user utterance contains an explicit amount. The workflow MUST NOT persist that candidate unless `ground_user_price` extracted the same `Decimal` amount from the raw message, or a pending clarification already stored that extracted amount. On a unique catalog match the workflow MUST compare the grounded amount to `Product.current_price` and MUST NOT ignore a mismatch. The workflow MUST reject a candidate that is not a positive decimal with at most two places. `source_type` MUST NOT be taken from the model as authority.

#### Scenario: Priced unknown utterance
- **WHEN** the scripted interpreter receives `1 pastel 250`
- **THEN** `AgentDecision` MUST have `intent=add_sale_item`, a product query for pastel, `quantity=1`, and `unit_price=250`

#### Scenario: Catalog utterance stays an add
- **WHEN** the scripted interpreter receives `900gr zanahoria`
- **THEN** `AgentDecision` MUST still have `intent=add_sale_item`, `unit=gram`, and `candidate_tool=sale.add_item@1`

### Requirement: Pending free-concept clarification
When resolution is `none` and the concept and quantity are known but the unit price is not, the runtime MUST ask only for the price and MUST store the pending free concept in the existing in-memory store keyed by `(business_id, actor_id, conversation_id)`, with `kind=free_concept`. It MUST NOT create a `SaleSession` or `SaleItem` on that turn. The stored concept MUST be the display span, not the normalized lookup. A later price-only reply MUST reuse that pending display span, quantity, and unit, MUST resolve `normalize_product_name` of the stored span, and MUST complete one add. That reply MUST NOT merge into a `catalog_unit` pending. A unit-only reply MUST still complete a `catalog_unit` pending and MUST NOT be parsed as a price. Schema `memory` MUST NOT be created.

#### Scenario: Bags then eighteen
- **WHEN** a Carrota actor posts `2 bolsas de hielo` and then `18` with the same `conversation_id`
- **THEN** the first response MUST be `¿A qué precio vendiste cada bolsa?` with no item, and the second MUST persist one free-concept line totaling `36.00` MXN

#### Scenario: Eighteen does not complete a missing unit
- **WHEN** a `catalog_unit` pending exists for `900 zanahoria` and the actor posts `18`
- **THEN** the runtime MUST NOT persist a Zanahoria line priced at `18`

#### Scenario: Por kilo completes a mass basis
- **WHEN** the actor posts `500g de hielo a 40` and then `por kilo` with the same `conversation_id`
- **THEN** the first response MUST ask whether the `$40.00` are per kilogram, with no item, and the second MUST persist one free-concept line totaling `20.00` MXN

#### Scenario: Follow-up keeps the display span
- **WHEN** the actor posts `500g de Café Molido a 240` and then `por kilo` with the same `conversation_id` and normalized `cafe molido` matches nothing
- **THEN** the persisted `product_name_snapshot` MUST be `Café Molido`

#### Scenario: Si does not complete a mass basis
- **WHEN** that mass-basis pending exists and the actor posts `sí`
- **THEN** no `SaleItem` MUST be persisted

### Requirement: Scripted free-concept utterances
The scripted interpreter MUST parse the closed free-concept utterances in `noncatalog-sale-item` after the existing closed command phrases and without repository access. `2 cajas de hielo a 18` MUST be an unsupported unit. `2 galletas A` MUST remain a catalog add-item decision with no unit price required.

#### Scenario: Galleta A is unchanged
- **WHEN** the scripted interpreter receives `2 galletas A`
- **THEN** the decision MUST be `add_sale_item` with quantity `2` and no required `unit_price`

### Requirement: Add-item audit and outbox record the source
A committed `sale.add_item@1` audit `after_payload` MUST include `source_type`, `product_id` (string or null), and `product_name`. The outbox event type MUST remain `sale.item.added` and its payload MUST include `sale_item_id`, `sale_session_id`, `source_type`, `product_id` (string or null), and `product_name`. The payload MUST NOT contain a guessed product id. Catalog message idempotency hashes MUST stay `raw_message|conversation_id|quantity|unit|product_query`. A free-concept hash MUST append `|unit_price`. Both MUST use operation type `lumo.message.add_sale_item`.

#### Scenario: Free-concept outbox
- **WHEN** a free-concept add commits
- **THEN** one `sale.item.added` event MUST have `source_type=free_concept` and `product_id` null, and the audit payload MUST match that source

#### Scenario: Catalog hash is unchanged
- **WHEN** `900gr zanahoria` is replayed with the same idempotency key and the existing catalog hash
- **THEN** the original catalog item MUST be returned and a second item MUST NOT be created

