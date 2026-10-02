## Why

Carrota’s Build A wedge is implemented across archived OpenSpec changes (sales, corrections, Daily Close, Memoria, exports, transaction references, operational surfaces). Product authority remains `docs/PRD_Lumo_AI_Native_Managed_Business_Operations_v0.11.md`. What is missing is a single final pilot-readiness acceptance change that separates merchant-visible manual proof from one compact Cursor technical pass, with explicit blocker classification and exit criteria. Without that gate, pilot readiness stays ambiguous even when individual slices were accepted.

## What Changes

- Introduce a **final pilot-readiness acceptance checklist** for Carrota (review/acceptance artifact only — no product feature work).
- Split validation into:
  - **A. Manual functional acceptance** — sequential operator cases run by the user in the running app.
  - **B. Technical / automated acceptance** — one compact Cursor-run validation pass.
- Define evidence expectations per manual case (screenshot, export file, visible app state; logs only when UI cannot prove the behavior).
- Define finding classification: exactly one of `PILOT BLOCKER`, `NON-BLOCKING UX IMPROVEMENT`, or `POST-PILOT / BUILD B`.
- Define the **pilot-ready** exit rule: all manual blocker-level cases PASS, technical acceptance PASS, and no open `PILOT BLOCKER` remains.
- Non-blocking UX improvements do not prevent pilot readiness.
- Do not invent new features during acceptance; validate current implemented Build A behavior only.

## Capabilities

### New Capabilities

- `carrota-pilot-final-acceptance`: Acceptance contract for Carrota pilot readiness — manual vs technical split, evidence model, finding classification, and pilot-ready exit criteria. This is a checklist/review capability, not a runtime product surface.

### Modified Capabilities

- None. This change does not alter product requirements of existing Build A capabilities. Archived Carrota and Build A specs remain the behavioral source of truth for what operators should observe.

## Impact

- OpenSpec only: `proposal.md`, `design.md`, `tasks.md`, and one new acceptance capability spec under this change.
- No backend, mobile, migration, ADR, or onboarding edits.
- Parallel active change `openspec/changes/build-a-conversational-onboarding-and-minimum-configuration/` stays untouched (not in scope for this pilot gate; onboarding remains a known Build A gap per completion review).
- Evidence sources for expected behavior: current implemented app + archived Carrota changes (`sale-corrections`, `operational-surfaces-v2`, `memory-activity-feed-v2`, `transaction-references`, `pilot-ux-convergence`) and earlier Build A archives.
- ADR: **none** (acceptance procedure only; no new architectural decision).

## Non-goals

- Implementing, fixing, or redesigning product behavior.
- Archiving this change or any other change.
- Commit, push, or repo cleanup beyond documenting acceptance checks.
- Touching onboarding semantics or marking onboarding acceptance complete.
- Replacing PRD pilot success metrics (§32 qualitative/economic thresholds) with this checklist — this gate is **software pilot-readiness**, not merchant-outcome success.
- Inventing Build B capabilities, reopen, refunds, mixed payments, RF-009, inventory, analytics, or search-by-TRX.
- Duplicating automated tests as manual checks unless user-visible behavior matters.
