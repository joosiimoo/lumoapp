## ADDED Requirements

### Requirement: Split pilot acceptance into manual and technical tracks
Carrota pilot-readiness acceptance MUST be split into (A) manual functional acceptance performed by a human operator in the running app and (B) technical/automated acceptance performed later by Cursor in one compact validation pass. Manual cases MUST validate user-visible Build A behavior only. Technical cases MUST validate integrity, isolation, migrations, exports schema, OpenSpec coherence, onboarding non-touch, and repo hygiene. Acceptance MUST NOT invent new product features and MUST NOT require backend/DB inspection for a manual case unless the UI cannot prove the behavior.

#### Scenario: Manual track covers operator-visible journeys
- **WHEN** Carrota pilot-readiness acceptance is executed
- **THEN** the manual track MUST include the sequential functional cases defined by the active change design (app start, catalog unit/weight sales, non-catalog sale, price override, remove before/after totalize, cash/card/transfer payment, TRX sequence, Memoria void and void TRX linkage, Inicio state, Hoy totals, cash count, balanced and short/over close, optional close note, close confirmation and close TRX, Memoria timeline, CSV/XLSX export, restart persistence, closed-day mutation protection, and restart-safe Memoria actions)

#### Scenario: Technical track is one compact pass
- **WHEN** technical/automated acceptance is executed
- **THEN** Cursor MUST run one compact checklist covering backend tests, Flutter tests, flutter analyze, migration base→head, migration integrity, RLS/FORCE RLS, tenant isolation, idempotency, transaction-reference concurrency, Event Memory integrity, export schema, OpenSpec strict validation, untouched active onboarding change, clean unintended repo status, and no archived-change drift

#### Scenario: Automated coverage is not duplicated as manual busywork
- **WHEN** a behavior is already proven by automated tests and is not user-visible
- **THEN** acceptance MUST NOT require a redundant manual case for that behavior

### Requirement: Manual case evidence model
Every manual acceptance case MUST define preconditions, user action, expected visible result, PASS criteria, FAIL criteria, and expected evidence. Allowed evidence types are screenshot, exported file, visible app state, and log-only when necessary. Exported-file evidence is required for CSV and XLSX cases. Log-only evidence MUST be exceptional.

#### Scenario: Sale confirmation evidence is UI-visible
- **WHEN** a manual payment or close confirmation case is marked PASS
- **THEN** evidence MUST include visible app state and a screenshot of the confirmation surface

#### Scenario: Export evidence includes the file
- **WHEN** CSV or XLSX manual export cases are marked PASS
- **THEN** evidence MUST include the exported file and the download/share UI state

### Requirement: Finding classification taxonomy
Every acceptance finding MUST be classified as exactly one of: `PILOT BLOCKER`, `NON-BLOCKING UX IMPROVEMENT`, or `POST-PILOT / BUILD B`. Acceptance MUST NOT invent a fourth class. Desired capabilities outside implemented Build A (including onboarding completion, reopen, refunds, mixed payments, RF-009, offline level expansion, search-by-TRX, and analytics) MUST be classified `POST-PILOT / BUILD B` when raised during this gate, not as silent Carrota product blockers invented by acceptance.

#### Scenario: Cosmetic issue does not block pilot
- **WHEN** a finding is copy, density, or convenience only and the operator can still complete the flow correctly
- **THEN** the finding MUST be classified `NON-BLOCKING UX IMPROVEMENT`

#### Scenario: Broken void on open day is a blocker
- **WHEN** Memoria void of an eligible open-day confirmed sale fails or live totals still include the voided sale
- **THEN** the finding MUST be classified `PILOT BLOCKER`

#### Scenario: Onboarding gap is not reclassified as this gate's blocker
- **WHEN** conversational onboarding or minimum configuration is incomplete
- **THEN** that gap MUST NOT be newly classified as a Carrota `PILOT BLOCKER` by this acceptance change and MUST remain tracked under the active onboarding change or as `POST-PILOT / BUILD B` per product authority

### Requirement: Pilot-ready exit criteria
Carrota MUST be declared pilot-ready only when all blocker-level manual acceptance cases PASS, technical/automated acceptance PASS, and no open finding remains classified `PILOT BLOCKER`. Non-blocking UX improvements MUST NOT prevent pilot readiness.

#### Scenario: Pilot ready with polish backlog
- **WHEN** all blocker-level manual cases and the technical pass PASS and only `NON-BLOCKING UX IMPROVEMENT` findings remain
- **THEN** the verdict MUST be pilot-ready

#### Scenario: Any open blocker prevents pilot ready
- **WHEN** any open finding is classified `PILOT BLOCKER`
- **THEN** the verdict MUST be not pilot-ready

### Requirement: Acceptance does not modify product code or onboarding
Execution and authorship of this acceptance change MUST NOT implement product features, MUST NOT modify `backend/` or `mobile/` as part of defining the checklist, MUST NOT modify `openspec/changes/build-a-conversational-onboarding-and-minimum-configuration/`, MUST NOT archive changes, and MUST NOT require a new ADR unless an architectural decision is actually introduced (expected: none).

#### Scenario: Checklist-only change surface
- **WHEN** this acceptance change is created
- **THEN** its artifacts MUST be OpenSpec proposal/design/tasks/acceptance-spec materials without product delta requirements on existing Build A capabilities
