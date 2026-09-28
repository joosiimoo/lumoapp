## Purpose

Internal Build A wedge stage gate for MVP (`build_a_stage_gate@1`): deterministic, versioned policy over persisted Daily Close outcomes, work absorption, source coverage limitation, outcome cost, and structured anti-POS perception. No merchant API, no Flutter UI, no readiness score, no LLM verdict. Overall statuses: `ready`, `not_ready`, `insufficient_evidence`. Criterion statuses: `pass`, `fail`, `insufficient_evidence`.

## Requirements

### Requirement: Stage gate policy is versioned and deterministic
The system MUST evaluate Build A wedge stage gate using a versioned policy identifier `build_a_stage_gate@1`. Policy rules, criterion codes, threshold identifiers, and composition logic MUST be defined in code or static configuration loaded at evaluation time. Evaluation MUST be a pure function of persisted evidence, enrollment, perception responses, policy version, evidence window, and an explicit `evidence_cutoff_at` parameter. The pure evaluator MUST NOT read the current clock or default `evidence_cutoff_at` internally. No LLM, model API, or runtime-generated threshold MAY decide overall readiness or criterion status.

#### Scenario: Same inputs yield the same verdict
- **WHEN** two evaluations run with the same policy version, window, cutoff, scope, and unchanged underlying rows
- **THEN** each criterion MUST receive the same `status`, `observed_value`, and `reason_code`, and overall status MUST match

#### Scenario: Policy version is stored on the assessment
- **WHEN** an assessment is finalized
- **THEN** `policy_version` MUST be `build_a_stage_gate@1`

### Requirement: Overall and criterion statuses use closed vocabularies
Overall stage gate status MUST be exactly one of `ready`, `not_ready`, and `insufficient_evidence`. Each criterion result MUST use exactly one of `pass`, `fail`, and `insufficient_evidence`. The system MUST NOT persist a numeric readiness score, percentage ready, or LLM prose verdict.

#### Scenario: Insufficient evidence is distinct from fail
- **WHEN** eligible OutcomeRun count is below the configured minimum sample for `sample_size_eligible_outcomes`
- **THEN** that criterion MUST be `insufficient_evidence` and MUST NOT be `fail` solely because count is low

#### Scenario: Fail requires a violated rule with evidence
- **WHEN** a configured blocking threshold is set and observed value violates it with measured or derived quality
- **THEN** the criterion MUST be `fail` and MUST include `threshold_rule` and `observed_value`

### Requirement: Evidence quality is explicit per observation
Each numeric or categorical observation in a criterion result MUST declare `evidence_quality` as one of `measured`, `estimated`, `merchant_reported`, `derived`, or `unavailable`. `estimated_minutes_saved` and baseline-derived step counts MUST be `estimated`. `OutcomeRun.status` MUST be `measured`. Perception `response_code` MUST be `merchant_reported`. NULL `business_intervention_seconds` MUST be treated as `unavailable`, not measured zero.

#### Scenario: Estimated minutes are not measured time
- **WHEN** work absorption totals include `estimated_minutes_saved`
- **THEN** the observation MUST use `evidence_quality=estimated`

#### Scenario: NULL intervention is unavailable
- **WHEN** aggregation reads `business_intervention_seconds` IS NULL on all absorption rows
- **THEN** any criterion requiring measured intervention duration MUST be `insufficient_evidence`

### Requirement: Evidence window uses business dates and cutoff uses UTC instant
`evidence_window_start` and `evidence_window_end` MUST be inclusive boundaries compared directly to `operations.operational_days.business_date`. Enrollment start and end MUST use the same business-date semantics. Window dates MUST NOT be derived from `evidence_cutoff_at`. `evidence_cutoff_at` MUST be an explicit UTC timestamptz evaluator input meaning evidence known no later than that instant. The pure evaluator MUST NOT default cutoff from the current clock.

#### Scenario: Window and cutoff are independent
- **WHEN** an operational day is inside the evidence window but its OutcomeRun `completed_at` is after `evidence_cutoff_at`
- **THEN** that day MAY be an eligible attempt while the run MUST NOT count as completed at cutoff

