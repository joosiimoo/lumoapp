## Context

Product authority is PRD v0.11 only (RF-083, RF-084, RF-085, §9.12, §26.11, §28.22–§28.24, §31.4, CAO-007, E26). Build A already has `daily_close_ready@1` in `operations.outcome_runs` (ADR-024, migration `0011`), Daily Close WorkItems (ADR-023, `0010`), CashCount, ClosingSnapshot, source coverage, and factual events (`0012`). Business Stream is a pure today read (ADR-027). Head revision is `0012_source_coverage_event_memory`.

OutcomeRun statuses are only `in_progress`, `ready`, and `completed`. There is no stored `blocked`, `failed`, or `cancelled`. `closing.prepare@1` is a read. Writes that already maintain the OutcomeRun are successful `sale.commit@1`, a new current CashCount, successful `closing.confirm@1`, and the today-only initializer.

The LLM provider port has no token-usage metadata. Outcome write transactions do not call a model. Conversational routing may call a model, but those tokens are not attributed to an OutcomeRun today. Money is `Money` / `numeric` / decimal strings. Merchant operational amounts are MXN. Platform cost is a different currency.

ADR-024 forbids a cost summary on `operations.outcome_runs`. This change keeps that row small and adds related instrumentation tables.

Directory:

- pure contracts in `backend/app/domain/operations/work_absorption.py` and `backend/app/domain/operations/outcome_cost.py` (no FastAPI, SQLAlchemy, or LLM SDK);
- sync inside the existing Daily Close write helpers (`sync_daily_close_outcome.py` and the close path), not a new HTTP use case;
- tables and repository methods next to the other `operations` types.

No `workflow` schema. No new event store. No Flutter module. No new route.

## Goals / Non-Goals

**Goals:**

- Classify each Daily Close administrative task with the closed PRD §9.12 execution-mode enum.
- Persist `WorkAbsorptionRecord` so a completed OutcomeRun can answer what Lumo absorbed, what still needed the merchant, what needed internal humans, how mode changed, step counts, estimated minutes saved, and linked evidence.
- Persist per-OutcomeRun cost with explicit measured vs estimated vs unavailable components.
- Observe existing Daily Close behavior. Do not add close steps to make metrics prettier.
- Keep instrumentation tenant-scoped, idempotent, and frozen after completion.

**Non-Goals:**

- Merchant or admin dashboards, Business Stream / Hoy / Memoria metrics, public cost API, Flutter product-surface change.
- Pricing, billing, margin, revenue, labor rates, merchant savings claims.
- LLM-estimated minutes, a scoring model, AutomationCandidate, workflow redesign.
- Build B partial completion, reopen, reversible/under-policy Daily Close execution, internal ReviewTask.
- External cloud billing, latency-derived infra cost, historical backfill of closed days.

## Decisions

### 1. Execution mode is the PRD §9.12 closed enum

Persist these values 1:1. Do not persist the RF-083 Spanish shorthand.

| Persisted value | RF-083 | Meaning |
|---|---|---|
| `manual_by_business` | manual | The business executed the task without Lumo preparing or performing it. |
| `assisted_by_lumo` | asistida | The business executed it with live Lumo assistance. Not produced by Daily Close Build A. |
| `prepared_by_lumo` | preparada | Lumo produced the result. The business may look at it. This task has no remaining required human execution step. |
| `executed_with_confirmation` | ejecutada con confirmación | Lumo requested or prepared the act; a business action is required for the task to count as done. |
| `executed_and_reversible` | reversible | Lumo executed an undoable act. Not used. Reopen is unregistered. |
| `executed_under_policy` | bajo política | Lumo executed under a standing policy with no per-instance confirmation. Not used. |
| `reviewed_by_lumo_operator` | revisión interna | An internal Lumo operator reviewed the task. Not used. Build A Daily Close has no ReviewTask. |
| `fully_automated` | automatizada | Lumo executed the task. No remaining required human step. |

Mode is how the task was executed. It is not WorkItem status, OutcomeRun status, actor, risk, or a percentage.

