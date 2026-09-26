## Context

Build A confirms a sale only inside `sale.commit@1`, which always stores `Payment.source = manual_capture`. A typed payment phrase and `sale.pay.cash@1`, `sale.pay.card@1`, or `sale.pay.transfer@1` are that same commit. `ready_to_charge` has no payment and no OperationalDay. A new `CashCount` stores `CashCount.source = manual_capture`. An equal amount is a read-back and inserts nothing. `closing.confirm@1` inserts one `ClosingSnapshot`, closes the day, completes `daily_close_ready@1`, and enqueues `closing.confirmed`. `closing.prepare@1`, the day summary, export, Next Best Action, and `OutcomeEngine.evaluate` do not write.

`operations` already holds days, cash counts, snapshots, work items, and outcome runs. Schema `memory` does not exist. Migration `0011` inserts nothing and the head pin in `test_daily_close_outcome_migration` treats `operations.source_coverage` and `operations.event_memory` as names that stay absent. Architecture §11.2 names `source_coverage_records` and `business_events`. Architecture §12 also describes a richer `MemoryItem` (confidence, actor, validity). That richer model is not this slice.

The Memoria tab is `MemoriaPage`, a placeholder whose body says factual memory will be enabled when confirmed events exist. PRD §7.12 lists a wider fact set (lines, price changes, work items, exports). This slice keeps three event types. PRD §7.1 names `manual_capture` as the initial source; no onboarding source registry exists in code, and this slice does not add one.

ADR-025 records these decisions at implementation. ADR-015 through ADR-024 are not edited.

## Goals / Non-Goals

**Goals:**

- A durable, tenant-scoped statement of what Lumo has observed for one OperationalDay, and the limitation on that statement.
- A curated append-only record of three confirmed business facts, written in the parent transaction, unique on the source fact.
- A hard separation from audit, outbox, ClosingSnapshot, and OutcomeRun.

**Non-Goals:**

- The proposal's non-goals. In particular: no completeness percentage, no `declared_complete`, no Memoria UI, no public memory API, no new audit or outbox taxonomy, no embeddings, no `memory` schema, and no second agent.

## Decisions

### 1. Table `operations.source_coverage_records`

Architecture §11.2 names this table. `operations.source_coverage` stays unused so the `0011` absence check for that shorter name can remain. No `memory` schema: coverage is an operational fact, and Architecture §11.1 allows a table convention instead of a physical `memory` schema. The implemented product schema for this kind of fact is `operations`.

Columns, all NOT NULL:

- `id` UUID primary key, UUIDv7
- `business_id` UUID
- `operational_day_id` UUID
- `domain` VARCHAR
- `source_type` VARCHAR
- `status` VARCHAR
- `limitation_code` VARCHAR
- `created_at` TIMESTAMPTZ

Those eight columns are the whole row. There is no `updated_at`. Build A coverage is an immutable statement that a source and domain were observed at least once for an OperationalDay: the only status is `observed`, the write is insert-if-absent, and `lumo_app` has no `UPDATE`. A second timestamp would have nothing to record. Do not replace `updated_at` with `last_observed_at`, `observation_count`, freshness, `evidence`, health, or another timestamp. A later slice may add source-health semantics if an external source exists. No actor, period, or prose column. The OperationalDay is the period.

Composite foreign key `fk_source_coverage_records_operational_day` on `(operational_day_id, business_id)` references `operations.operational_days (id, business_id)`. Unique `uq_source_coverage_records_identity` on `(business_id, operational_day_id, domain, source_type)`. Index `ix_source_coverage_records_business_id` on `business_id`.

### 2. Domains are `sales` and `cash_count`

Checks allow only those two. `daily_close` is not a domain. Close confirms facts already observed; it does not observe a new source. Cash count is its own domain because `CashCount` is a merchant declaration of physical cash, not proof about which sales exist.

Not included: inventory, purchasing, suppliers, bank, ecommerce, accounting, tax, CRM.

### 3. Source type is `manual_capture` only

The check allows only `manual_capture`. That is `PaymentSource` and `CashCountSource` today, and it is the PRD §7.1 / v0.11 MVP source name. A typed phrase and a payment `UiAction` both flow through `sale.commit@1` and both persist `manual_capture`, so they are one source. This slice does not add `lumo_conversation`, `merchant_declared`, `lumo_workflow`, `lumo_device_sync`, voucher, terminal, bank, or ecommerce.

