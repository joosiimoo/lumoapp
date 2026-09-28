## Context

**Product authority:** PRD v0.11 only — RF-075, RF-096, §4.8 (wedge stage gate), §18.1–18.2 (Build A exit / Build B entry), §32 (pilot success hypotheses), §36.4–36.7 (pilot phases, duration, abandonment), E28, CAP-001–CAP-005, §31.10 (anti-POS metrics intent).

**Baseline architecture (accepted through ADR-028, migration `0013_work_absorption_outcome_cost`):**

- `operations.outcome_runs` — `daily_close_ready@1`, statuses `in_progress` | `ready` | `completed` only.
- `operations.work_absorption_records`, `operations.outcome_costs` — frozen on completion; intervention seconds NULL in Build A.
- Source coverage — `only_lumo_registered_operations`; completed close ≠ full real-world coverage.
- WorkItems — merchant decisions (`cash_count_required`, `cash_difference_review`, `close_confirmation_required`).
- No ReviewTask / `reviewed_by_lumo_operator` in Daily Close Build A.

**Illustrative only (not pilot-ready):** Carrota one completed close — six absorption rows, 6→2 steps, 8 estimated minutes, partial OutcomeCost. One close MUST NOT pass sample-size rules.

## Goals / Non-Goals

**Goals:**

- Deterministic, reproducible stage gate assessments for `business` and `cohort` scope.
- Distinguish capability vs performance vs perception evidence.
- Explicit insufficient evidence vs fail.
- Minimal perception capture for RF-096 / E28.
- Internal-only surface; no product runtime gating.

**Non-Goals:** Listed in proposal; especially dashboards, LLM verdicts, Build B, migrations in this step, payment-continuity capture.

## PRD mapping

| PRD | This slice |
|-----|------------|
| RF-075 Register wedge stage gate and continuity decision | `StageGateAssessment`, policy `build_a_stage_gate@1`, internal register command |
| RF-096 Anti-POS perception | `PilotPerceptionResponse`, `anti_pos@1`, blocking criteria `delegation_perception` and `proactive_information_delivery`; classification diagnostic |
| §4.8 Gate de continuidad | ≥5 eligible outcomes **per business**; ≥3 such businesses at cohort; effort reduction via absorption; perception thresholds |
| §18.2 Build B entry | Overall `ready` — product interprets; system does not unlock Build B |
| §32.3 90% closes; §32.4 70% delegation / 60% no admin nav | Encoded in `@1` completion and cohort perception thresholds |
| §36.5 Five jornadas initial gate | **5 eligible outcomes per business** in `@1` |
| §36.5 Ten jornadas per merchant | **Policy @2 / repeatability** — documented, **non-blocking** for initial gate |
| E28, CAP-001–005 | `anti_pos@1` questions; classification for diagnosis |

## Evidence model

**Classes (orthogonal to pass/fail):** product capability, pilot performance, merchant perception — unchanged.

**Evidence quality:** `measured`, `estimated`, `merchant_reported`, `derived`, `unavailable` — unchanged.

## Pilot unit and window

**Enrollment:** `operations.pilot_program_enrollments` — per `(business_id, cohort_code)` with `pilot_started_on`, optional `pilot_ended_on`.

**Assessment scopes:**

- **`business`:** One merchant; evaluates that merchant only.
- **`cohort`:** Rollup over enrolled businesses; stores per-business criterion summaries so one high-volume merchant cannot hide a merchant with no evidence.

**Window fields on `StageGateAssessment`:**

- `evidence_window_start`, `evidence_window_end` — inclusive **business-date** boundaries. Compare directly to `operations.operational_days.business_date`. Enrollment `pilot_started_on` / `pilot_ended_on` use the same business-date semantics. Do **not** derive window dates from `evidence_cutoff_at`.
- `evidence_cutoff_at` — **required explicit input** to evaluation (UTC `timestamptz`). Means **evidence known no later than this instant**. The pure evaluator MUST NOT call `now()`. Orchestration (CLI/service) supplies the cutoff. Persisted on the assessment.
- **Window vs cutoff:** window selects *which operational days*; cutoff selects *what was known by when*.

