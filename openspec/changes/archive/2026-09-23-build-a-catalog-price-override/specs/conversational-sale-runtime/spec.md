## MODIFIED Requirements

### Requirement: Orchestrator delegates; workflow owns the write transaction
For intent `add_sale_item` with a resolvable product and a complete unit (explicit, or inferred only for `unit`/`package` products after unique resolve), and with no grounded price or a grounded price `Decimal`-equal to `Product.current_price`, the orchestrator MUST request interpretation and policy, then invoke the application add-item workflow. A unique match whose grounded price differs from `Product.current_price` MUST clarify under `CAT-001` with reason `catalog_price_override_reason_required` and MUST NOT open the write transaction on that turn. The later merchant reason turn, specified by `catalog-price-override`, MAY open that add-item write transaction and, inside it, MUST lock the product and decide from that locked `Product.current_price` before any session insert or idempotency reservation. For intent `add_sale_item` whose resolution is `none` and whose free-concept quantity, unit, and explicit grounded price are complete, including a per-kilogram basis when the unit is gram or kilogram, the orchestrator MUST invoke that same add-item workflow and MUST NOT invoke a second tool. For intent `totalize_sale`, it MUST invoke `TotalizeSaleSession` and MUST NOT run add-item. For intent `commit_sale`, it MUST invoke `CommitSaleSession` and MUST NOT run add-item or totalize. It MUST NOT open ORM sessions or database transactions. The add-item workflow MUST: (1) run `catalog.resolve_product@1` as a read **before** any write transaction; (2) if the match is unique, the grounded price is absent or `Decimal`-equal to `Product.current_price`, and the session is `open` or absent (including when only `confirmed` sessions exist), or a pending catalog override is ready to commit under `catalog-price-override`, or the match is `none` and the free-concept facts are complete, including a per-kilogram basis for gram or kilogram, open one write transaction that **locks** the existing active `SaleSession` when present (`SELECT ... FOR UPDATE`), re-reads status, creates or reuses the open session only if still open, and inserts the `SaleItem` using `sale.start@1` / `sale.add_item@1` semantics without an intervening commit; (3) write audit, outbox, and the message-level idempotency record in that same transaction; (4) compose `sale_item_added@1` only after commit. If the locked session is `ready_to_charge` (CASE A), it MUST deny under `SALE-002` without writing an item and MUST NOT start a second lookup in that same request to create a new sale. If that lookup finds no active session because a concurrent commit already confirmed (CASE B), the same request MAY create a new `open` session. If resolve is ambiguous, or a free-concept fact or per-kilogram basis is missing, or a unique catalog price differs and no merchant reason has been accepted, or policy is not `allow`, it MUST clarify or deny without opening the write transaction. Committing `sale.start@1` before `sale.add_item@1` on this path is forbidden. `match=none` alone MUST NOT skip a complete free-concept write. A gram or kilogram free concept without a per-kilogram basis MUST NOT open that write.

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

#### Scenario: Catalog price difference does not open a transaction yet
- **WHEN** Inicio posts `900gr tomate a 30` and Tomate `current_price` is `20.00`
- **THEN** the write transaction MUST NOT open and no `SaleSession` MUST be created