Daily Close Build A produces only `fully_automated`, `prepared_by_lumo`, and `executed_with_confirmation`. `previous_execution_mode` is always `manual_by_business` for baseline `@1`. The other enum values remain legal so the contract matches PRD §9.12.

Rejected: a 0–100 score, a different persisted vocabulary, or mapping mode onto WorkItem type.

### 2. Daily Close task taxonomy is six administrative jobs

Derived from the implemented flow, not from API calls or chat turns.

| `task_type` | Implemented behavior | Why it is a unit |
|---|---|---|
| `organize_registered_sales` | `sale.commit@1` attaches confirmed sales to the OperationalDay; `summarize_day` lists them. | Absorbing reconstruction of the day's registered sales. |
| `calculate_expected_cash` | Server sum of recorded cash payments. | Absorbing the expected-cash total. |
| `record_cash_count` | Merchant submits `closing.submit_cash_count@1`. WorkItem `cash_count_required`. | The remaining physical count. |
| `reconcile_cash` | Server `counted − expected`, `cash_status`, and optional `cash_difference_review`. | Compare and surface difference are one job. Balanced still reconciles (difference `0.00`). |
| `prepare_close` | `closing.prepare@1` is the prepared package. Written at confirm because prepare is a read. | Absorbing assembly of the close record. |
| `confirm_close` | `closing.confirm@1` writes ClosingSnapshot, closes the day, completes the OutcomeRun. | Merchant confirmation. System completion is not a second task. |

Rejected as separate types: request vs record cash count; compare vs surface difference; complete close vs confirm; one record per sale, GET, or message.

This is the E26 intent mapped to current code, not a hard-coded slogan. Baseline `@1` has six formerly manual tasks. In Lumo: two `fully_automated` (eliminated as merchant work), two `prepared_by_lumo`, two `executed_with_confirmation`. Short, over, and balanced closes use the same six types. `reconcile_cash` does not disappear when balanced.

### 3. Versioned static baseline, copied onto the row

Code constant, not a UI, not an LLM, not a database table in this slice:

`daily_close_ready@1/work_absorption_baseline@1`

| task | previous | current | `human_steps_before` | `human_steps_after` | `estimated_minutes_saved` |
|---|---|---|---|---|---|
| `organize_registered_sales` | `manual_by_business` | `fully_automated` | 1 | 0 | 2 |
| `calculate_expected_cash` | `manual_by_business` | `fully_automated` | 1 | 0 | 2 |
| `record_cash_count` | `manual_by_business` | `executed_with_confirmation` | 1 | 1 | 0 |
| `reconcile_cash` | `manual_by_business` | `prepared_by_lumo` | 1 | 0 | 2 |
| `prepare_close` | `manual_by_business` | `prepared_by_lumo` | 1 | 0 | 2 |
| `confirm_close` | `manual_by_business` | `executed_with_confirmation` | 1 | 1 | 0 |

Rule: `estimated_minutes_saved = (human_steps_before − human_steps_after) × 2`. **Product decision (approved):** two estimated minutes per eliminated human step for `daily_close_ready@1/work_absorption_baseline@1`. This is a **provisional pilot estimate**, not measured elapsed time, not a merchant-facing ROI claim. It is **versioned**; a future `baseline@2` may recalibrate constants without changing historical rows. Copy all integers and `baseline_version` onto `WorkAbsorptionRecord` at write time.

`baseline_version` is not in PRD §28.24. It is required so historical records stay auditable.

Rejected: runtime LLM estimates; deriving steps from conversation length; a baseline-management UI.

### 4. WorkAbsorptionRecord contract

Table `operations.work_absorption_records`.