**Idempotency natural key:** `scope_type`, business or `cohort_code`, `policy_version`, `evidence_window_start`, `evidence_window_end`, `evidence_cutoff_at`. Same identity → reuse finalized assessment; later cutoff → new immutable row.

## Historical evaluation at `evidence_cutoff_at`

The evaluator MUST NOT use current `OutcomeRun.status` alone when `evidence_cutoff_at` is in the past. Use authoritative persisted instants on `operations.outcome_runs` (accepted in `outcome-run-foundation`):

| `status_at_cutoff` | Rule (deterministic) |
|--------------------|----------------------|
| `completed` | `completed_at IS NOT NULL` AND `completed_at <= evidence_cutoff_at` |
| `ready` | NOT completed at cutoff AND `ready_at IS NOT NULL` AND `ready_at <= evidence_cutoff_at` |
| `in_progress` | NOT completed or ready at cutoff AND `created_at <= evidence_cutoff_at` |
| (not eligible) | `created_at > evidence_cutoff_at` (run did not exist yet) |

`updated_at` is NOT a completion timestamp (evidence-only updates occur without status change). Do not infer from logs.

**Supplementary check (optional, not required for `@1`):** latest `audit.audit_events` row with `action=outcome_run.status_changed` and `created_at <= cutoff` may validate transitions; primary source remains `created_at`, `ready_at`, `completed_at`.

**Example:** row now `completed` with `completed_at` after cutoff → `status_at_cutoff` is `ready` or `in_progress` per table above → counts as **not completed** for completion rate.

**Eligibility at cutoff** (in addition to window + enrollment + `daily_close_ready@1`):

1. `operational_days.business_date` within `[evidence_window_start, evidence_window_end]`.
2. `outcome_runs.created_at <= evidence_cutoff_at` (first confirmed sale creates the row; no run without sales).
3. **Sale activity:** Build A inserts the OutcomeRun only on first `sale.commit@1` for that day, so `created_at <= cutoff` implies `sale_count >= 1` was already true at run creation and cannot drop below 1 via allowed mutations. Do not use post-cutoff evidence-only `sale_count` increases to *create* eligibility for a run born after cutoff.

No new event store. **No extra persistence** in this slice for temporal replay — existing `outcome_runs` timestamps plus `outcome_run.created` audit (`audit.audit_events.created_at`) are sufficient.

**Perception at cutoff:** latest sufficient `anti_pos@1` capture with `captured_at <= evidence_cutoff_at` (one merchant = one capture).

**Instrumentation rows** (absorption, cost): for criteria requiring completed outcomes, only runs with `status_at_cutoff=completed` and frozen rows that existed by cutoff (OutcomeCost/absorption written before or at completion in same transaction — use `completed_at <= cutoff`).

## Business vs cohort aggregation

**Business assessment** evaluates one `business_id`:

- ≥5 eligible outcomes in window (else `sample_size_eligible_outcomes` = `insufficient_evidence`).
- Completion rate ≥90% over that business's eligible attempts when sample sufficient.
- Work absorption structural pass on that business's completed eligible runs.
- Coverage and OutcomeCost on that business's completed eligible runs.
- Perception: that merchant's **latest sufficient** `anti_pos@1` capture before cutoff (`delegation_perception`, `proactive_information_delivery` as pass/fail/insufficient per business rules).

**Cohort assessment:**

- **`cohort_merchant_count` (blocking):** **PASS** when ≥3 enrolled businesses each have ≥5 eligible outcomes at cutoff. When **0, 1, or 2** businesses qualify → **`insufficient_evidence`** (sample shortage, not product failure). MUST NOT satisfy cohort size by summing five eligible days across merchants.
- **`outcome_completion_rate` (cohort, approved @1):** when ≥3 qualifying businesses, **pooled**  
  `sum(completed eligible at cutoff) / sum(all eligible at cutoff)`  
  across those businesses only. **≥90% → pass**, **<90% → fail**. Do **not** require each merchant ≥90% for cohort `@1`. Store **per-business** completion numerators/denominators in sub-results (e.g. A 10/10, B 10/10, C 8/10 → pooled 28/30 pass while C diagnostic shows 80%). Policy `@2` / repeatability may later add per-business cohort floors.
