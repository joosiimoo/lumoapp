## 1. Source Coverage domain

- [x] 1.1 Add `backend/app/domain/operations/source_coverage.py` with domains `sales` and `cash_count`, source `manual_capture`, status `observed`, limitation `only_lumo_registered_operations`, and the pure recorded-operations declaration. The persisted row is insert-if-absent and has `created_at` only. No `updated_at`, FastAPI, SQLAlchemy, percentage, or `declared_complete`

## 2. Event Memory domain

- [x] 2.1 Add `backend/app/domain/operations/business_event.py` with `sale_confirmed`, `cash_count_recorded`, and `daily_close_completed`, exact fact keys, and `source_type=manual_capture` as the operational data source of the fact. `daily_close_completed` is proved by `closing_snapshot` and the ClosingSnapshot id. No embedding, prose, workflow-origin field, or coverage foreign key

## 3. Migration and persistence

- [x] 3.1 Add Alembic `0012_source_coverage_event_memory` down from `0011_daily_close_outcome`: both tables, checks, unique keys, composite day foreign keys, FORCE RLS, `tenant_isolation`, `SELECT`/`INSERT`/`DELETE` for `lumo_app`, and `business_events_immutable`. `source_coverage_records` has no `updated_at`. No row insert, no `memory` schema, no vector extension
- [x] 3.2 Downgrade aborts when either table has a row; otherwise it drops only those two tables. Retarget the `0011` head pin at revision `0011_daily_close_outcome`. Reset helpers delete `business_events` and `source_coverage_records` before `operational_days`
- [x] 3.3 Add tenant-scoped insert-if-absent coverage, append-only event insert, and list-by-day reads on the operations repository. Product code never updates or deletes either row

## 4. Sale commit hook

- [x] 4.1 On successful `sale.commit@1`, after outcome and WorkItem sync and before idempotency completes, ensure one `sales` coverage row and insert one `sale_confirmed` event. A second sale reuses the coverage row. A typed phrase and `sale.pay.*@1` share `manual_capture`
- [x] 4.2 `ready_to_charge`, totalize, replay, confirmed read-back, and a closed-day refusal MUST NOT write coverage or an event. No new idempotency operation

## 5. Cash-count hook

- [x] 5.1 On a new CashCount insert, after outcome and WorkItem sync and before idempotency completes, ensure one `cash_count` coverage row and insert one `cash_count_recorded` event. Short and over stay on `facts.cash_status`. A later count reuses coverage and adds an event only for the new cash count id
- [x] 5.2 Equal-amount read-back and `closing.prepare@1` MUST NOT write coverage or an event. Balanced cash MUST NOT change sales coverage status

## 6. Close hook

- [x] 6.1 On successful `closing.confirm@1`, after the snapshot, the closed day, OutcomeRun completion, and the WorkItem link, ensure missing `sales` and `cash_count` coverage without changing an existing row, then insert one `daily_close_completed` event that references that OutcomeRun and ClosingSnapshot. Do not add a `daily_close` domain or copy coverage into OutcomeRun evidence
- [x] 6.2 Replay, already-closed read-back, clarify, and a stale token MUST NOT insert a second event. Do not enqueue `memory.event.created` or `source_coverage.updated`. Close copy stays unchanged

## 7. Initializer

- [x] 7.1 Extend the existing open-today command so an open day dated today gains `sales` coverage when it has a confirmed sale and `cash_count` coverage when it has a current CashCount. Skip closed days and older open days. Insert no business event and write no coverage audit. Do not add an HTTP route or grant `BYPASSRLS`
- [x] 7.2 A second run MUST NOT insert a duplicate. Alembic `0012` itself MUST insert nothing

## 8. Provenance and conservative claims

- [x] 8.1 Keep `source_type=manual_capture` on coverage and events. On `business_events` that value is the primary operational data source of the fact, not the writer, workflow, or route. `daily_close_completed` stays `manual_capture` and is proved by the ClosingSnapshot. No link from a business event to a coverage row. Do not register `memory.query_events`, a coverage tool, or a new UI component
- [x] 8.2 Leave day-summary and confirmed-close fallback text unchanged. Do not add assistant copy that claims every sale was captured, that no sale is missing, or that the day is 100% complete

## 9. Integrity and idempotency tests

- [x] 9.1 Cover first sale, second sale, typed phrase and payment action sharing one sales row, `ready_to_charge`, balanced cash leaving sales `observed`, short-count facts, equal-amount read-back, close referencing OutcomeRun and ClosingSnapshot, and close not creating a `daily_close` domain
- [x] 9.2 Cover replay, parent rollback, tenant isolation, pure reads and `OutcomeEngine.evaluate` writing nothing, no new audit or outbox type, no event backfill, initializer scope, and absence of embeddings, schema `memory`, and a Memoria timeline change

## 10. ADR-025

- [x] 10.1 Add `docs/adr/ADR-025-source-coverage-event-memory.md` with the closed decisions in design.md, including coverage with no `updated_at`, and `business_events.source_type` as the operational data source `manual_capture` for all three event types, with `daily_close_completed` proved by `closing_snapshot` and the ClosingSnapshot id. Do not edit ADR-015 through ADR-024