### Requirement: OutcomeRun status at cutoff uses persisted lifecycle timestamps
For each OutcomeRun, `status_at_cutoff` MUST be derived only from `created_at`, `ready_at`, and `completed_at` on `operations.outcome_runs` plus `evidence_cutoff_at`. The evaluator MUST NOT use current `status` alone. Rules: `completed` when `completed_at IS NOT NULL` AND `completed_at <= evidence_cutoff_at`; else `ready` when `ready_at IS NOT NULL` AND `ready_at <= evidence_cutoff_at`; else `in_progress` when `created_at <= evidence_cutoff_at`; else the run MUST NOT be eligible. `updated_at` MUST NOT be used as completion time. The system MUST NOT invent `failed`, `blocked`, or `cancelled`.

#### Scenario: Late completion is incomplete at cutoff
- **WHEN** an OutcomeRun row currently has `status=completed` but `completed_at` is after `evidence_cutoff_at`
- **THEN** `status_at_cutoff` MUST be `ready` or `in_progress` per timestamps and MUST NOT count as completed for completion rate

### Requirement: Eligibility at cutoff uses run creation not post-cutoff facts
An eligible attempt at cutoff MUST satisfy window and enrollment on `business_date`, `outcome_runs.created_at <= evidence_cutoff_at`, and Build A's rule that OutcomeRun creation follows first confirmed sale so eligibility implies `sale_count >= 1` by cutoff without using evidence-only updates after cutoff to establish first eligibility.

#### Scenario: Run born after cutoff is not eligible
- **WHEN** the first confirmed sale for an in-window day occurs after `evidence_cutoff_at`
- **THEN** that OutcomeRun MUST NOT count as an eligible attempt for that assessment

### Requirement: Evidence window is reproducible
Every `StageGateAssessment` MUST store `evidence_window_start`, `evidence_window_end`, `evidence_cutoff_at`, `scope_type`, `build_identifier` `mvp_build_a`, and `included_outcome_run_refs` for OutcomeRuns counted at cutoff. Re-evaluation with the same scope, window, policy version, and cutoff MUST reuse the same finalized assessment.

#### Scenario: Cutoff excludes late completion
- **WHEN** `status_at_cutoff` is not `completed` because `completed_at` is null or after cutoff
- **THEN** that run MUST count in the eligible denominator and MUST NOT count in the completed numerator

### Requirement: Eligible Daily Close attempts use existing OutcomeRun semantics
An eligible attempt MUST be a `daily_close_ready` version `1` OutcomeRun whose operational day falls in the evidence window, enrollment is active on that day, and outcome evidence shows `sale_count >= 1` at cutoff. A completed attempt MUST have `status=completed`. An incomplete attempt MUST have `status=in_progress` or `status=ready`. The system MUST NOT invent `failed`, `blocked`, or `cancelled` OutcomeRun statuses for gate purposes. Days without sales MUST NOT count as eligible attempts.

#### Scenario: Ready but unclosed counts as incomplete
- **WHEN** an eligible run has `status=ready` at cutoff
- **THEN** it MUST count toward eligible attempts and MUST NOT count as completed

#### Scenario: No sales means no attempt
- **WHEN** no operational day in the window has a confirmed sale
- **THEN** eligible attempt count MUST be zero and sample-size criterion MUST be `insufficient_evidence`

### Requirement: Stage gate reads existing instrumentation without duplication
Criteria MUST aggregate from `operations.outcome_runs`, `operations.work_absorption_records`, `operations.outcome_costs`, `operations.work_items`, and `operations.source_coverage_records` by reference. Assessment storage MUST NOT copy full outcome evidence, absorption payloads, or snapshot totals. `evidence_refs` MUST use `{kind, id}` only.

#### Scenario: Completion uses OutcomeRun status only
- **WHEN** computing completion rate
- **THEN** numerators and denominators MUST use OutcomeRun `status` at cutoff and MUST NOT infer failure from missing ClosingSnapshot alone

### Requirement: Work absorption aggregates are derived honestly
For completed eligible runs in scope, the evaluator MUST sum `human_steps_before`, `human_steps_after`, and `estimated_minutes_saved` from frozen absorption rows. `steps_eliminated` MUST equal the sum over runs of `(human_steps_before - human_steps_after)`. Blocking `work_absorption_steps_reduced` MUST be `pass` only when `total_human_steps_before > 0`, `total_human_steps_after < total_human_steps_before`, and `steps_eliminated > 0` on those completed eligible runs; otherwise `fail` when sample exists, or `insufficient_evidence` when no completed eligible runs contribute. Diagnostic `absorbed_step_ratio` MUST equal `steps_eliminated / total_human_steps_before` when denominator greater than zero and MUST NOT be labeled as time saved or used as a blocking threshold in policy `@1`.