- When **<3** qualifying businesses → `outcome_completion_rate` = **`insufficient_evidence`** (not fail).
- **Other performance criteria** (absorption, coverage, cost): per qualifying business with sub-results preserved.
- **Perception (blocking):** denominators are **businesses with sufficient perception capture**, not response rows. One merchant = one latest sufficient capture. If **<3** such businesses → `delegation_perception` and `proactive_information_delivery` = `insufficient_evidence` (not fail). If ≥3: **delegation** PASS when ≥70% of those businesses are delegation-positive; **proactive information** PASS when ≥60% have `information_delivery=lumo_brings`. `unsure` / incomplete captures are excluded from denominator, not counted negative.

## Work absorption aggregation

Over **completed eligible** OutcomeRuns in scope, sum:

- `total_human_steps_before`, `total_human_steps_after`, `steps_eliminated`, `total_estimated_minutes_saved` (estimated).

**Blocking `work_absorption_steps_reduced` (@1):** PASS when:

- `total_human_steps_before > 0`
- `total_human_steps_after < total_human_steps_before`
- `steps_eliminated > 0`

No absorption-percentage fail threshold in `@1`.

**Diagnostic only:** `absorbed_step_ratio = steps_eliminated / total_human_steps_before` when denominator > 0; not labeled time-saved percentage; not blocking.

At **cohort** scope, each business that counts toward `cohort_merchant_count` MUST individually pass the absorption structural rule (per-business sub-result); one merchant failing absorption MUST NOT be masked by cohort totals.

## Merchant confirmation (diagnostic only)

**`merchant_confirmation_exposure`** — non-blocking. Reports confirmation task count, `executed_with_confirmation` distribution, remaining human steps. More confirmations are not greater readiness.

## Internal intervention

**`internal_intervention_evidence`** — `insufficient_evidence` (no ReviewTask source). **Non-blocking** for `@1`. No fabrication from retries/latency.

## Unresolved WorkItems

**`unresolved_work_items_at_cutoff`** — measured diagnostic; **threshold OPEN** for `@1` → criterion status `insufficient_evidence` or informational, **non-blocking**. Policy `@2` may promote to blocking with a numeric cap.

## Source coverage

**`source_coverage_limitation_on_record` (blocking):** PASS when limitation is explicitly on record (`only_lumo_registered_operations`) for required days/runs — NOT that all merchant operations were captured.

## Outcome cost

**`outcome_cost_rows_present` (blocking):** every completed eligible outcome has an `OutcomeCost` row; `partial` is acceptable.

**Complete unit economics** — diagnostic / `insufficient_evidence`, **non-blocking**. No `estimated_total_cost` requirement.

## Payment continuity

**Out of scope for `@1`.** No `payment_continuity_signal` criterion, field, survey, UI, or persistence. Document as future commercial/continuity evidence outside this slice.

## Repeatability (10 jornadas)

PRD §36.5 ten jornadas per merchant for repeatability → **`repeatability_sample_size` policy @2** / follow-up stage. Recorded in design as non-blocking; MUST NOT block initial gate.

## Anti-POS perception — RF-096 / E28

**Question set `anti_pos@1`:** unchanged four questions.

**Sufficient capture (per business):** latest capture (max `captured_at` ≤ `evidence_cutoff_at`) where all four `question_code`s are present and each `response_code != unsure`.

**Classification `anti_pos_classification@1`:** unchanged deterministic rules → `operator_perceived`, `mixed`, `pos_like`, `insufficient_evidence`. **Diagnostic only** — record `pos_like` incidence; not a blocking rule.

**Blocking perception criteria (@1):**