| Column | Null | Notes |
|---|---|---|
| `id` | no | UUIDv7 |
| `business_id` | no | From `TenantContext` / owning OutcomeRun. Never from an untrusted parameter. |
| `outcome_run_id` | no | Composite FK `(outcome_run_id, business_id)` → `outcome_runs (id, business_id)` |
| `work_item_id` | yes | Optional. Composite FK `(work_item_id, business_id)` → `work_items (id, business_id)` after `UNIQUE (id, business_id)` is added |
| `task_type` | no | Closed Daily Close taxonomy |
| `previous_execution_mode` | no | Closed enum |
| `current_execution_mode` | no | Closed enum |
| `human_steps_before` | no | INTEGER `>= 0` |
| `human_steps_after` | no | INTEGER `>= 0` |
| `estimated_minutes_saved` | no | INTEGER `>= 0` |
| `business_intervention_seconds` | yes | NULL = unknown / not measured; `0` = measured zero; `>0` = measured duration |
| `internal_intervention_seconds` | yes | Same semantics as business |
| `automation_level` | no | Closed rollup: `manual`, `assisted`, `automated` (derived from `current_execution_mode`, not equal to it) |
| `evidence_ids` | no | JSONB array of `{kind, id}` objects, not payloads |
| `baseline_version` | no | Copied identifier |
| `created_at` | no | timestamptz UTC |
| `updated_at` | no | timestamptz UTC; needed because live rows upsert |

`updated_at` and `baseline_version` are the only non-PRD columns. Both are required for upsert-then-freeze and historical stability.

`automation_level` is a coarse aggregation only. It is not a percentage and not a "Lumo efficiency score". Derivation from `current_execution_mode`:

| `current_execution_mode` | `automation_level` |
|---|---|
| `manual_by_business` | `manual` |
| `assisted_by_lumo`, `prepared_by_lumo`, `executed_with_confirmation`, `reviewed_by_lumo_operator` | `assisted` |
| `fully_automated`, `executed_under_policy`, `executed_and_reversible` | `automated` |

No runtime LLM classification. Execution mode remains the detailed factual field.

Unique: `uq_work_absorption_records_task` on `(business_id, outcome_run_id, task_type)`. One record per task per OutcomeRun. Recounts, later sales, and close retries reuse that row. They do not insert a second generation. A returned `cash_difference_review` WorkItem does not create a second `reconcile_cash` record.

### 5. When records are created

Same parent transactions as OutcomeRun. Reads never create them.

| Event | Records upserted |
|---|---|
| First `sale.commit@1` / OutcomeRun insert | `organize_registered_sales`, `calculate_expected_cash`. Insert `OutcomeCost`. |
| Later confirmed sale | Refresh evidence on those two if facts changed. No duplicate. |
| New current CashCount | `record_cash_count`, `reconcile_cash`. Link count WorkItem / difference WorkItem when present. |
| Equal-amount cash-count read-back | No write. |
| `closing.prepare@1`, Business Stream, NBA, export, summary | No write. |
| `closing.confirm@1` | Upsert all six with final evidence, including `prepare_close` and `confirm_close`, **then** complete the OutcomeRun. Finalize `OutcomeCost`. |
| Close repair missing OutcomeRun | Insert or restore OutcomeRun as `in_progress` or `ready`, insert/upsert all instrumentation, then set `completed` in the same transaction. MUST NOT insert instrumentation after the run is already `completed`. |
| Today-only initializer | Same as the facts now allow. Skip closed and older open days. No historical backfill. |
| Idempotent parent replay | No second row. |

`prepare_close` is recorded at confirm because `closing.prepare@1` MUST remain a read.

### 6. Intervention seconds are unknown unless measured

`business_intervention_seconds`: active merchant effort to complete that task.

`internal_intervention_seconds`: active Lumo internal-operator effort.

Do not count backend execution time, GET latency, or Flutter redraws.

Build A cannot measure active seconds. There is no ReviewTask timer. WorkItem elapsed open→resolve MUST NOT be used.

Persist **NULL** for both intervention fields on normal Daily Close instrumentation. Semantics: **NULL** = unknown / not measured; **0** = measured zero seconds; **>0** = measured duration. Do not convert `estimated_minutes_saved` into seconds. Do not fabricate non-null values.

Merchant actions still happened (`record_cash_count`, `confirm_close`). Duration remains unknown until a future measurement source exists.

