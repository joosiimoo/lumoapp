## MODIFIED Requirements

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
`PolicyEngine` MUST evaluate `SEC-001`, `SEC-002`, `SEC-003`, `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, `SALE-001`, `SALE-002`, `SALE-003`, `SALE-004`, `PAY-001`, `DAY-001`, `CLOSE-001`, `CLOSE-002`, and `CLOSE-003` for this slice. Unregistered tools MUST be `deny`. Missing essential fields or low-confidence mutation MUST be `clarify`. Inactive or unknown product MUST be `deny` or `clarify` without persist. Unknown payment method MUST be `clarify` under `PAY-001`. A cash count with no `OperationalDay` for today MUST be `clarify` under `CLOSE-001` without persisting anything. `CLOSE-003` MUST deny `closing.confirm@1` when the arguments include a server-owned total, difference, status, day id, snapshot id, or `closed_at`. Evaluation order MUST remain security, integrity, tenant and permissions, workflow gates, business rules, catalog and pricing, confidence, then user experience.

#### Scenario: Unregistered reopen denied
- **WHEN** a decision names `closing.reopen@1`
- **THEN** policy MUST `deny` under `SEC-002` and no close or reopen MUST occur

#### Scenario: Positive quantity policy
- **WHEN** add-item arguments include a non-positive quantity
- **THEN** policy or domain validation MUST block the mutation under `SALE-001`

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
For intent `record_cash_count`, the orchestrator MUST request policy and then invoke the cash-count write workflow, and MUST NOT run add-item, totalize, commit, or the day-summary read. For intent `close_preparation`, it MUST invoke the preparation read workflow and MUST NOT run any write workflow. For intent `request_close`, it MUST invoke the preparation read and, only when that read is confirmable, attach a confirmation token. It MUST NOT call `closing.confirm@1` for `request_close`. For intent `confirm_close`, it MUST pass `client_context.confirmation_token` into `closing.confirm@1` and MUST ignore a model-supplied token. The orchestrator MUST NOT open ORM sessions or database transactions and MUST NOT calculate expected cash or a difference. The write workflows MUST own one application transaction as specified by `cash-count-foundation` and `daily-close-confirmation`. `daily_close_preparation@1` MUST be composed only after a cash-count commit, or immediately for a non-writing preparation or request-close. `daily_close_confirmed@1` MUST be composed only after a confirm commit or from a committed snapshot read. The read workflow MUST NOT open a write transaction.

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