### 4. Status is `observed` only

The check allows only `observed`. Build A has no merchant action that declares a source complete, so `declared_complete` is not a status. A second sale, a later cash count, balanced cash, short, over, a completed OutcomeRun, zero open WorkItems, and a successful close MUST NOT change `status`. A reuse MUST NOT update the row. `created_at` stays the insert time. `lumo_app` is not granted `UPDATE`.

### 5. Identity

One row per business, OperationalDay, domain, and source type. The first confirming sale inserts `sales` + `manual_capture`. A later confirming sale for that day inserts nothing. The first new CashCount inserts `cash_count` + `manual_capture`. A later new CashCount for that day inserts nothing. A missing row at close is inserted then, still `observed`, which repairs a skipped initializer without a read.

### 6. Limitation code

Column `limitation_code` is `only_lumo_registered_operations` and nothing else. It is not merchant prose. Server-side copy, if a later slice renders it, interprets the code. Every sales and cash-count row carries it. Meaning: only operations registered in Lumo are represented. Lumo has no POS, bank, inventory, or commerce feed that would prove otherwise.

### 7. Recorded Operations Completeness

Not a table and not a percentage. A pure function over the day's coverage rows returns:

- `basis = recorded_operations`
- `domains`: the distinct domains present, sorted
- `sources`: the distinct source types present, sorted
- `limitation_code = only_lumo_registered_operations`
- `merchant_source_declaration = null`

`sale_count`, a successful close, balanced cash, a completed OutcomeRun, and zero open WorkItems MUST NOT add a completeness flag, a percent, or a non-null merchant declaration. No code path infers a missing transaction. An empty day still returns the limitation and a null declaration.

### 8. Coverage write hooks

Same transaction as the parent, after the parent fact and the existing OutcomeRun / WorkItem sync, before parent idempotency completes:

- successful `sale.commit@1` ensures `sales`
- a new CashCount insert ensures `cash_count`
- successful `closing.confirm@1` ensures `sales` and `cash_count` when the close's own facts include them, and still does not create another domain or change status

No write from Next Best Action GET, `operational_day.next_best_action@1`, summary, export, `closing.prepare@1`, `OutcomeEngine.evaluate`, totalize, `ready_to_charge`, clarify, stale token, closed-day refusal, idempotent replay, confirmed-sale read-back, equal-amount cash read-back, or already-closed read-back.

### 9. Coverage initialization

Migration `0012` inserts nothing. The existing deploy initializer, for each business's open OperationalDay dated today only, ensures `sales` when that day has a confirmed sale and `cash_count` when it has a current CashCount. It skips closed days and older open days. It does not insert business events, does not audit, is not an HTTP route, and does not grant `BYPASSRLS`. A second run inserts nothing.

### 10. No coverage API

No merchant route, no dashboard, and no coverage tool. Tests read the repository. The recorded-operations function is in-process only.

### 11. Table `operations.business_events`

This is the Architecture §10.2 / §11.2 confirmed-fact write, not `memory.memory_items` and not `operations.event_memory`. `event_memory` stays an absent name.

Columns:

- `id` UUID primary key, UUIDv7
- `business_id` UUID NOT NULL
- `operational_day_id` UUID NOT NULL
- `event_type` VARCHAR NOT NULL
- `occurred_at` TIMESTAMPTZ NOT NULL
- `source_type` VARCHAR NOT NULL
- `source_entity_type` VARCHAR NOT NULL
- `source_entity_id` UUID NOT NULL
- `facts` JSONB NOT NULL, object
- `created_at` TIMESTAMPTZ NOT NULL

No `updated_at`, `outcome_run_id` column, embedding, vector, title, narrative, summary, importance, sentiment, confidence, expiry, or editable text. `operational_day_id` is required because every Build A event in this set belongs to a day. A nullable day is not justified.

Foreign key `fk_business_events_operational_day` on `(operational_day_id, business_id)` references `operations.operational_days (id, business_id)`. No polymorphic foreign keys to sales, cash counts, snapshots, or outcome runs: the proving id is `source_entity_id`, and the extra nullable columns would be null on every other event type. Same-transaction writes plus uniqueness are the integrity for those ids.

