## MODIFIED Requirements

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

### Requirement: Orchestrator delegates; workflow owns the write transaction
For intent `add_sale_item` with a resolvable product and a complete unit (explicit, or inferred only for `unit`/`package` products after unique resolve), the orchestrator MUST request interpretation and policy, then invoke the application add-item workflow. For intent `totalize_sale`, it MUST invoke `TotalizeSaleSession` and MUST NOT run add-item. For intent `commit_sale`, it MUST invoke `CommitSaleSession` and MUST NOT run add-item or totalize. It MUST NOT open ORM sessions or database transactions. The add-item workflow MUST: (1) run `catalog.resolve_product@1` as a read **before** any write transaction; (2) if unique and the session is `open` or absent (including when only `confirmed` sessions exist), open one write transaction that **locks** the existing active `SaleSession` when present (`SELECT ... FOR UPDATE`), re-reads status, creates or reuses the open session only if still open, and inserts the `SaleItem` using `sale.start@1` / `sale.add_item@1` semantics without an intervening commit; (3) write audit, outbox, and the message-level idempotency record in that same transaction; (4) compose `sale_item_added@1` only after commit. If the locked session is `ready_to_charge` (CASE A), it MUST deny under `SALE-002` without writing an item and MUST NOT start a second lookup in that same request to create a new sale. If that lookup finds no active session because a concurrent commit already confirmed (CASE B), the same request MAY create a new `open` session. If resolve is ambiguous or none, or policy is not `allow`, it MUST clarify or deny without opening the write transaction. Committing `sale.start@1` before `sale.add_item@1` on this path is forbidden.

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

#### Scenario: Commit is a separate workflow
- **WHEN** Inicio posts `efectivo` for a `ready_to_charge` session
- **THEN** `CommitSaleSession` MUST run, add-item and totalize MUST NOT run, and `sale_confirmed@1` MUST be composed only after commit

### Requirement: Message-level idempotency
`POST /api/v1/lumo/messages` MUST treat `Idempotency-Key` as the key for the whole message workflow. Add-item MUST use `operation_type` `lumo.message.add_sale_item`. Totalize MUST use `operation_type` `lumo.message.totalize_sale`. Commit MUST use `operation_type` `lumo.message.commit_sale`. These MUST NOT share one operation type.

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

### Requirement: Minimum policies for these tools
`PolicyEngine` MUST evaluate `SEC-001`, `SEC-002`, `SEC-003`, `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, `SALE-001`, `SALE-002`, `SALE-003`, `SALE-004`, and `PAY-001` for this slice. Unregistered tools MUST be `deny`. Missing essential fields or low-confidence mutation MUST be `clarify`. Inactive or unknown product MUST be `deny` or `clarify` without persist. Unknown payment method MUST be `clarify` under `PAY-001`. Evaluation order MUST remain security, integrity, tenant and permissions, workflow gates, business rules, catalog and pricing, confidence, then user experience.

#### Scenario: Unregistered closing tool denied
- **WHEN** a decision names `closing.confirm@1`
- **THEN** policy MUST `deny` under `SEC-002` and no close MUST occur

#### Scenario: Positive quantity policy
- **WHEN** add-item arguments include a non-positive quantity
- **THEN** policy or domain validation MUST block the mutation under `SALE-001`

### Requirement: Scripted interpreter for local and test
Local and test runtimes MUST use a non-vendor interpreter that can produce a valid `AgentDecision` for catalog add-item utterances, unit-only follow-ups, totalize synonyms `totalizar`, `total`, and `el total`, and the closed payment phrases for cash, card, and transfer (trimmed, case-insensitive). A real LLM vendor SDK MUST NOT be required for the acceptance tests of this capability. The interpreter MUST remain compatible with a future `LLMProvider` (no repository or DB access). Count-product completion MUST NOT be hardcoded in the interpreter from catalog prices; missing unit for a possible count product MUST still reach application resolve. The interpreter MUST NOT write domain state.

#### Scenario: Fake provider still boots
- **WHEN** no vendor LLM is configured
- **THEN** health MAY report fake/non-ready and `POST /api/v1/lumo/messages` MUST still execute the golden path via the scripted interpreter

#### Scenario: Totalize interpretation
- **WHEN** the scripted interpreter receives `totalizar`
- **THEN** `AgentDecision` MUST have `intent=totalize_sale` and `candidate_tool=sale.totalize@1`

#### Scenario: Cash interpretation
- **WHEN** the scripted interpreter receives `pagar en efectivo`
- **THEN** `AgentDecision` MUST have `intent=commit_sale`, `payment_method=cash`, and `candidate_tool=sale.commit@1`

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

## ADDED Requirements

### Requirement: AgentDecision extension for commit
`AgentDecision` MUST keep existing add-item and totalize fields and MAY add optional `payment_method` (`cash` | `card` | `transfer`). Intent `commit_sale` MUST be used for approved payment phrases. `candidate_tool` MUST be `sale.commit@1` or null. Invalid provider output MUST still be discarded with no mutation.

#### Scenario: Golden card interpretation
- **WHEN** the scripted interpreter receives `con tarjeta`
- **THEN** `AgentDecision` MUST have `intent=commit_sale`, `payment_method=card`, and `candidate_tool=sale.commit@1`

### Requirement: Tool sale.commit@1
`ToolRegistry` MUST register `sale.commit@1` as a write tool. Input MUST be `{ "conversation_id": string|null, "payment_method": "cash"|"card"|"transfer" }`. Input MUST NOT include amount, change, or a client-calculated total. Output MUST include `sale_session_id`, `payment_id`, `status` (`confirmed`), `item_count`, `currency`, `total`, `payment` (`method`, `amount`, `status=recorded`), and `items`. Permission MUST be `sale.create`. Idempotency MUST be required for the **transition** when commit is invoked as its own public operation. On the message path, a transitioning commit, `Payment`, audit, outbox, and message idempotency MUST share one application-owned write transaction after locking the session row. The tool MUST lock the active session for the interaction context, then:

- if `status=ready_to_charge`: Decimal-sum persisted items, insert one `Payment` with that total and `business_id` copied from the locked session / `TenantContext` (never from client or tool input), persist `confirmed`, write `sale.commit@1` audit, enqueue `sale.confirmed` and `payment.recorded`, complete `lumo.message.commit_sale`;
- if no active session and the latest session is `confirmed`: return the current confirmation as a stable read-back with no status change, no second `Payment`, no second outbox, no transition audit, and no new idempotency record;
- if `status=open`: deny without mutation;
- if no session: deny without mutation.

Compose `sale_confirmed@1` after commit on the transition path, and from current persisted rows on the read-back path. Catalog prices MUST NOT be re-read in this change; the ready-to-charge item snapshots remain the financial truth.

#### Scenario: Commit ready_to_charge session
- **WHEN** `sale.commit@1` runs for a ready Carrota session totaling `56.50` with `payment_method=cash`
- **THEN** it MUST persist `status=confirmed`, one `Payment` of `56.50` cash, return that total, write `sale.commit@1` audit, and enqueue `sale.confirmed` and `payment.recorded`

#### Scenario: Commit already confirmed is a stable read-back
- **WHEN** commit runs again for a conversation whose latest session is `confirmed` with a different idempotency key
- **THEN** status MUST stay `confirmed`, a second `Payment` MUST NOT be written, a second `sale.confirmed` outbox event MUST NOT be written, and no new `lumo.message.commit_sale` idempotency row MUST be created

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
