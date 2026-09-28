# ADR-028: Work absorption and outcome cost instrumentation

- Status: Accepted
- Date: 2026-09-27

## Context

PRD v0.11 RF-083, RF-084, and RF-085 require Build A to classify execution mode, persist `WorkAbsorptionRecord`, and record cost per OutcomeRun. Daily Close already has `daily_close_ready@1` OutcomeRun (ADR-024), WorkItems (ADR-023), CashCount, ClosingSnapshot, source coverage, and factual events. Business Stream is a pure read (ADR-027). ADR-024 forbids a cost summary on `operations.outcome_runs`.

## Decision

**Economic unit.** Instrumentation is keyed to OutcomeRun, not user, conversation, token, message, screen, or session.

**Execution mode.** Persist the closed PRD §9.12 enum (`manual_by_business` through `fully_automated`). Daily Close Build A writes only `fully_automated`, `prepared_by_lumo`, and `executed_with_confirmation`. Mode describes how a task was executed, not WorkItem or OutcomeRun status.

**Automation level.** Persist a closed rollup `manual`, `assisted`, or `automated` derived only from `current_execution_mode` (`manual_by_business` → manual; assisted/prepared/confirmation/internal review modes → assisted; fully automated/policy/reversible → automated). Not equal to execution mode. No percentage score. No LLM classification.

**Work absorption.** Persist `operations.work_absorption_records` with one row per `(business_id, outcome_run_id, task_type)` for six Daily Close administrative tasks. Baseline `daily_close_ready@1/work_absorption_baseline@1` is **approved**: two estimated minutes per eliminated human step (provisional pilot estimate, not measured time, not merchant ROI). Values are copied onto the row and stay stable when baseline versions change later.

**Intervention seconds.** Nullable integers on absorption and cost rows: NULL = unknown/not measured; 0 = measured zero; >0 = measured duration. Build A Daily Close persists NULL (no reliable active-time measurement). Do not use WorkItem elapsed time or estimated minutes.

**Evidence.** `evidence_ids` holds `{kind, id}` references only. No new event store.

**Writes.** Upserts run only inside existing OutcomeRun write transactions. Reads write nothing. `prepare_close` absorption is written at confirm because prepare stays a read.

**Immutability.** When OutcomeRun is `completed`, database `BEFORE INSERT` and `BEFORE UPDATE` on absorption and cost reject all changes. No post-complete instrumentation insert, including repair. Repair: OutcomeRun in non-completed state → instrumentation → `completed` in one transaction. No correction table in Build A.

**Cost storage.** One `operations.outcome_costs` row per OutcomeRun. Platform currency **USD** (approved). Model/token and infrastructure cost **unavailable** (NULL amounts). `estimated_total_cost_amount` NULL, `cost_completeness=partial`. Conversation LLM attribution deferred. No configured infra estimate.

**Surface.** No merchant API, admin dashboard, or Flutter change.

## Consequences

Lumo can answer internal pilot questions about absorbed Daily Close work and honest partial cost without changing merchant close behavior. E26 maps to six tasks with 2/2/2 execution modes and eight baseline minutes saved. Conversation LLM cost remains unattributed until a future provider contract exists.