Unique `uq_business_events_source` on `(business_id, event_type, source_entity_type, source_entity_id)`. Index `ix_business_events_business_day` on `(business_id, operational_day_id)`.

`source_type` is the primary operational data source underlying the confirmed business fact. It is not the application component that executed the write, the workflow that produced the event, or the API or tool route that handled the request. The check allows only `manual_capture`. This slice does not add `lumo_workflow`, `merchant_declared`, `conversation`, `system`, or any other event source type, and it does not add a workflow-origin field.

- `sale_confirmed` is `manual_capture` because its confirmed `Payment` is `manual_capture`.
- `cash_count_recorded` is `manual_capture` because the merchant `CashCount` is `manual_capture`.
- `daily_close_completed` is `manual_capture` because the Build A close commits operational facts whose implemented source coverage is `manual_capture`. The proving entity remains `source_entity_type=closing_snapshot` and `source_entity_id` equal to that `ClosingSnapshot.id`. The close tool is not a source type.

There is no foreign key to `source_coverage_records`. Provenance is `source_type` plus `source_entity_type` and `source_entity_id`.

A `BEFORE UPDATE` trigger `business_events_immutable` raises for every role. Product code does not delete. `DELETE` stays granted for the existing tenant reset.

### 12. Event types and facts

Checks allow only:

- `sale_confirmed` with `source_entity_type = sale_session`
- `cash_count_recorded` with `source_entity_type = cash_count`
- `daily_close_completed` with `source_entity_type = closing_snapshot`

`occurred_at` is the fact time: `confirmed_at`, `counted_at`, or `closed_at`. `created_at` is the insert time.

`facts` keys are exact. Money values are quantized decimal strings with two fraction digits and a `.` separator. No nested money object and no model prose.

`sale_confirmed`: `sale_session_id` (equals `source_entity_id`), `payment_id`, `payment_method` (`cash`, `card`, or `transfer`), `amount`, `currency`. No sale lines.

`cash_count_recorded`: `cash_count_id` (equals `source_entity_id`), `expected_cash`, `counted_cash`, `cash_difference`, `cash_status` (`balanced`, `short`, or `over`), `currency`. Short and over are this `cash_status`, not a separate event. A superseding count has a new id and therefore a new event. The previous event stays.

`daily_close_completed`: `outcome_run_id`, `closing_snapshot_id` (equals `source_entity_id`), `sale_count` (JSON integer), `gross_sales_total`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status` (`balanced`, `short`, or `over`), `currency`. No snapshot body, no payment mix, and no key that means all real-world sales were captured.

PostgreSQL checks reject extra keys by requiring `facts` minus the allowed keys to equal `{}`.

### 13. Event write hooks

Same transaction, after the parent fact exists, before parent idempotency completes. No new idempotency operation. Replay returns before the hook. A parent rollback removes the event.

- `sale.commit@1` inserts `sale_confirmed` after the payment, the day, and outcome/work sync
- a new CashCount inserts `cash_count_recorded` after the count and outcome/work sync
- `closing.confirm@1` inserts `daily_close_completed` after the snapshot, the closed day, the completed OutcomeRun, and the WorkItem link

The close event's `outcome_run_id` is that run, including a run inserted as `completed` in the same transaction. `closing_snapshot_id` is the snapshot just inserted.

### 14. No event backfill

`0012` inserts no events. The initializer inserts no events, including for open today. Confirmed facts from before the hook exist in their source tables. A closed day remains evidenced by its ClosingSnapshot. Event memory starts with the first hooked commit after deploy.

### 15. Repository read only

The operations repository lists one tenant's events for one `operational_day_id`, ordered by `occurred_at`, then `id`. It can load coverage rows for that day. No `memory.query_events` tool, no `/memory/search`, and no natural-language history.

### 16. Memoria UI stays a placeholder

`MemoriaPage` is unchanged. A navigation tab is not a timeline. Factual memory is a backend capability first. A later slice may define a timeline or conversational history. This slice does not.

### 17. OutcomeRun is not coverage

`daily_close_ready@1` completed means the Daily Close responsibility for operations represented in Lumo was completed. It does not mean every real-world sale was observed. Outcome evidence keeps its current keys. It does not gain a coverage id, a coverage summary, or a completeness percent.

### 18. Audit

No `source_coverage.*` and no `business_event.*` audit action. Parent mutations already audit `sale.commit@1`, `closing.submit_cash_count@1`, and `closing.confirm@1`. Event memory is the fact record. Coverage has no merchant declaration to audit. The initializer's coverage insert is silent.

### 19. Outbox

No `source_coverage.updated` and no `memory.event.created`. Existing `sale.confirmed`, `payment.recorded`, `cash_count.recorded`, and `closing.confirmed` stay. Event memory does not wait on outbox delivery. Deleting or retaining an outbox row does not delete a business event.

### 20. Idempotency

Hooks inherit `lumo.message.commit_sale`, `lumo.message.record_cash_count`, and `lumo.message.confirm_close`. Uniqueness is the database backstop. Read-backs do not reserve a key and do not write coverage or events.

### 21. RLS

Both tables require `business_id`, `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and policy `tenant_isolation` with `business_id::text = current_setting('app.current_business_id', true)`. `lumo_app` receives `SELECT`, `INSERT`, and `DELETE` only. `lumo_app` and `lumo_admin` stay `NOBYPASSRLS`.

