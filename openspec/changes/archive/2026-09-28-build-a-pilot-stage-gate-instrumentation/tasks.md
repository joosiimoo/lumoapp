## 1. Domain contracts / policy

- [x] 1.1 Add domain module for stage gate: closed enums, policy `build_a_stage_gate@1`, approved constants (5 eligible/business, 3 businesses/cohort, 90% completion, 70% delegation, 60% proactive info), blocking vs diagnostic criterion sets, composition function
- [x] 1.2 Add `status_at_cutoff` from `created_at` / `ready_at` / `completed_at`; eligibility at cutoff; explicit `evidence_cutoff_at` parameter (no `now()` in evaluator)
- [x] 1.3 Add pure aggregation helpers: absorption structural pass, diagnostic `absorbed_step_ratio`, WorkItem open counts (non-blocking), coverage, OutcomeCost, NULL-safe intervention
- [x] 1.4 Add perception helpers: sufficient `anti_pos@1` capture, delegation-positive and proactive-positive rules, `anti_pos_classification@1` (diagnostic only)
- [x] 1.5 Document repeatability `repeatability_sample_size` as policy @2 placeholder (non-blocking)

## 2. Persistence (migration 0014)

- [x] 2.1 Add Alembic `0014_pilot_stage_gate_instrumentation` per persistence delta
- [x] 2.2 Immutability for finalized assessments and append-only perception
- [x] 2.3 SQLAlchemy models and repositories
- [x] 2.4 Test cleanup/integrity helpers

## 3. Evidence aggregation service

- [x] 3.1 Business aggregator: one merchant, per-business rules, per-business perception pass/fail
- [x] 3.2 Cohort aggregator: per-business sub-results; cohort_merchant_count insufficient when 0–2 qualify; pooled completion when ≥3 qualify; perception denominators = businesses with sufficient capture (not row counts)
- [x] 3.3 `included_outcome_run_refs` and `evidence_refs` without payload duplication

## 4. Perception instrumentation

- [x] 4.1 Internal command to record `PilotPerceptionResponse` rows
- [x] 4.2 Wire sufficient-capture and blocking criteria; classification for diagnostics only

## 5. Stage Gate evaluation

- [x] 5.1 Evaluator accepts explicit `evidence_cutoff_at`; orchestration/CLI supplies timestamp
- [x] 5.2 Per-criterion results including diagnostic `merchant_confirmation_exposure`
- [x] 5.3 Immutable `StageGateAssessment` idempotent on scope + window + policy + cutoff
- [x] 5.4 Internal CLI with explicit cutoff flag for manual acceptance

## 6. Lifecycle / versioning

- [x] 6.1 Preserve policy, question set, and classification versions on assessments
- [x] 6.2 New cutoff → new assessment row

## 7. Tenancy / internal access

- [x] 7.1 RLS on enrollment and perception
- [x] 7.2 Merchant cannot read cohort assessments

## 8. Automated tests

- [x] 8.1 Approved thresholds: 5/business insufficient vs fail; cohort 0–2 merchants insufficient; pooled 90% cohort completion with per-business sub-results; historical cutoff status tests
- [x] 8.2 Cohort perception &lt;3 → insufficient; 70%/60% pass/fail
- [x] 8.3 Work absorption structural pass; ratio diagnostic non-blocking
- [x] 8.4 Merchant confirmation diagnostic non-blocking
- [x] 8.5 Unresolved WorkItems non-blocking; internal intervention non-blocking
- [x] 8.6 Explicit cutoff reproducibility and idempotency
- [x] 8.7 Per-business sub-results at cohort; no cross-merchant day summing for sample
- [x] 8.8 Partial OutcomeCost pass; no payment continuity criterion
- [x] 8.9 Assess read-only on product outcomes

## 9. Manual acceptance

- [x] 9.1 Multi-day test business + cohort of three merchants; explicit cutoff via CLI
- [x] 9.2 Inspect blocking vs diagnostic criteria in persisted assessment

## 10. ADR acceptance

- [x] 10.1 Set ADR-029 to Accepted after implementation and manual acceptance

## 11. Archive readiness

- [x] 11.1 `openspec validate build-a-pilot-stage-gate-instrumentation --strict` and `openspec validate --all --strict`
- [x] 11.2 Sync main specs on archive
