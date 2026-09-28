## Why

Build A already persists Daily Close `OutcomeRun` rows, `WorkAbsorptionRecord`, partial `OutcomeCost`, source coverage limitations, WorkItems, and factual events. That is **product capability evidence**, not a reproducible answer to whether the wedge is ready to progress toward Reliable Daily Close / Build B.

PRD v0.11 **RF-075** requires registering the wedge stage gate and continuity decision. **RF-096** requires measuring anti-POS perception during the pilot. Sections **4.8**, **18.1–18.2**, **32**, **36.4–36.5**, and scenario **E28** define what the gate must evaluate: outcome reliability, delegation/work absorbed, trust/coverage, economics signals, operator behavior, and merchant perception — not feature ticket completion.

This slice adds **internal pilot instrumentation** only: structured perception capture, a versioned deterministic gate policy, and immutable `StageGateAssessment` snapshots that explain pass, fail, or insufficient evidence per criterion. It does not change Daily Close, Business Stream, or merchant UX.

## What Changes

- Introduce capability **`pilot-stage-gate`**: versioned policy `build_a_stage_gate@1`, closed overall status (`ready`, `not_ready`, `insufficient_evidence`), closed criterion status (`pass`, `fail`, `insufficient_evidence`), evidence-quality semantics, reproducible evidence windows, deterministic aggregation over existing `OutcomeRun` / absorption / cost / WorkItem / source-coverage data, and persisted immutable assessments with structured criterion results and evidence references (not duplicated payloads).
- Introduce capability **`pilot-perception`**: versioned question set `anti_pos@1`, closed response codes, optional short note, deterministic anti-POS classification (`operator_perceived`, `mixed`, `pos_like`, `insufficient_evidence`), manual/internal capture path (no merchant survey UI).
- Minimal pilot membership: `pilot_program_enrollments` (per business, cohort code, window bounds) to define who is in scope without a generic experimentation platform.
- Expected migration **`0014_pilot_stage_gate_instrumentation`** (design only in this change; **not created yet**): enrollment, perception responses, stage gate assessments, RLS, immutability triggers, uniqueness for idempotent assessment creation.
- Internal evaluation entry point (domain service + repository tests + internal command). **No** merchant HTTP route, **no** Flutter, **no** Business Stream fields, **no** runtime feature gating.
- **ADR-029** (Proposed): deterministic stage gate, policy versioning, cohort evaluation boundary, perception contract.

## Capabilities

### New Capabilities

- `pilot-stage-gate`: Policy versioning, evidence window, eligibility rules for Daily Close outcomes, criterion evaluation, overall composition, assessment persistence, cohort rollup via trusted internal path.
- `pilot-perception`: Question set versioning, response persistence, deterministic classification, linkage to gate criteria.

### Modified Capabilities

- `persistence`: Revision `0014` tables, RLS, assessment immutability, enrollment uniqueness, internal cohort aggregation semantics documented.
- `tenant-isolation`: Explicit rule that cohort evaluation uses a trusted internal sequential path; merchant `lumo_app` sessions MUST NOT read cross-tenant cohort payloads.

### Unchanged (read-only evidence sources)

- `outcome-run-foundation`, `daily-close-outcome`, `work-absorption`, `outcome-cost`, `source-coverage`, `work-item-foundation`, `business-stream` — no merchant contract changes; gate **reads** only.

## Impact

- Backend: domain modules under `backend/app/domain/operations/` (or `pilot/`), repositories, internal assess command, tests. Head becomes `0014` when implemented.
- Docs: ADR-029 Proposed until implementation and manual acceptance.
- Mobile: no change.
- Product: policy `build_a_stage_gate@1` includes **approved** thresholds (5 eligible outcomes per business, 3 businesses at cohort, 90% completion, 70% delegation perception, 60% proactive information delivery); repeatability (10 jornadas) and WorkItem caps remain **policy @2** / OPEN (see design).

## Non-goals

- Build B, automatic unlock of features, admin/merchant dashboards, KPI charts, LLM gate verdict or sentiment scoring.
- Duplicate measurement systems, generic A/B platform, CRM/Slack mining, backfill of unsupported historical evidence.
- New Daily Close outcomes, new OutcomeRun statuses (`failed`/`blocked`), merchant-facing ROI or readiness badges.
- Complete unit economics, model/infra cost fabrication, internal ReviewTask instrumentation (gap documented honestly).
- Payment continuity / commercial intent capture (no persistence or survey in this slice).
- Archive, commit, or application implementation in this OpenSpec-only step.