### 7. Evidence ids, not payloads

`evidence_ids` is a JSONB array of objects `{ "kind": "<closed>", "id": "<uuid>" }`. No duplicated sale lines, snapshot bodies, or prose.

Allowed `kind`: `outcome_run`, `work_item`, `cash_count`, `closing_snapshot`, `business_event`, `source_coverage`.

Every record MUST include `{kind: outcome_run, id: <run>}`. Additional ids:

- `organize_registered_sales`: sales `source_coverage` when present; not one id per sale.
- `record_cash_count`: current `cash_count`; `cash_count_required` WorkItem when present; `cash_count_recorded` event when present.
- `reconcile_cash`: current `cash_count`; `cash_difference_review` WorkItem when present.
- `prepare_close` / `confirm_close` at completion: `closing_snapshot`; `daily_close_completed` event when present; `close_confirmation_required` WorkItem when it existed.

Do not create a new event store.

### 8. Cost lives on OutcomeCost, not on OutcomeRun

PRD §26.11 says each OutcomeRun must record cost. It does not require those columns on `operations.outcome_runs`. ADR-024 already forbids `cost_summary` on that row.

One `operations.outcome_costs` row per OutcomeRun. Unique `(business_id, outcome_run_id)`. Composite FK to `outcome_runs (id, business_id)`.

Rejected: JSON `cost_summary` on OutcomeRun (conflicts with ADR-024, mixes completeness into evidence). Rejected: columns on OutcomeRun (bloats the lifecycle row, harder to freeze independently).

ADR-028 (Proposed) records this.

### 9. Measured vs estimated vs unavailable

Never store unavailable money as `0.00`.

| Component | Build A treatment | Why |
|---|---|---|
| Model calls / tokens / model cost | `unavailable`; amounts and token counts NULL | Provider port has no usage metadata. Outcome writes do not call a model. Conversation tokens are not attributed to Daily Close. Do not fabricate. Do not force an LLM call. |
| Infrastructure | `unavailable`; amount NULL | No observability allocation. Do not use request latency. Do not query cloud billing. A configured per-outcome dollar would be false precision. |
| Storage / evidence | `unavailable` | Not metered. |
| Integrations | `unavailable` | No billed integration in this path. |
| Support / review / double control | `unavailable` | No internal review path. |
| Retries | `measured` integer `>= 0` | Count defined below. Happy path is 0 meaning no recorded retry. |
| Business / internal seconds | nullable integer; Build A Daily Close uses NULL | Same NULL / 0 / >0 semantics as absorption. Not converted to money. |
| Labor / avoided cost in MXN or USD | not stored | Inferred rates and merchant savings claims are non-goals. |

`estimated_total_cost_amount` is NULL while any monetary component intended for the total is unavailable. Build A Daily Close therefore has NULL total and `cost_completeness=partial`. Completeness MUST be stored. A NULL total plus `partial` is the honest state. Do not sum NULLs as zero.

### 10. Money contract

Platform cost currency is **USD**. Model and infra invoices, when they exist later, are USD. Do not mix with MXN merchant operational amounts.

Amounts: `numeric(12,2)` plus `currency CHAR(3)`. Python `Money`. No float. JSON decimal strings. `currency` on the cost row is `USD` even when all money columns are NULL.

### 11. Retry count

`retry_count` is the number of recorded **server-side re-attempts of outcome-delivery writes** after a retryable failure for this OutcomeRun.

Counted: a retryable error on `sale.commit@1`, a new CashCount insert, or `closing.confirm@1` that is then successfully retried as a new attempt (new idempotency operation), recorded by the instrumentation hook.

Not counted: idempotent replay of the same key; equal-amount cash-count read-back; `closing.prepare@1`; GET refreshes including Business Stream and NBA; Flutter rebuilds; merchant recounts (those are operational facts, not system retries).

Build A has no auto-retry loop on those writes. The hook still exists, so `0` is **measured: no recorded retry**, not an invented unavailable zero. `retry_count_status` is `measured`.

