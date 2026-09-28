# ADR-029: Pilot stage gate and perception instrumentation

- Status: Accepted
- Date: 2026-09-27

## Context

PRD v0.11 RF-075 requires registering the wedge stage gate and continuity decision in Build A. RF-096 requires anti-POS perception measurement. Build A already records Daily Close `OutcomeRun` completion, `WorkAbsorptionRecord`, partial `OutcomeCost`, source coverage with `only_lumo_registered_operations`, and WorkItems. None of that is, by itself, a reproducible gate verdict.

ADR-028 established OutcomeRun as the economic unit and honest partial cost. ADR-024 forbids cost on `outcome_runs`. Business Stream remains read-only (ADR-027). Merchant tenants are RLS-isolated (ADR-010).

## Decision

**Purpose.** Stage gate instrumentation answers whether Build A is producing enough **reliable evidence** to justify progressing the wedge (Build B entry is "MVP Build A supera el stage gate inicial del wedge" per PRD §18.2). It evaluates product thesis evidence, not ticket completion.

**Three evidence classes (never collapsed).** Product capability, pilot performance, merchant perception — unchanged.

**Determinism.** Policy `build_a_stage_gate@1` is versioned code/constants. Evaluation is pure given persisted inputs, business-date window, **`evidence_cutoff_at` as an explicit parameter** (evaluator does not call `now()`), and policy version. No LLM decides readiness.

**Temporal semantics.** `evidence_window_start` / `evidence_window_end` are inclusive `OperationalDay.business_date` boundaries (not derived from cutoff). `evidence_cutoff_at` is UTC and means evidence known no later than that instant.

**Status at cutoff.** Derive `status_at_cutoff` from `outcome_runs.created_at`, `ready_at`, and `completed_at` — not current `status` alone. Eligibility requires `created_at <= cutoff` (first sale creates run; implies `sale_count >= 1` by Build A rules). No new event store; no extra persistence for replay in this slice.

**Approved thresholds (@1).**

- ≥5 eligible outcomes per business; below → `insufficient_evidence` (not fail).
- Cohort: ≥3 businesses each with ≥5 eligible outcomes; **0–2 qualify → `insufficient_evidence`** for `cohort_merchant_count` (not fail).
- Business completion ≥90% when sample sufficient; cohort pooled completion ≥90% across qualifying businesses when ≥3 qualify; **<3 qualify → `insufficient_evidence`** for cohort completion. Per-business completion preserved in sub-results; no per-merchant 90% floor at cohort `@1`.
- Cohort perception: ≥70% delegation-positive / ≥60% `lumo_brings` among businesses with sufficient capture; <3 such businesses → `insufficient_evidence`.
- Ten jornadas → policy **@2** repeatability; non-blocking.

**Idempotency.** Natural key: scope, business/cohort identity, `policy_version`, window dates, `evidence_cutoff_at`.

**Overall status (closed):** `ready`, `not_ready`, `insufficient_evidence`.

**Criterion status (closed):** `pass`, `fail`, `insufficient_evidence`.

**Blocking (@1).** Business: sample size, completion rate, work absorption structural reduction, source coverage limitation on record, OutcomeCost rows present, delegation perception, proactive information delivery. Cohort additionally: `cohort_merchant_count`.

**Non-blocking.** Merchant confirmation exposure (diagnostic), internal intervention (`insufficient_evidence`), unresolved WorkItems (threshold OPEN), complete unit economics, retries, anti-POS classification incidence, wedge informational codes, repeatability, payment continuity (out of slice).

**Non-control.** Gate results do not change Daily Close, permissions, or feature flags.

## Consequences

Lumo can record a defensible Build A wedge continuity decision with auditable criteria and historical cutoff semantics. Policy `@2` may strengthen repeatability and per-business cohort completion. Flutter and merchant APIs stay unchanged.
