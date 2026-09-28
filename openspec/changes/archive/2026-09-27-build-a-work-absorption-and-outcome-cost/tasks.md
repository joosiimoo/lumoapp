## 1. Domain contracts

- [x] 1.1 Add `backend/app/domain/operations/work_absorption.py` with closed execution-mode enum, automation rollup (`manual` / `assisted` / `automated`), Daily Close `task_type` enum, approved baseline `@1` constant, evidence kind types, and pure helpers to derive row payloads from persisted facts. No I/O and no LLM
- [x] 1.2 Add `backend/app/domain/operations/outcome_cost.py` with component status enum, partial-total rules, USD money types, and Build A unavailable model/infra semantics
- [x] 1.3 Document intervention semantics: NULL unknown, 0 measured zero, >0 measured; Build A Daily Close uses NULL only

## 2. Persistence

- [x] 2.1 Add Alembic `0013_work_absorption_outcome_cost` per `persistence` delta: nullable intervention seconds, automation_level rollup check, `BEFORE INSERT` and `BEFORE UPDATE` completion freeze triggers, RLS, uniques, composite FKs. Do not backfill
- [x] 2.2 Add SQLAlchemy rows and repository methods for absorption and cost next to other `operations` types. Domain must not import ORM models
- [x] 2.3 Extend reset/integrity helpers to delete `work_absorption_records` and `outcome_costs` in the required order and to flag orphan instrumentation rows

## 3. Daily Close instrumentation

- [x] 3.1 Upsert absorption rows inside `sale.commit@1` / first OutcomeRun path for `organize_registered_sales` and `calculate_expected_cash` with NULL intervention seconds and derived `automation_level`
- [x] 3.2 Upsert `record_cash_count` and `reconcile_cash` inside new current CashCount transactions with evidence links
- [x] 3.3 Upsert all six task types inside `closing.confirm@1` before OutcomeRun transitions to `completed`, including `prepare_close` without making `closing.prepare@1` a write
- [x] 3.4 Wire the today-only initializer to the same helpers for open today only. Skip closed and older open days

## 4. Outcome-cost instrumentation

- [x] 4.1 Insert OutcomeCost when the OutcomeRun is first created while not `completed`; keep model/infra unavailable with NULL amounts
- [x] 4.2 Update `retry_count` only through the defined outcome-delivery retry hook. Persist NULL intervention seconds in Build A
- [x] 4.3 Finalize `cost_completeness=partial` and NULL `estimated_total_cost_amount` before OutcomeRun becomes `completed`

## 5. Lifecycle and idempotency

- [x] 5.1 Enforce `uq_work_absorption_records_task` upsert semantics so retries and recounts do not duplicate rows
- [x] 5.2 Enforce completion freeze on INSERT and UPDATE; repair paths use non-completed OutcomeRun until instrumentation exists, then complete in one transaction
- [x] 5.3 Keep reads (`closing.prepare@1`, Business Stream, NBA, export, summary) free of absorption/cost writes

## 6. Tenancy

- [x] 6.1 Scope all repository methods with `TenantContext`. Never accept client-supplied `business_id` for instrumentation writes
- [x] 6.2 Prove RLS on both new tables: tenant B cannot read tenant A rows

## 7. Automated tests

- [x] 7.1 Closed execution-mode enum and automation rollup mapping reject illegal values
- [x] 7.2 WorkAbsorptionRecord: OutcomeRun link, tenant, baseline `@1` (8 minutes total), E26 2/2/2 modes, NULL intervention in Build A, idempotent commit, evidence ids, no read-side writes
- [x] 7.3 Daily Close: six rows after close; merchant close behavior unchanged
- [x] 7.4 Intervention: NULL vs measured zero semantics; no fabrication from minutes or WorkItem elapsed time
- [x] 7.5 OutcomeCost: unavailable model/infra NULL not zero, partial completeness, USD money, NULL intervention in Build A
- [x] 7.6 Completed outcome: absorption and cost INSERT and UPDATE both rejected
- [x] 7.7 Repair close: instrumentation exists before OutcomeRun becomes `completed`
- [x] 7.8 Business Stream repeated GET leaves instrumentation unchanged; no new merchant route; no Flutter change required

## 8. Manual acceptance

- [x] 8.1 On Carrota, complete one normal Daily Close (sale, count, confirm). Inspect DB: OutcomeRun, six absorption rows, one OutcomeCost, modes and automation rollup defensible, baseline version copied, intervention NULL, cost partial with NULL total, merchant UI unchanged. No dashboard required

## 9. ADR acceptance

- [x] 9.1 After implementation and manual acceptance pass, set `docs/adr/ADR-028-work-absorption-and-outcome-cost-instrumentation.md` to Accepted

## 10. Archive readiness

- [x] 10.1 Run `openspec validate build-a-work-absorption-and-outcome-cost --strict` and `openspec validate --all --strict` before archive
- [x] 10.2 Sync main specs via archive workflow. Do not archive until tasks 1–8 and validations pass
