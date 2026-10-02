## 1. Acceptance kit readiness

- [x] 1.1 Confirm product authority is `docs/PRD_Lumo_AI_Native_Managed_Business_Operations_v0.11.md` and behavioral truth is current implemented Build A + archived Carrota changes (no feature invention)
- [x] 1.2 Confirm non-touch surfaces: no edits to `backend/`, `mobile/`, or `openspec/changes/build-a-conversational-onboarding-and-minimum-configuration/`; no archive/commit/push as part of defining this change
- [x] 1.3 Prepare evidence package template (checklist sheet M01–M27 / T01–T15, screenshot slots, export file slots, technical command log, final verdict field)
- [x] 1.4 Confirm finding taxonomy cards are available to the tester: `PILOT BLOCKER` | `NON-BLOCKING UX IMPROVEMENT` | `POST-PILOT / BUILD B`

## 2. Manual functional acceptance (operator)

- [x] 2.1 M01 App starts correctly from clean state
- [x] 2.2 M02 Catalog sale by unit
- [x] 2.3 M03 Catalog sale by weight
- [x] 2.4 M04 Non-catalog sale
- [x] 2.5 M05 Price override with reason
- [x] 2.6 M06 Remove item before payment
- [x] 2.7 M07 Remove item after totalize
- [x] 2.8 M08 Cash payment
- [x] 2.9 M09 Card payment
- [x] 2.10 M10 Transfer payment
- [x] 2.11 M11 Transaction-number sequence
- [x] 2.12 M12 Sale void from Memoria
- [x] 2.13 M13 Void gets own TRX and references original TRX
- [x] 2.14 M14 Inicio operational state
- [x] 2.15 M15 Hoy sales/payment totals
- [x] 2.16 M16 Cash count
- [x] 2.17 M17 Balanced close
- [x] 2.18 M18 Short/over close (separate open day if M17 already closed today)
- [x] 2.19 M19 Optional close note
- [x] 2.20 M20 Daily close confirmation
- [x] 2.21 M21 Close receives TRX
- [x] 2.22 M22 Memoria timeline
- [x] 2.23 M23 CSV export (retain file)
- [x] 2.24 M24 XLSX export (retain file)
- [x] 2.25 M25 Restart/persistence
- [x] 2.26 M26 Closed-day mutation protection
- [x] 2.27 M27 Restart-safe Memoria actions where applicable
- [x] 2.28 For every manual FAIL, classify exactly one label and attach required evidence; do not invent features to “fix” during acceptance

> Operator manual acceptance: M01–M27 **PASS** (executed by operator in the running app; not re-run by Cursor).

## 3. Technical / automated acceptance (Cursor compact pass)

- [x] 3.1 T01 Backend targeted/full tests (`pytest` in `backend/`) — **428 passed**
- [x] 3.2 T02 Flutter tests (`flutter test` in `mobile/`) — operator evidence: **109 passed** (not re-run)
- [x] 3.3 T03 `flutter analyze` in `mobile/` — operator evidence: **No issues found** (not re-run)
- [x] 3.4 T04 Migration base→head (incl. through `0018`) — covered by full suite migration tests
- [x] 3.5 T05 Migration integrity (CHECKs/backfill/counters/close_note/corrections/TRX order)
- [x] 3.6 T06 RLS / FORCE RLS
- [x] 3.7 T07 Tenant isolation
- [x] 3.8 T08 Idempotency (sale pay/void/close; stable post-0018 TRX replay)
- [x] 3.9 T09 Transaction-reference concurrency
- [x] 3.10 T10 Event Memory integrity
- [x] 3.11 T11 Export schema (CSV/XLSX columns + SaleItem grain)
- [x] 3.12 T12 OpenSpec strict validation (`openspec validate build-a-carrota-pilot-final-acceptance --strict` and `openspec validate --all --strict`) — **47 passed, 0 failed**
- [x] 3.13 T13 Active onboarding change remains untouched
- [x] 3.14 T14 Repo status / no unintended files from acceptance work
- [x] 3.15 T15 No archived-change drift (`openspec/changes/archive/**` unmodified)

## 4. Verdict

- [x] 4.1 Aggregate manual + technical results; list all findings with exactly one classification each — see `acceptance.md`
- [x] 4.2 Apply pilot-ready rule: all blocker-level manual cases PASS + technical PASS + zero open `PILOT BLOCKER`
- [x] 4.3 Record verdict `PILOT_READY` or `NOT_PILOT_READY` with open blockers (if any) and non-blocking backlog (if any) — **`PILOT_READY`**
- [x] 4.4 Stop — do not implement fixes, do not archive, do not commit/push unless explicitly requested in a later change
