## Why

Lumo can complete sales and report today's totals, but it cannot answer the question the merchant actually asks at the end of the day: "how much cash should be in the till, and how much is really there?" PRD §7.9 and SRS RF-A-080 through RF-A-083 require Lumo to compute expected cash, request and persist the real count, and show the difference without correcting it (RB-A-010). This slice adds only that cash foundation. It is the prerequisite for Daily Close and it does not confirm a close.

## What Changes

- Persist `CashCount` in the existing `operations` schema: `operations.cash_counts`, one **current** row per `OperationalDay`, recounts appended as new rows that supersede the previous one (SRS RF-A-081, PRD v0.11 §`CashCount` `supersedes_cash_count_id`).
- Compute `expected_cash` in the backend as the Decimal sum of recorded `cash` payments of the day's confirmed sales. Card and transfer MUST NOT change it (RB-A-009). Build A has no opening float, expenses, withdrawals, deposits, or refunds; the authoritative docs define none, so none are introduced.
- Compute `cash_difference = counted_cash - expected_cash` server-side (SRS RF-A-082) and derive `cash_status` `not_counted` | `balanced` | `over` | `short`. Neither value is persisted.
- Register the Architecture §10.1 closing tools that this slice owns: write `closing.submit_cash_count@1` (input is only `amount`) and read `closing.prepare@1` (empty input). `closing.prepare@1` is a **read**: it computes the preparation state and writes nothing. `closing.confirm` and `closing.reopen` stay unregistered.
- Extend the scripted interpreter with two closed phrase sets: cash-count capture with a numeric slot (`tengo 120 en caja`, `hay 120 en caja`, `conté 120`, `caja 120`) and close-preparation requests (`preparar el cierre`, `preparar cierre`, `cuánto debería haber en caja`, `efectivo esperado`). `cerrar el día`, `cerrar caja`, and `confirmar cierre` MUST clarify without mutating.
- Register Generative UI `daily_close_preparation@1` and render it on the existing Inicio stream. PRD §10.5 `closing_ready_card` and `cash_difference_card` stay unregistered because this slice does not confirm a close.
- Alembic `0006_cash_count` (`down_revision = "0005_operational_day"`) creates `operations.cash_counts` with FORCE RLS, tenant-safe composite self-references, and one `DEFERRABLE INITIALLY DEFERRED` foreign key so a recount can retire the previous row before inserting the new one. ADR-017.
- Repair a stale baseline requirement: `conversational-sale-session` still says `sale.commit@1` MUST NOT create an `OperationalDay`, which the archived `build-a-operational-day-foundation` change already superseded. The requirement is corrected to say commit ensures and attaches the day but creates no `CashCount`, `WorkItem`, invoice, or Daily Close. Spec text only; no sale behavior changes.

**BREAKING** relative to the archived baseline: `operations.cash_counts` exists; `ToolRegistry` gains two `closing.*` tools; `GenerativeUIRegistry` gains `daily_close_preparation@1`; the "no cash-count table" rule in `persistence` and `sale-payment` is replaced. `OperationalDay.status` stays `open` only.

## Capabilities

### New Capabilities

- `cash-count-foundation`: `CashCount` entity, current-versus-superseded model, the write workflow and its transaction, `closing.submit_cash_count@1`, cash-count phrases, audit, outbox, idempotency, and tenant isolation.
- `daily-close-preparation`: the `expected_cash` formula, signed `cash_difference`, the `cash_status` enum, read tool `closing.prepare@1`, its non-mutating guarantee, and zero-sales / no-day behavior.
- `daily-close-preparation-ui`: versioned `daily_close_preparation@1` and its Flutter rendering, including the "falta contar efectivo" state.

### Modified Capabilities

- `persistence`: add `operations.cash_counts` and migration `0006_cash_count`; drop the rule that cash-count tables must not exist; extend integrity cleanup and orphan checks.
- `ai-native-contracts`: register `closing.submit_cash_count@1`, `closing.prepare@1`, `daily_close_preparation@1`, and policies `CLOSE-001` / `CLOSE-002`. `closing.confirm@1` and `closing.reopen@1` MUST stay unregistered and denied under `SEC-002`.
- `conversational-sale-runtime`: interpreter phrase sets, `AgentDecision.counted_amount`, orchestrator routing for `record_cash_count` and `close_preparation`, and message operation type `lumo.message.record_cash_count`.
- `mobile-shell`: renderer registers `daily_close_preparation` version `1`; Flutter MUST NOT compute expected cash, difference, or status. Hoy stays a placeholder.
- `operational-day-foundation`: a `CashCount` belongs to an `OperationalDay`; `status` remains `open`; neither counting cash nor requesting preparation creates a day.
- `conversational-sale-session`: repair the stale commit requirement so it matches the implemented baseline — commit ensures and attaches the `OperationalDay`, and creates no `CashCount`, `WorkItem`, invoice, or Daily Close.

## Non-goals

- `closing.confirm`, `closing.reopen`, `OperationalDay.status` `closed` / `in_progress` / `ready_to_close` / `failed`, `ClosingSnapshot`, close approval, manager override, tolerance thresholds.
- WorkItems, NextBestAction, OutcomeRuns, `daily_close_ready@1` gates, exception queues, source coverage.
- Cash denominations, opening float, expenses, withdrawals, deposits, refunds, voids, price overrides.
- Card / transfer / bank / terminal reconciliation, accounting posting, CFDI/SAT.
- Close history, export, charts, weekly or monthly reporting, the Hoy screen, the Design System "Preparar el cierre del día" action card.
- Inventory, purchasing, suppliers, replenishment, forecasting, CRM, loyalty.
- Vendor LLM, voice, camera, Redis, Kafka, vector DB, multi-agent, multi-branch, free-form NLU.

## Impact

- Backend: `domain/operations` gains `CashCount` and the difference/status rules; new repository methods on `OperationsRepository`; two application workflows (`RecordCashCount` write, `GetDailyClosePreparation` read); two tool registrations; two policies; interpreter phrases; `daily_close_preparation@1` composer.
- Persistence: one new table, one migration, one new audit action, one new outbox event, one new idempotency operation type. Cleanup helpers delete cash counts before their operational days.
- Mobile: one new renderer contract on Inicio. No navigation, tab, or theme change.
- Docs: ADR-017 for the cash-count and preparation decision. ADR-015 and ADR-016 stay unchanged.