#### Scenario: Carrota-scale single close is not sufficient sample
- **WHEN** a business-scope assessment has fewer than five eligible OutcomeRuns in the window at cutoff
- **THEN** `sample_size_eligible_outcomes` MUST be `insufficient_evidence` and MUST NOT be `fail`

#### Scenario: Work absorption blocks on structural reduction
- **WHEN** completed eligible runs in scope sum to `total_human_steps_before > 0`, `total_human_steps_after < total_human_steps_before`, and `steps_eliminated > 0`
- **THEN** `work_absorption_steps_reduced` MUST be `pass`

#### Scenario: Absorbed step ratio is diagnostic only
- **WHEN** `absorbed_step_ratio` is computed as `steps_eliminated / total_human_steps_before`
- **THEN** it MUST be stored only on diagnostic criterion results and MUST NOT by itself cause `not_ready`

### Requirement: Source coverage limitation is preserved
Criteria MUST NOT treat `OutcomeRun.status=completed` as full real-world coverage. Trust criteria MUST treat `limitation_code=only_lumo_registered_operations` as the honest boundary. Passing coverage criteria MUST mean limitation rows exist where required, not that all merchant activity was captured.

#### Scenario: Completed close with observed sales coverage
- **WHEN** a completed eligible run's day has `source_coverage_records` with `limitation_code=only_lumo_registered_operations`
- **THEN** `source_coverage_limitation_on_record` MAY be `pass` with measured refs

### Requirement: Outcome cost partial completeness is expected in Build A
For each completed eligible run, `outcome_cost_rows_present` MUST be `pass` when an `OutcomeCost` row exists. Criteria requiring `cost_completeness=complete` or non-null `estimated_total_cost_amount` MUST be `insufficient_evidence` in Build A, not automatic `fail`.

#### Scenario: Partial cost is honest pass for instrumentation
- **WHEN** OutcomeCost has `cost_completeness=partial` and NULL model and infrastructure amounts
- **THEN** `outcome_cost_rows_present` MUST be `pass` and complete-cost criteria MUST be `insufficient_evidence`

### Requirement: Internal intervention is not fabricated
Criteria for internal Lumo operator intervention MUST NOT infer effort from logs, latency, retries, or WorkItem duration. When no `reviewed_by_lumo_operator` absorption rows and NULL `internal_intervention_seconds` exist, `internal_intervention_evidence` MUST be `insufficient_evidence` with reason `no_review_task_instrumentation`.

#### Scenario: Retries do not imply support minutes
- **WHEN** `retry_count` is greater than zero and intervention seconds are NULL
- **THEN** internal intervention criteria MUST remain `insufficient_evidence`

### Requirement: Sample size uses per-business minimum five eligible outcomes
Policy `build_a_stage_gate@1` MUST require at least five eligible Daily Close OutcomeRuns per business for `sample_size_eligible_outcomes` to be `pass` on business scope. When count is below five, the criterion MUST be `insufficient_evidence` and MUST NOT be `fail`. Cohort scope MUST NOT treat five eligible days summed across merchants as satisfying per-business sample; each business MUST be evaluated against five individually for cohort membership in `cohort_merchant_count`.

#### Scenario: Four eligible outcomes is insufficient not fail
- **WHEN** a business has exactly four eligible OutcomeRuns in window at cutoff
- **THEN** `sample_size_eligible_outcomes` MUST be `insufficient_evidence`

### Requirement: Cohort merchant count requires three businesses with sufficient evidence
On cohort scope, `cohort_merchant_count` MUST be `pass` only when at least three enrolled businesses each have at least five eligible OutcomeRuns in the window at cutoff. When zero, one, or two businesses meet that bar, the criterion MUST be `insufficient_evidence` and MUST NOT be `fail`. The cohort MUST NOT pass by aggregating five eligible days across merchants.

#### Scenario: Two merchants with five eligible each is insufficient evidence
- **WHEN** exactly two businesses each have five eligible OutcomeRuns at cutoff
- **THEN** `cohort_merchant_count` MUST be `insufficient_evidence` and MUST NOT be `fail`

