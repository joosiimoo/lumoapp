## MODIFIED Requirements

### Requirement: Scripted interpreter for local and test
Local and test runtimes MUST use a non-vendor interpreter that can produce a valid `AgentDecision` for catalog add-item utterances, unit-only follow-ups, totalize synonyms `totalizar`, `total`, and `el total`, the closed payment phrases for cash, card, and transfer (trimmed, case-insensitive), and the closed day-summary phrases. A real LLM vendor SDK MUST NOT be required for the acceptance tests of this capability. The interpreter MUST remain compatible with a future `LLMProvider` (no repository or DB access). Count-product completion MUST NOT be hardcoded in the interpreter from catalog prices; missing unit for a possible count product MUST still reach application resolve. The interpreter MUST NOT write domain state. Day-summary matching MUST run after payment and totalize matching and before product parsing. After accent folding, case folding, whitespace collapse, and stripping one surrounding layer of `¿?¡!`, only `como vamos hoy`, `ventas de hoy`, and `cuanto vendimos hoy` MUST map to `intent=day_summary` and `candidate_tool=operational_day.summary@1`.

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

## ADDED Requirements

### Requirement: Tool operational_day.summary@1
`ToolRegistry` MUST register `operational_day.summary@1` as a read tool. Input MUST be an empty object and MUST NOT accept a client business date, sale count, or totals. Output MUST be the daily summary payload from persisted confirmed sales. Permission MUST be `sale.create`. Side effect MUST be `read`. Idempotency MUST NOT be required and the message path MUST NOT insert an idempotency row for this read. The orchestrator MUST route `day_summary` to the read workflow and MUST NOT open a business transaction. The workflow MUST NOT insert or update an OperationalDay, sale, or payment.

#### Scenario: Summary does not write
- **WHEN** `operational_day.summary@1` runs for a tenant
- **THEN** it MUST return the server summary and MUST NOT insert `operations.operational_days`, audit, outbox, or `idempotency_records` rows