### 22. Migration `0012_source_coverage_event_memory`

`down_revision` is `0011_daily_close_outcome`. Upgrade creates the two tables, checks, keys, index, RLS, grants, and the immutability trigger. It inserts nothing. It does not create schema `memory` or `workflow`, a vector extension, an embeddings table, a knowledge table, a key-value memory store, or recommendation tables.

Downgrade aborts when either table has a row. Otherwise it drops both tables and does not drop `outcome_runs`.

The `0011` test that upgrades to head and expects revision `0011` must target `0011_daily_close_outcome` explicitly once `0012` is head. At exactly revision `0011`, `source_coverage_records` and `business_events` are still absent.

Reset helpers delete `business_events` and `source_coverage_records` before `operational_days`. Existing order `work_items` before `outcome_runs` before `closing_snapshots` before `cash_counts` before `operational_days` stays.

### 23. Assistant claims

This slice changes no rendered sentence. Summary text stays `Hoy {date} · {n} ventas · …`. Close text stays `Cierre confirmado · …`. The contract forbids new or changed assistant text, fallback text, and tool output that says all of today's sales were captured, that no sale is missing, that 100% of the operation was registered, or that the day's operation is complete, unless a coverage status of `declared_complete` exists. Build A cannot produce that status.

Wording that stays available for a later slice: "Según las ventas registradas en Lumo…", "En las operaciones registradas hoy…", and "El cierre registrado en Lumo…".

### 24. ADR-025

Implementation adds `docs/adr/ADR-025-source-coverage-event-memory.md` with the decisions in this file: coverage is not completeness; only registered operations are represented; domains and `manual_capture`; status `observed`; coverage rows have no `updated_at`; event types and identity; `business_events.source_type` is the primary operational data source underlying the fact, which is `manual_capture` for `sale_confirmed`, `cash_count_recorded`, and `daily_close_completed`, and is not the writer, workflow, or route; `daily_close_completed` is proved by `closing_snapshot` and the ClosingSnapshot id; same-transaction writes; audit and outbox stay separate; no model prose; no embeddings or vector database; RLS; migration `0012` with no row insert; no new UI or API. It does not edit ADR-015 through ADR-024.

## Risks / Trade-offs

- [A deploy mid-day leaves earlier sales without a `sale_confirmed` event] → Accepted. Coverage for open today is initialized from current facts. Events are not reconstructed. Source rows and ClosingSnapshot remain the historical evidence.
- [A reader treats `OutcomeRun.status=completed` as full coverage] → No status above `observed` exists, and outcome evidence does not copy coverage. ADR-025 states the distinction.
- [Outbox `sale.confirmed` is mistaken for the memory row] → Different tables. Memory does not depend on outbox delivery, and this slice adds no outbox type.
- [`0011` tests pin head] → The implementation retargets that upgrade at revision `0011` before asserting later tables are absent.

## Migration Plan

1. Apply `0012` before the application revision that writes the new tables. Upgrade inserts nothing.
2. Deploy the application. New commits, new counts, and new closes write coverage and events in their existing transactions.
3. Run the existing open-today initializer once so today's already-open day gains coverage from facts it already has. It does not invent events.
4. Rollback of the application stops new writes. Downgrade of `0012` is allowed only while both tables are empty; otherwise it aborts and the rows remain.

## Open Questions

None. The decisions above are closed for implementation.