### Requirement: Outcome completion rate uses ninety percent when sample is sufficient
On business scope, when `sample_size_eligible_outcomes` is `pass`, `outcome_completion_rate` MUST equal OutcomeRuns with `status_at_cutoff=completed` divided by all eligible OutcomeRuns at cutoff. It MUST be `pass` when the rate is at least `0.90` and `fail` when below. When business sample size is not sufficient, `outcome_completion_rate` MUST be `insufficient_evidence` and MUST NOT be `fail`. On cohort scope, when fewer than three businesses each have at least five eligible outcomes at cutoff, `outcome_completion_rate` MUST be `insufficient_evidence`. When at least three qualify, the cohort rate MUST be the pooled ratio of sum(completed eligible at cutoff) over sum(all eligible at cutoff) across those businesses only, MUST be `pass` at or above `0.90` and `fail` below, and MUST NOT require each business individually to reach `0.90` for policy `@1`. Per-business completion numerators and denominators MUST be stored in cohort sub-results.

#### Scenario: Eighty nine percent completion fails when sample sufficient
- **WHEN** a business has five eligible runs and four have `status_at_cutoff=completed`
- **THEN** `outcome_completion_rate` MUST be `fail`

#### Scenario: Pooled cohort pass with weak single merchant visible
- **WHEN** cohort qualifying businesses A and B each have ten of ten completed at cutoff and business C has eight of ten completed at cutoff
- **THEN** pooled `outcome_completion_rate` MUST be `pass` at twenty-eight of thirty and sub-results MUST show business C at eighty percent

### Requirement: Delegation perception is a blocking criterion
`delegation_perception` MUST be blocking for `build_a_stage_gate@1`. A business with sufficient `anti_pos@1` capture MUST be delegation-positive when `close_organizer` is `lumo` or `shared` and `workflow_ownership` is `yes` or `partially`. On business scope, sufficient capture with a non-positive combination MUST be `fail`; missing sufficient capture MUST be `insufficient_evidence`. On cohort scope, when fewer than three businesses have sufficient perception capture, the criterion MUST be `insufficient_evidence`. When at least three do, the criterion MUST be `pass` when at least seventy percent of businesses with sufficient capture are delegation-positive, else `fail`. Unsure or incomplete captures MUST NOT enter the denominator and MUST NOT count as negative.

#### Scenario: Cohort perception below three businesses is insufficient
- **WHEN** cohort scope has only two businesses with sufficient perception capture
- **THEN** `delegation_perception` MUST be `insufficient_evidence`

### Requirement: Proactive information delivery is a blocking criterion
`proactive_information_delivery` MUST be blocking for `build_a_stage_gate@1`. A business with sufficient capture MUST be positive when `information_delivery=lumo_brings`. `mixed` and `merchant_searches` MUST NOT count as positive. On cohort scope, the same fewer-than-three-business rule MUST yield `insufficient_evidence`. When at least three businesses have sufficient capture, the criterion MUST be `pass` when at least sixty percent of those businesses are positive, else `fail`.

#### Scenario: Merchant searches is not positive
- **WHEN** sufficient capture has `information_delivery=merchant_searches`
- **THEN** business-scope `proactive_information_delivery` MUST be `fail`

### Requirement: Merchant confirmation exposure is diagnostic only
`merchant_confirmation_exposure` MUST be evaluated and persisted as non-blocking diagnostic evidence including confirmation task counts, `executed_with_confirmation` distribution, and remaining human steps. It MUST NOT be in the blocking set and MUST NOT treat more confirmations as greater readiness.

#### Scenario: More confirmations do not change overall ready
- **WHEN** all blocking criteria pass and diagnostic confirmation exposure reports additional `executed_with_confirmation` tasks
- **THEN** overall status MUST remain `ready`

### Requirement: Unresolved WorkItems are non-blocking while threshold is open
`unresolved_work_items_at_cutoff` MUST record measured open WorkItem counts at cutoff. For policy `@1` with no approved numeric threshold, the criterion MUST be `insufficient_evidence` or informational and MUST NOT block `ready`. Future policy versions MAY promote it to blocking.

#### Scenario: Open WorkItems with open threshold do not block
- **WHEN** open WorkItems exist at cutoff and policy `@1` has no WorkItem cap threshold
- **THEN** `unresolved_work_items_at_cutoff` MUST NOT be `fail` and overall status MUST NOT be `not_ready` solely for that reason