### 12. Lifecycle and freeze

```
in_progress / ready  →  INSERT and UPDATE allowed
closing.confirm@1    →  final upsert, then transition OutcomeRun to completed
completed            →  INSERT and UPDATE on absorption/cost rejected
```

`blocked` / `failed` / `cancelled` remain absent. Do not add them for instrumentation.

Database MUST enforce immutability when the owning OutcomeRun `status` is `completed`: **both `BEFORE INSERT` and `BEFORE UPDATE`** on `work_absorption_records` and `outcome_costs` MUST reject the statement. There is **no** exception for missing instrumentation after the run is already `completed`.

Repair paths that must end `completed` in one transaction: create or restore the OutcomeRun in `in_progress` or `ready`, insert and finalize all absorption and cost rows, then set `status=completed` (and link snapshot) in that same transaction.

No silent overwrite of completed history. **No correction table in Build A.** Late telemetry is dropped. A calculation bug requires a later slice (append-only correction), not an in-place fix of completed rows.

### 13. Tenancy

`business_id` from `TenantContext` or the owning OutcomeRun already loaded in that tenant session. RLS `ENABLE` + `FORCE` + policy `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`. Grant `lumo_app` `SELECT, INSERT, UPDATE, DELETE`. No `BYPASSRLS`. Cross-business reads return nothing.

### 14. No merchant API, no Flutter change

Acceptance is repository/tests plus one manual SQL/DB inspection after a normal Carrota close. Do not add `GET /api/v1/outcome-costs` or an absorption route. Business Stream payload stays exactly as ADR-027. Flutter must not show cost, tokens, infra, absorption percentage, internal intervention, or automation score.

### 15. Audit

Insert writes `work_absorption.created` or `outcome_cost.created` in the same transaction. Upserts that do not insert are silent. Completion does not add a third audit type; `outcome_run.status_changed` already marks completion. No outbox event. No new idempotency operation.

## Risks / Trade-offs

[E26 numbers look prescribed] → Mapping is defended from current Daily Close jobs, not copied as a slogan. Minutes-per-step `2` is an **approved** provisional pilot estimate for baseline `@1`, not measured elapsed time.

[NULL intervention confused with "no human involved"] → Spec and ADR state NULL = not measured. Remaining human tasks are visible via `executed_with_confirmation` and step counts.

[NULL total looks like missing data] → `cost_completeness=partial` is required. Unavailable money is NULL, never `0.00`.

[Conversation LLM cost omitted] → Honest. Attribution would mix sales chat into Daily Close. Provider usage is not captured.

[Trigger freeze vs same-transaction confirm] → Final upsert happens before OutcomeRun status becomes `completed`.

[Unique task key hides recount generations] → Recounts are one administrative cash-count job. WorkItems already keep generations; absorption does not duplicate them.

## Migration Plan

Design only. Do not create the migration in this OpenSpec step.

1. Alembic `0013_work_absorption_outcome_cost`, `down_revision = 0012_source_coverage_event_memory`.
2. `ALTER TABLE operations.work_items ADD CONSTRAINT uq_work_items_id_business UNIQUE (id, business_id)` if missing, for the optional absorption FK.
3. Create `operations.work_absorption_records` and `operations.outcome_costs` with checks, uniques, composite FKs, indexes on `business_id` and `outcome_run_id`, RLS, grants.
4. Create `BEFORE INSERT` and `BEFORE UPDATE` triggers on both tables that reject any statement when the owning OutcomeRun `status` is `completed`.
5. Migration itself inserts no rows. Downgrade refuses if either table has rows.
6. Reset helper deletes `work_absorption_records` then `outcome_costs` then `work_items` then `outcome_runs`.
7. Rollback: downgrade after tables are empty, or leave `0012` as head if the revision was not applied.

## Open Questions

1. Whether a future slice should attribute **conversation**-provider tokens to Daily Close once usage metadata exists (explicitly deferred; outcome-delivery writes remain non-LLM).
2. MXN reporting conversion for internal USD cost (conversion is out of this slice).