### Requirement: Minimum policies for these tools
`PolicyEngine` MUST evaluate `SEC-001`, `SEC-002`, `SEC-003`, `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, `SALE-001`, `SALE-002`, `SALE-003`, `SALE-004`, `SALE-005`, `PAY-001`, `DAY-001`, `CLOSE-001`, `CLOSE-002`, and `CLOSE-003` for this slice. Unregistered tools MUST be `deny`. Missing essential fields or low-confidence mutation MUST be `clarify`. An inactive product MUST be `deny` or `clarify` without persist. `match=none` without a complete explicit free-concept price and quantity MUST be `clarify` without persist. For gram or kilogram, `match=none` without an explicit per-kilogram basis MUST be `clarify` with reason `price_basis_required` and without persist. `match=none` with those facts, including the basis when the unit is mass, MUST be `allow` under `SALE-005`. A unique catalog match whose grounded price differs from `Product.current_price` MUST be `clarify` under `CAT-001` reason `catalog_price_override_reason_required` and MUST NOT be routed through `SALE-005`. An accepted override completion MUST be `allow` under `SALE-001` and `CAT-001` with reason `catalog_price_override`. An ambiguous match MUST stay `clarify` under `CAT-001` and MUST NOT be allowed as a free concept. Unknown payment method MUST be `clarify` under `PAY-001`. A cash count with no `OperationalDay` for today MUST be `clarify` under `CLOSE-001` without persisting anything. `CLOSE-003` MUST deny `closing.confirm@1` when the arguments include a server-owned total, difference, status, day id, snapshot id, or `closed_at`. Evaluation order MUST remain security, integrity, tenant and permissions, workflow gates, business rules, catalog and pricing, confidence, then user experience.

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

#### Scenario: Catalog price difference is not a free concept
- **WHEN** resolution is `unique` and the grounded price differs from `Product.current_price`
- **THEN** policy MUST clarify under `CAT-001` with reason `catalog_price_override_reason_required`, MUST NOT allow `SALE-005`, and MUST NOT reserve idempotency

#### Scenario: Cash count without a started day clarifies
- **WHEN** a decision names `closing.submit_cash_count@1` and no `OperationalDay` exists for today's business date
- **THEN** policy MUST NOT be `allow`, the response MUST clarify, and no `CashCount` or `OperationalDay` MUST be persisted

#### Scenario: CLOSE-003 rejects model-supplied close figures
- **WHEN** policy evaluates `closing.confirm@1` with arguments carrying `expected_cash`, `cash_difference`, or `operational_day_id`
- **THEN** the decision MUST be `deny` under `CLOSE-003` and no snapshot MUST be written

### Requirement: AgentDecision carries an explicit unit price candidate
`AgentDecision` MAY include optional `unit_price` as a decimal string. The interpreter MUST set it only when the user utterance contains an explicit amount. The workflow MUST NOT persist that candidate unless `ground_user_price` extracted the same `Decimal` amount from the raw message, or a pending clarification already stored that extracted amount. On a unique catalog match the workflow MUST compare the grounded amount to `Product.current_price` and MUST NOT ignore a mismatch. A mismatch MUST start `catalog_price_override` rather than storing the uttered amount on that turn. The workflow MUST reject a candidate that is not a positive decimal with at most two places. `source_type` MUST NOT be taken from the model as authority. The model MUST NOT supply `price_override_reason`.

#### Scenario: Priced unknown utterance
- **WHEN** the scripted interpreter receives `1 pastel 250`
- **THEN** `AgentDecision` MUST have `intent=add_sale_item`, a product query for pastel, `quantity=1`, and `unit_price=250`

#### Scenario: Catalog utterance stays an add
- **WHEN** the scripted interpreter receives `900gr zanahoria`
- **THEN** `AgentDecision` MUST still have `intent=add_sale_item`, `unit=gram`, and `candidate_tool=sale.add_item@1`

#### Scenario: Model price without merchant text does not override
- **WHEN** the user message is `900gr tomate` and the decision carries `unit_price` `30.00`
- **THEN** the workflow MUST NOT start a catalog price override

## ADDED Requirements

### Requirement: Pending catalog price override
When a unique catalog price differs, the runtime MUST store `kind=catalog_price_override` in the existing in-memory store keyed by `(business_id, actor_id, conversation_id)`. The entry MUST include the merchant product query, the resolved `product_id`, quantity, unit, the grounded override amount, and the observed catalog price. It MUST NOT include a reason. Schema `memory` MUST NOT be created. While that kind is pending, `cancelar`, `cancela`, and `no` after closed-phrase normalization MUST clear it and write nothing. A `parse_sale_utterance` result of kind `utterance` with both quantity and a display span MUST clear it and MUST be interpreted as a new add. Other text MUST be the reason candidate, not a model field. A closed totalize, payment, day-summary, cash-count, or close intent MUST clear it and run that intent.

#### Scenario: Reason is the next merchant message
- **WHEN** a Tomate override is pending and the actor posts `precio especial para cliente`
- **THEN** the runtime MUST treat that text as the reason and MUST NOT parse it as a new product

#### Scenario: Cancel writes nothing
- **WHEN** a catalog override is pending and the actor posts `no`
- **THEN** the pending entry MUST be cleared and no `SaleItem` MUST be written