### Requirement: Payment continuity is out of scope
Policy `build_a_stage_gate@1` MUST NOT include `payment_continuity_signal` or any payment-intent persistence. Commercial continuity evidence is deferred outside this slice.

#### Scenario: No payment continuity criterion
- **WHEN** policy `build_a_stage_gate@1` criterion codes are enumerated
- **THEN** `payment_continuity_signal` MUST NOT be present

### Requirement: Cohort assessment preserves per-business evidence
Cohort assessments MUST store per-business sub-results for blocking operational criteria so one high-volume merchant cannot hide another merchant with no evidence. Cohort perception MUST use one latest sufficient capture per business, not weight by number of response rows.

#### Scenario: Low-evidence merchant visible in cohort sub-results
- **WHEN** cohort scope includes one business with five eligible outcomes and another with zero eligible outcomes
- **THEN** the cohort assessment MUST include a per-business sub-result showing insufficient sample for the second business and `cohort_merchant_count` MUST NOT be `pass`

### Requirement: Overall composition is deterministic
Overall status MUST be computed by policy `build_a_stage_gate@1` composition: any blocking criterion `fail` → `not_ready`; else any blocking criterion `insufficient_evidence` → `insufficient_evidence`; else `ready`. Blocking criteria on business scope MUST be exactly `sample_size_eligible_outcomes`, `outcome_completion_rate`, `work_absorption_steps_reduced`, `source_coverage_limitation_on_record`, `outcome_cost_rows_present`, `delegation_perception`, and `proactive_information_delivery`. Cohort scope MUST additionally block on `cohort_merchant_count`. Non-blocking criteria include `merchant_confirmation_exposure`, `internal_intervention_evidence`, `unresolved_work_items_at_cutoff`, complete outcome cost, retries, anti-POS classification incidence, wedge informational codes, and repeatability sample size. The system MUST NOT average criteria into a score.

#### Scenario: Gap in internal intervention does not force not_ready
- **WHEN** all blocking criteria pass and `internal_intervention_evidence` is `insufficient_evidence`
- **THEN** overall status MUST be `ready`

### Requirement: StageGateAssessment is immutable and idempotent
The system MUST persist `StageGateAssessment` in `operations.stage_gate_assessments`. After `finalized_at` is set, UPDATE and DELETE MUST be rejected. Re-evaluation with the same natural key MUST return the existing row. Changed window or cutoff MUST create a new assessment row.

#### Scenario: New cutoff creates new history
- **WHEN** a second evaluation uses a later `evidence_cutoff_at`
- **THEN** a new assessment id MUST be inserted and the prior assessment MUST remain unchanged

### Requirement: Stage gate does not mutate product outcomes
Evaluation and assessment persistence MUST NOT insert, update, or delete OutcomeRun, WorkAbsorptionRecord, OutcomeCost, WorkItem, source coverage, ClosingSnapshot, or Business Stream projections.

#### Scenario: Assess is read-only on operations facts
- **WHEN** stage gate assessment runs
- **THEN** row counts for `outcome_runs` before and after MUST match

### Requirement: Stage gate is internal only
Merchant-scoped database roles MUST NOT read cohort assessments or other tenants' assessments. Stage gate results MUST NOT appear in Business Stream, merchant APIs, or Flutter surfaces. Assessment MUST NOT unlock Build B features or change Daily Close behavior.

#### Scenario: Merchant session cannot read cohort assessment
- **WHEN** session is scoped to business A and a cohort assessment includes business B
- **THEN** `SELECT` on that cohort assessment under `lumo_app` MUST return no row

### Requirement: Cohort included_business_ids lists enrolled in-scope businesses
On cohort-scoped assessments, `included_business_ids` MUST list businesses enrolled and in scope for the cohort evaluation and evidence window. It MUST NOT be restricted only to businesses that qualify for `cohort_merchant_count`. Sample qualification and merchant counts MUST be expressed through `cohort_merchant_count`, per-business sub-results, and eligible counts. The system MUST NOT introduce `qualifying_business_ids` in policy `@1`.

#### Scenario: Enrolled low-sample merchant remains listed
- **WHEN** a cohort assessment evaluates enrolled businesses where one merchant has fewer than five eligible outcomes
- **THEN** `included_business_ids` MAY include that merchant and per-business sub-results MUST show its insufficient sample without removing it from scope

