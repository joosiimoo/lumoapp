# Acceptance notes

Tasks 24/24. Manual acceptance 11.1 and 11.2 PASS.

## A. Automated acceptance

- Backend: **317 passed** (full suite at implementation sign-off)
- Flutter: **72 passed**
- `fvm flutter analyze`: clean
- OpenSpec: **39/39** strict validation
- Migration head: `0012_source_coverage_event_memory` — no `0013`
- ADR-027: **Accepted**

## B. Manual 11.1 PASS

- `no_active_day`
- `cash_count_required`
- `cash_difference`
- `ready_to_close`
- `Revisar cierre` reused existing conversation flow (`cerrar el día` on shell `conversation_id`)
- `closing.confirm@1` stayed card-only
- `closed` state with ClosingSnapshot-aligned facts

## C. Copy defect discovered and fixed

Observed: `1 ventas`

Corrected: `1 venta`

Regression: `saleCountLabel(1)` → `1 venta`; `saleCountLabel(2)` → `2 ventas`

## D. Stale API image incident

- Initial `GET /api/v1/business-stream/today` returned HTTP 404 (`TENANT_SCOPE_VIOLATION` / Not Found)
- Root cause: stale Docker `lumo-api` image — route absent from running OpenAPI
- Fix: `docker compose build api` + `docker compose up -d api` only
- No product-code fix required
- After rebuild: HTTP 200 `no_active_day` when no OperationalDay; HTTP 200 `closed` for accepted Carrota state

## E. Manual 11.2 PASS

**Repeated GET (×3):** HTTP 200, `operator_state=closed`, same snapshot facts; only `as_of` changed. No row writes.

**Tenant isolation:** Test-owned tenant B → `no_active_day`; no Carrota `22.50`, ids, or snapshot leakage.

**Anti-POS:** Surface reads as current operational responsibility with at most one next action; not POS grid, dashboard, or feed.

**Historical conversation card:** Prior `Cerrar el día` card remains expected history below the panel; closed Business Stream has `primary_action=null`; page load does not emit a new card for the stream.

## F. Final Carrota accepted state (`business_date` 2026-09-26)

- OperationalDay: **closed** (`01a0e0bb-e090-731e-936e-b77b396345a7`)
- 1 confirmed SaleSession; 1 cash Payment **22.50**
- CashCounts: **20.00** (superseded), **22.50** (current)
- 3 resolved WorkItems; 1 completed OutcomeRun (`closed_confirmed`)
- 1 ClosingSnapshot (`01a0e0c5-3041-7b28-9f4b-0467a65511fe`)
- 2 source coverage rows; 4 business events
- Snapshot: sale_count **1**, gross **22.50**, expected/counted **22.50**, difference **0.00**, **balanced**

## G. No-write accepted counts (Carrota, after 11.2 reads)

| Entity | Count |
|--------|------:|
| operational_days | 1 |
| closing_snapshots | 1 |
| cash_counts | 2 |
| work_items | 3 |
| outcome_runs | 1 |
| source_coverage_records | 2 |
| business_events | 4 |
| audit_events | 18 |
| outbox_events | 8 |
| idempotency_records | 6 |
