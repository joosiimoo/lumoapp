## MODIFIED Requirements

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

## ADDED Requirements

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
