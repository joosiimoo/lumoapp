## ADDED Requirements

### Requirement: Agent message endpoint
The API MUST expose `POST /api/v1/lumo/messages` under `/api/v1`. The body MUST accept `message` and MAY accept `conversation_id` and `client_context`. The route MUST authenticate, derive `TenantContext` from the session, require `Idempotency-Key`, and propagate `X-Correlation-ID`. The handler MUST invoke the single `LumoOrchestrator` and MUST NOT contain catalog or pricing rules.

#### Scenario: Authenticated send
- **WHEN** a Carrota actor posts `{"message": "900gr zanahoria"}` with a valid session and idempotency key
- **THEN** the orchestrator MUST run and the HTTP handler MUST NOT calculate `line_total`

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
`ToolRegistry` MUST register `sale.start@1` as a write tool. Input MUST be `{ "conversation_id": string|null }`. Output MUST be `{ "sale_session_id": uuid, "status": "open", "created": boolean, "item_count": integer }`. Permission MUST be `sale.create`. Idempotency MUST be required when start is invoked as its own public operation. The tool MUST reuse the open session for the interaction context. When composed on the message path, start/reuse MUST participate in the workflow write transaction (see message-path transaction requirement) and MUST NOT commit an empty session before add-item.

#### Scenario: Start is idempotent
- **WHEN** `sale.start@1` is invoked twice as its own public operation with the same tenant, actor, conversation, key, and payload
- **THEN** one `SaleSession` MUST exist and both results MUST return the same `sale_session_id`

### Requirement: Tool sale.add_item@1
`ToolRegistry` MUST register `sale.add_item@1` as a write tool. Input MUST be `{ "sale_session_id": uuid, "product_id": uuid, "quantity": decimal-string, "unit": "gram"|"kilogram"|"unit"|"package" }`. Output MUST include `sale_session_id`, `sale_item_id`, `product_id`, `product_name`, `quantity_input`, `unit_input`, `quantity_normalized`, `unit_normalized`, `unit_price`, `line_total`, `session_item_count`, and `session_total` (money as decimal string plus `MXN`). Permission MUST be `sale.create`. Idempotency MUST be required when add-item is invoked as its own public operation. The tool MUST re-read the product, reject inactive/missing products, normalize quantity, calculate `line_total`, persist, and audit. On the message path, those writes MUST share the workflow transaction with session create/reuse.

#### Scenario: Add 900 grams of Zanahoria
- **WHEN** the tool runs with the seeded Zanahoria `product_id`, `quantity=900`, and `unit=gram` on an open session
- **THEN** it MUST persist `quantity_normalized=0.900`, `unit_normalized=kilogram`, `unit_price.amount=25.00`, `line_total.amount=22.50`, and an audit event in the same committed state

#### Scenario: Replay identical add-item
- **WHEN** the same tenant resubmits `sale.add_item@1` with the same idempotency key and payload hash
- **THEN** the original item id and body MUST be returned and a second `SaleItem` MUST NOT be created

### Requirement: Orchestrator delegates; workflow owns the write transaction
For intent `add_sale_item` with complete product, quantity, and unit, the orchestrator MUST request interpretation and policy, then invoke the application add-item workflow. It MUST NOT open ORM sessions or database transactions. The workflow MUST: (1) run `catalog.resolve_product@1` as a read **before** any write transaction; (2) if unique, open one write transaction that creates or reuses the open `SaleSession` and inserts the `SaleItem` using `sale.start@1` / `sale.add_item@1` semantics without an intervening commit; (3) write audit, outbox, and the message-level idempotency record in that same transaction; (4) compose `sale_item_added@1` only after commit. If resolve is ambiguous or none, or policy is not `allow`, it MUST clarify or deny without opening the write transaction. Committing `sale.start@1` before `sale.add_item@1` on this path is forbidden.

#### Scenario: Golden path sequences tools
- **WHEN** Inicio posts `900gr zanahoria` for Carrota
- **THEN** resolve MUST run first, start/reuse and add-item MUST commit together, and a `SaleItem` MUST exist only after that commit

#### Scenario: Ambiguity stops before mutation
- **WHEN** product resolution is `ambiguous` or `none`
- **THEN** `sale.start@1` and `sale.add_item@1` MUST NOT run as a result of that message and no `SaleSession` MUST be created for it

#### Scenario: Failed add-item does not leave a new session
- **WHEN** the message would create a new `SaleSession` and add-item fails before commit
- **THEN** neither the session nor the item MUST remain

### Requirement: Message-level idempotency
`POST /api/v1/lumo/messages` MUST treat `Idempotency-Key` as the key for the whole add-item workflow (`operation_type` scoped to the message mutation), not as two separately committed start and add-item operations.

#### Scenario: Replay of the golden message
- **WHEN** the same tenant resubmits `"900gr zanahoria"` with the same message idempotency key and payload hash
- **THEN** the original session id, item id, and body MUST be returned and a second `SaleItem` MUST NOT be created

### Requirement: Minimum policies for these tools
`PolicyEngine` MUST evaluate `SEC-001`, `SEC-002`, `SEC-003`, `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, and `SALE-001` for this slice. Unregistered tools MUST be `deny`. Missing essential fields or low-confidence mutation MUST be `clarify`. Inactive or unknown product MUST be `deny` or `clarify` without persist. Evaluation order MUST remain security, integrity, tenant and permissions, workflow gates, business rules, catalog and pricing, confidence, then user experience.

#### Scenario: Unregistered sale.commit denied
- **WHEN** a decision names `sale.commit@1`
- **THEN** policy MUST `deny` under `SEC-002` and no sale confirmation MUST occur

#### Scenario: Positive quantity policy
- **WHEN** add-item arguments include a non-positive quantity
- **THEN** policy or domain validation MUST block the mutation under `SALE-001`

### Requirement: Scripted interpreter for local and test
Local and test runtimes MUST use a non-vendor interpreter that can produce a valid `AgentDecision` for `900gr zanahoria` and can return clarification for missing unit or unsupported intent. A real LLM vendor SDK MUST NOT be required for the acceptance tests of this change.

#### Scenario: Fake provider still boots
- **WHEN** no vendor LLM is configured
- **THEN** health MAY report fake/non-ready and `POST /api/v1/lumo/messages` MUST still execute the golden path via the scripted interpreter
