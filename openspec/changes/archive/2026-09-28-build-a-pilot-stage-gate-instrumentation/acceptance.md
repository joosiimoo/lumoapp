# Acceptance notes

Manual acceptance PASS. Tasks 32/32. ADR-029 Accepted (2026-09-27).

## A. Automated acceptance

- Backend suite: **355 passed**, 0 failed
- Targeted pilot stage gate tests: **27 passed**
- Migration `0013_work_absorption_outcome_cost` → `0014_pilot_stage_gate_instrumentation`: **passed**
- PostgreSQL enrollment exclusion constraint (`excl_pilot_program_enrollments_no_overlap`): **passed**
- Non-overlapping re-enrollment (same cohort, disjoint ranges): **passed**
- RLS (perception, business assessment, cohort assessment): **passed**
- Historical `status_at_cutoff` / explicit cutoff: **passed**
- Finalized assessment immutability: **passed**
- Assessment idempotency (same natural key): **passed**
- Perception `evidence_refs` (`pilot_perception_capture` + four `pilot_perception_response` ids): **passed**
- OpenSpec change + all validation: **passed** (42 items before new baseline capabilities)

## B. Manual window

- **cohort_code:** `build-a-manual-accept-2026` (shortfall cohort: `build-a-manual-accept-short-2026`)
- **evidence_window:** `2026-09-01` through `2026-09-14` (inclusive `OperationalDay.business_date`)
- **evidence_cutoff_at:** `2026-09-30T23:59:59Z`
- **later cutoff:** `2026-10-01T12:00:00Z`

Test-owned businesses only (deterministic UUIDs `aaaaaaaa-bbbb-4ccc-8ddd-000000000001`–`007`). Internal CLI: `enroll`, `record-perception`, `assess`. No direct SQL inserts into `stage_gate_assessments`.

## C. insufficient_evidence

Assessment `01a0e834-20d8-7793-aac3-7a73b289d830` — **3** eligible Daily Close outcomes.

- `sample_size_eligible_outcomes` = `insufficient_evidence`
- `outcome_completion_rate` = `insufficient_evidence`
- `overall_status` = `insufficient_evidence`

Lack of sample is **not** product failure (`not_ready`).

## D. not_ready

Assessment `01a0e834-22c1-7f10-81fd-634deda4d673` — **5** eligible, **4** completed at cutoff.

- `outcome_completion_rate` = **fail** (`4/5` = 80%, threshold 90%)
- `sample_size_eligible_outcomes` = **pass**
- `overall_status` = `not_ready`

## E. ready business

Assessment `01a0e834-24c6-7e7c-a793-6bc97ffa7f65` — `overall_status` = **ready**.

All blocking criteria **pass**. Non-blocking gaps (e.g. `internal_intervention_evidence`, `merchant_confirmation_exposure`, `anti_pos_classification`) = `insufficient_evidence` did **not** block ready.

## F. Perception evidence

Capture `01a0e834-1989-74c5-b4ff-e7dae1e367ca` (anti_pos@1, all four questions, none `unsure`).

Response ids: `01a0e834-1b0d-7445-b925-808c0c5cb716`, `01a0e834-1b15-7561-a58d-feb96a406af8`, `01a0e834-1b15-7a96-804e-e28216e4406a`, `01a0e834-1b16-7bd7-8f52-febb2e3bd647`.

`delegation_perception` and `proactive_information_delivery` `evidence_refs` include `pilot_perception_capture` and the four `pilot_perception_response` ids. No answer payload duplication; `note` not scored.

## G. ready cohort

Assessment `01a0e834-274c-7948-9a3f-d8a6fc69f3f3` — `overall_status` = **ready**.

- Pooled completion **32/35** (91.4%) ≥ 90% — **pass**
- `cohort_merchant_count` — **pass**
- `delegation_perception` — **pass** (≥70% among sufficient captures)
- `proactive_information_delivery` — **pass** (≥60%)
- Per-business sub-results preserved (e.g. cohort C **8/10** while pooled passes)

### included_business_ids semantics (accepted)

`included_business_ids` lists businesses **enrolled and in scope** for the cohort/window evaluation. It is **not** limited to businesses qualifying for `cohort_merchant_count`. Qualification is expressed via `cohort_merchant_count`, eligible counts, and per-business sub-results. No `qualifying_business_ids` in policy `@1`.

## H. cohort sample shortage

Cohort `build-a-manual-accept-short-2026`. Assessment `01a0e834-295e-7732-912e-9c9982e7d729`.

Two qualifying businesses (each ≥5 outcomes). `cohort_merchant_count` = `insufficient_evidence`; `overall_status` = `insufficient_evidence` (not `not_ready`).

## I. Idempotency / history

- Same scope/window/cutoff/policy: reused id `01a0e834-24c6-7e7c-a793-6bc97ffa7f65`
- Later cutoff: new assessment `01a0e834-2d24-7b2a-8ee2-e52b8ad4dfdc`; prior row unchanged (`finalized_at` set)

## J. Tenancy / surfaces — PASS

- Merchant cannot read another tenant's perception responses
- Merchant cannot read another tenant's business assessment
- Merchant cannot read cohort `StageGateAssessment`
- Trusted internal cohort `assess` path works
- No merchant HTTP stage-gate or perception routes
- No Flutter stage-gate / pilot survey UI
- Daily Close and Business Stream unchanged; no readiness badge or runtime feature gating

## K. Carrota

Accepted Carrota pilot history was **not** mutated. Acceptance used dedicated test-owned tenants only.

## Tooling

`backend/scripts/manual_accept_pilot_stage_gate.py` — manual acceptance runner with test-owned fixture purge/seed; not product runtime.