| Code | Business scope | Cohort scope |
|------|----------------|--------------|
| `delegation_perception` | PASS if sufficient capture AND `close_organizer` ∈ `lumo`,`shared` AND `workflow_ownership` ∈ `yes`,`partially`. Else `fail` if sufficient but not positive; `insufficient_evidence` if no sufficient capture | If <3 businesses with sufficient capture → `insufficient_evidence`. Else PASS if ≥70% of businesses **with sufficient capture** are delegation-positive |
| `proactive_information_delivery` | PASS if sufficient capture AND `information_delivery=lumo_brings`. `mixed` / `merchant_searches` not positive. Else fail/insufficient analogously | Same <3 rule; PASS if ≥60% of businesses with sufficient capture have `information_delivery=lumo_brings` |

## Stage gate policy `build_a_stage_gate@1` — approved thresholds

| Rule | Value |
|------|--------|
| Min eligible outcomes per business | **5** — below → `sample_size_eligible_outcomes` = **`insufficient_evidence`**, not fail |
| Min businesses at cohort (each with ≥5 eligible) | **3** — `cohort_merchant_count`; **0–2 qualify → `insufficient_evidence`** |
| Business completion (sample sufficient) | **90%** on that business's eligible runs at cutoff |
| Cohort completion (≥3 qualify) | **Pooled 90%** across qualifying businesses; per-business rates in sub-results |
| Cohort completion (<3 qualify) | **`insufficient_evidence`** |
| Cohort delegation perception | **≥70%** of businesses with sufficient capture |
| Cohort proactive information | **≥60%** of businesses with sufficient capture |
| Completion when sample insufficient | `outcome_completion_rate` = **`insufficient_evidence`**, not fail |

### Blocking criteria

**`business` scope:**

- `sample_size_eligible_outcomes`
- `outcome_completion_rate`
- `work_absorption_steps_reduced`
- `source_coverage_limitation_on_record`
- `outcome_cost_rows_present`
- `delegation_perception`
- `proactive_information_delivery`

**`cohort` scope additionally:**

- `cohort_merchant_count`

### Non-blocking / diagnostic

- `merchant_confirmation_exposure`
- `internal_intervention_evidence`
- `unresolved_work_items_at_cutoff` (threshold OPEN → non-blocking insufficient/informational)
- `outcome_cost_complete` / full unit economics
- `retry_count` / retries
- `anti_pos_classification` incidence (`operator_perceived`, `mixed`, `pos_like`)
- Wedge informational codes (`wedge_*`)
- `repeatability_sample_size` (10 jornadas — policy @2)
- `absorbed_step_ratio` and related absorption diagnostics
- Payment continuity (future, out of slice)

### Overall composition

1. Any **blocking** criterion `fail` → `not_ready`.
2. Else any **blocking** criterion `insufficient_evidence` → `insufficient_evidence`.
3. Else → `ready`.

No numeric readiness score. No LLM verdict.

**Pure evaluator contract:** `evaluate(policy_version, scope, window, evidence_cutoff_at, evidence_snapshot)` — cutoff is a parameter; orchestration supplies it.

## Domain model (proposed)

Unchanged entities: `PilotProgramEnrollment`, `PilotPerceptionResponse`, `StageGateAssessment`, embedded `StageGateCriterionResult` with per-business sub-results for cohort.

## Persistence (migration `0014` — design only)

Unchanged table sketch; `evidence_cutoff_at` stored from explicit evaluation input.

## Read / write lifecycle, tenancy, API

Unchanged: internal only; no Flutter; cohort via trusted per-tenant reads.

## Test plan (automated)

Add cases: 90% completion fail vs sample insufficient; cohort 3 merchants each ≥5 eligible; cohort perception <3 → insufficient; 70/60% cohort perception; per-business absorption at cohort; explicit cutoff reproducibility; merchant_confirmation non-blocking.

## Manual acceptance

Unchanged flow; CLI passes explicit `--evidence-cutoff-at` (or equivalent).

## Open product decisions (@1)

1. Numeric threshold for `unresolved_work_items_at_cutoff` when promoted in policy `@2`.

## Deferred policy @2

- `repeatability_sample_size` (10 jornadas per merchant).
- Per-business minimum completion rate at cohort scope (in addition to pooled rate).
- WorkItem open-count blocking threshold.
- Payment continuity / commercial intent capture.

## Risks

- Cross-tenant leak → internal-only cohort path + tests.
- Single Carrota close → per-business minimum 5 eligible outcomes.
