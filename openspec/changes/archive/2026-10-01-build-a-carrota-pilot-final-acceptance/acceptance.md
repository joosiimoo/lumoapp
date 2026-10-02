# Carrota pilot final acceptance — results

| Field | Value |
|---|---|
| Change | `build-a-carrota-pilot-final-acceptance` |
| Product authority | `docs/PRD_Lumo_AI_Native_Managed_Business_Operations_v0.11.md` |
| Manual functional (M01–M27) | **PASS** — operator manual acceptance in running app (not re-run by Cursor) |
| Flutter (T02/T03) | **PASS** — operator evidence: `fvm flutter test` 109 passed; `fvm flutter analyze` No issues found (not re-run by Cursor) |
| Technical pass date | 2026-10-01 |
| Verdict | **PILOT_READY** |

---

## Finding classification

| Finding | Class | Notes |
|---|---|---|
| _(none)_ | — | No open `PILOT BLOCKER` |
| Pre-existing untracked `backend/uv.lock`, `mobile/.fvm/*`, `docs/reviews/` | `NON-BLOCKING UX IMPROVEMENT` / hygiene | Present before this acceptance pass; not introduced by checklist execution; not product blockers |

No `POST-PILOT / BUILD B` findings raised by this technical pass. Onboarding remains an active separate change and is out of this gate (unchanged).

---

## A. Manual functional acceptance (operator)

All **M01–M27** and task **2.28**: **PASS** (operator manual acceptance). Cursor did not re-execute these cases.

---

## B. Technical / automated acceptance (T01–T15)

| ID | Check | Status | Evidence |
|---|---|---|---|
| T01 | Backend targeted/full tests | **PASS** | `python -m pytest` in `backend/`: **428 passed**, 1 warning (Starlette/httpx TestClient deprecation), 91.49s |
| T02 | Flutter tests | **PASS** | Operator: `fvm flutter test` → 109 passed (not re-run) |
| T03 | flutter analyze | **PASS** | Operator: `fvm flutter analyze` → No issues found (not re-run) |
| T04 | Migration base→head | **PASS** | Covered by full suite incl. `*_migration.py` and TRX `0018` migration tests (base→head helpers) |
| T05 | Migration integrity | **PASS** | CHECKs/backfill/counters/close_note/corrections/TRX order exercised in migration suites within the 428 |
| T06 | RLS / FORCE RLS | **PASS** | e.g. `test_force_rls_and_no_bypass`, RLS assertions across close/count/memory/instrumentation |
| T07 | Tenant isolation | **PASS** | `test_tenant_isolation` + cross-tenant refusals across sale/close/memory/stream |
| T08 | Idempotency | **PASS** | Pay/void/close/recount/message idempotency tests in full suite |
| T09 | TRX concurrency | **PASS** | `test_concurrent_allocations_*`, `test_concurrent_first_allocation_*`, `test_concurrent_void_allocates_one_void_number` |
| T10 | Event Memory integrity | **PASS** | `test_factual_memory`, `test_source_coverage_event_memory*` |
| T11 | Export schema | **PASS** | `test_daily_sales_export`, TRX export column tests in `test_transaction_references` / void export in `test_sale_corrections` |
| T12 | OpenSpec strict | **PASS** | `openspec validate build-a-carrota-pilot-final-acceptance --strict` → valid; `openspec validate --all --strict` → **47 passed, 0 failed** |
| T13 | Active onboarding untouched | **PASS** | `git status` clean for `openspec/changes/build-a-conversational-onboarding-and-minimum-configuration/` |
| T14 | Repo status / no unintended acceptance files | **PASS** | Acceptance artifacts only under `openspec/changes/build-a-carrota-pilot-final-acceptance/`; no `backend/app`, `backend/migrations`, `backend/tests`, or `mobile/lib` diffs from this pass |
| T15 | No archived-change drift | **PASS** | `openspec/changes/archive/**` unmodified |

---

## Pilot-ready rule

1. All blocker-level manual cases PASS — **yes** (operator).
2. Technical acceptance PASS — **yes** (T01–T15).
3. No open `PILOT BLOCKER` — **yes**.

**Final verdict: `PILOT_READY`**

---

## Stop constraints honored

- No feature implementation / fixes.
- No archive.
- No commit / push.
- Onboarding change not modified.
- Flutter test/analyze not re-run.
- Manual M01–M27 not re-run.
