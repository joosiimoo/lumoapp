## Context

Carrota is the first pilot merchant for Lumo Build A. Product authority is `docs/PRD_Lumo_AI_Native_Managed_Business_Operations_v0.11.md`. Behavioral truth for this gate is **current implemented Build A** plus archived OpenSpec changes (especially Carrota slices: sale corrections, pilot UX convergence, operational surfaces v2, Memoria activity feed v2, transaction references).

This change is an **acceptance procedure**, not a feature. It defines how a human operator and a later Cursor technical pass prove pilot readiness without inventing product work, without touching onboarding, and without re-litigating archived slice acceptances unless user-visible behavior fails now.

Known out-of-gate gap (documented, not invented here): conversational onboarding / minimum configuration remains an active separate change and is **not** part of Carrota pilot-readiness for this checklist. Failures there are `POST-PILOT / BUILD B` or tracked under that active change — not silent pilot blockers invented by this gate.

## Goals / Non-Goals

**Goals:**

- One sequential **manual functional acceptance** checklist (27 cases) for operator-visible Carrota flows.
- One compact **technical / automated acceptance** checklist for Cursor to run later in a single pass.
- Explicit evidence model, finding classification, and pilot-ready exit criteria.
- Trace each case to implemented behavior / archived change evidence — do not invent features.

**Non-Goals:**

- Code changes in `backend/` or `mobile/`.
- Modifying `openspec/changes/build-a-conversational-onboarding-and-minimum-configuration/`.
- Archiving, committing, pushing.
- New ADR, migration, tool/UI registry expansion.
- Replacing PRD §32 merchant-success metrics with this software gate.
- Turning automated unit/integration coverage into redundant manual steps.

## Decisions

### 1. Acceptance split (manual vs technical)

**Decision:** Validate user-visible operator journeys manually; validate integrity, isolation, migrations, exports schema, OpenSpec coherence, and repo hygiene in one Cursor technical pass.

**Rationale:** Manual duplication of pytest/Flutter assertions wastes time and still misses concurrency/RLS. Technical pass cannot substitute for “does the merchant see TRX / can they void from Memoria / does Hoy show today totals.”

**Alternative considered:** Fully automated E2E for all 27 cases → rejected for this gate (fragile, not yet the accepted Carrota evidence path).

### 2. Finding classification (exactly one label)

Every finding MUST be classified as exactly one:

| Class | Meaning | Blocks pilot-ready? |
|---|---|---|
| `PILOT BLOCKER` | Implemented Build A behavior required for Carrota daily ops fails, corrupts data, breaks tenant/safety invariants, or makes a checklist case FAIL at blocker level | Yes |
| `NON-BLOCKING UX IMPROVEMENT` | Cosmetic, copy, density, or convenience issue; core flow still completable correctly | No |
| `POST-PILOT / BUILD B` | Desired capability explicitly out of Build A / deferred (onboarding polish, reopen, refunds, mixed payments, RF-009, offline L2, search-by-TRX, analytics, etc.) | No |

**Rules:**

- Do not invent new features and then mark them blockers.
- If UI cannot prove a safety invariant, escalate that specific invariant to the technical pass — do not require DB inspection for ordinary manual cases.
- Onboarding gaps are not reclassified as Carrota pilot blockers by this change.

### 3. Pilot-ready exit criteria

Carrota is **pilot-ready** when and only when:

1. All manual cases that are blocker-level PASS (see case table; each case defaults to blocker-level unless marked optional).
2. Technical / automated acceptance PASS as a whole.
3. No open finding remains classified `PILOT BLOCKER`.

Non-blocking UX improvements may be listed for later polish and **do not** prevent pilot readiness.

### 4. Evidence model

| Evidence type | When to use |
|---|---|
| **Visible app state** | Default for most cases (cards, totals, statuses, TRX labels, Memoria rows) |
| **Screenshot** | Confirmation of terminal UI state for each major case (sale confirmed, void, close, Hoy, Memoria, exports share sheet) |
| **Exported file** | CSV and XLSX cases only (open file; verify columns/rows) |
| **Log only** | Only when UI cannot prove the behavior and the case still needs a non-DB signal (rare; prefer technical pass for integrity) |

Do **not** require backend/DB inspection for manual cases unless the UI cannot prove the claim. Integrity that UI cannot show (RLS, FORCE RLS, idempotency, concurrent TRX allocation) belongs in technical acceptance.

### 5. Sequential manual execution model

Run cases **in order** on one Carrota tenant / business day when possible. Later cases may rely on artifacts from earlier ones (sales for totals, TRX sequence, Memoria void, close). If a case fails as `PILOT BLOCKER`, stop or continue only to gather evidence — do not declare pilot-ready.

Suggested day shape:

1. Clean start → sales mix (unit/weight/noncatalog/override/remove/pay) → TRX observation.
2. Memoria void (+ TRX linkage) → Inicio/Hoy checks.
3. Close workspace (count, balanced + short/over as needed, note, confirm, close TRX).
4. Memoria + exports + restart + closed-day protection.

Short/over and balanced close may use separate days or sequential recounts only if the product allows re-count before confirm; follow current implemented Hoy close workspace rules (do not invent reopen).

### 6. ADR

**Expected ADR: none.** This change introduces no architectural boundary, persistence contract, or registry change.

### 7. Spec strategy

One new capability spec (`carrota-pilot-final-acceptance`) records the normative acceptance contract (split, classification, evidence, exit criteria). Detailed case procedures live in this design (and tasks) as the executable checklist. No product delta specs.

---

## A. MANUAL FUNCTIONAL ACCEPTANCE

For every case: **Preconditions**, **User action**, **Expected visible result**, **PASS**, **FAIL**, **Evidence**. Default severity if FAIL: `PILOT BLOCKER` unless noted.

Evidence sources (behavioral): archived Carrota/Build A changes cited in brackets.

### M01 — App starts correctly from clean state

- **Preconditions:** App installed/configured for Carrota tenant; cold start (force-quit if needed). Prefer clear local session only if product supports it; otherwise “fresh launch after process kill.”
- **User action:** Launch app; land on Inicio (or configured home).
- **Expected visible result:** App loads without crash; Inicio shows conversational shell (greeting / light operational header + composer); navbar usable (Inicio / Hoy / Memoria as implemented).
- **PASS:** Stable home surface; can type/send or see composer; no blocking error screen.
- **FAIL:** Crash loop, blank/unusable shell, auth hard-fail without recovery, missing primary tabs.
- **Evidence:** Screenshot of Inicio after launch; visible app state.
- **Trace:** `mobile-shell`, core foundation.

### M02 — Catalog sale by unit

- **Preconditions:** Open operational day (or first sale creates day per implementation); catalog product with unit pricing available (e.g. piece/unit).
- **User action:** From Inicio composer, sell one catalog unit product (natural language or established phrase); complete to payment if needed for confirm, or stop at confirmed sale per flow.
- **Expected visible result:** Item recognized from catalog; quantity/unit coherent; line total server-authored; sale can proceed.
- **PASS:** Catalog unit line appears with correct product identity and money display; no client-invented catalog.
- **FAIL:** Wrong product, crash, cannot add unit catalog item, silent no-op.
- **Evidence:** Screenshot of item/summary card; visible app state.
- **Trace:** `catalog-foundation`, conversational sale archives.

### M03 — Catalog sale by weight

- **Preconditions:** Catalog product sold by weight (e.g. kg) with price.
- **User action:** Sell a weight-based catalog quantity (e.g. “2 kg de X”).
- **Expected visible result:** Weight quantity and unit shown; line total matches server; sale can proceed.
- **PASS:** Weight sale line visible and coherent; confirmable.
- **FAIL:** Treated as unit incorrectly, rejected without reason, wrong total display, crash.
- **Evidence:** Screenshot of weight line/summary.
- **Trace:** `catalog-foundation`, conversational sale.

### M04 — Non-catalog sale

- **Preconditions:** Open day; phrase for free-concept / non-catalog item.
- **User action:** Register a non-catalog sale item (e.g. “bolsa de hielo 36”).
- **Expected visible result:** Free-concept line without forcing product creation; price accepted; sale can proceed.
- **PASS:** Non-catalog line present; CAE-003 spirit (no forced product create); confirmable.
- **FAIL:** Forced catalog create, rejection of free concept, wrong persistence presentation.
- **Evidence:** Screenshot of non-catalog line.
- **Trace:** `noncatalog-sale-item` archive.

### M05 — Price override with reason

- **Preconditions:** Catalog product; override path available.
- **User action:** Override catalog price with a different charged price and provide reason; complete add.
- **Expected visible result:** Adjusted price shown; reason captured in UI captions as implemented; catalog list price not silently replaced as “new catalog price” in operator UI.
- **PASS:** Override line shows charged price + reason cue; sale confirmable.
- **FAIL:** Override ignored, reason not required/captured when required, crash, wrong price shown as catalog default without override marking.
- **Evidence:** Screenshot of override captions on item/summary.
- **Trace:** `catalog-price-override` archive.

### M06 — Remove item before payment

- **Preconditions:** Active sale `open` with ≥1 item (not yet totalized/ready_to_charge, or still pre-payment per UI).
- **User action:** Remove one line via secondary remove control.
- **Expected visible result:** Line gone; remaining items/total recomposed; empty sale allowed if last item removed (no confirmed history).
- **PASS:** Removed line absent; totals update; session remains usable.
- **FAIL:** Remove no-op, wrong line removed, crash, phantom total.
- **Evidence:** Screenshot before/after remove.
- **Trace:** `sale-corrections`.

### M07 — Remove item after totalize

- **Preconditions:** Active sale in `ready_to_charge` / summary with ≥1 item.
- **User action:** Remove a line from summary; observe status if emptied.
- **Expected visible result:** Recomposed summary; if items remain, stays ready_to_charge; if emptied, returns to open empty sale per implementation.
- **PASS:** Remove works post-totalize; totals/status coherent.
- **FAIL:** Remove forbidden incorrectly, stale total, stuck ready_to_charge when empty.
- **Evidence:** Screenshot of summary after remove.
- **Trace:** `sale-corrections`.

### M08 — Cash payment

- **Preconditions:** Sale ready to charge with known total.
- **User action:** Pay with cash (`sale.pay.cash@1` / UI).
- **Expected visible result:** `sale_confirmed@1` (or equivalent) shows sale registered; payment method cash; TRX may appear (also covered in M11).
- **PASS:** Confirmed sale visible; cash recorded in confirmation UI.
- **FAIL:** Payment fails, double charge UX, wrong method, no confirmation.
- **Evidence:** Screenshot of confirmation.
- **Trace:** `sale-payment`, `sale-confirmed-ui`.

### M09 — Card payment

- **Preconditions:** New sale ready to charge.
- **User action:** Pay with card.
- **Expected visible result:** Confirmed sale with card method.
- **PASS:** Confirmation shows card; sale appears in day activity.
- **FAIL:** Same as M08 for card.
- **Evidence:** Screenshot of confirmation.
- **Trace:** `sale-payment`.

### M10 — Transfer payment

- **Preconditions:** New sale ready to charge.
- **User action:** Pay with transfer.
- **Expected visible result:** Confirmed sale with transfer method.
- **PASS:** Confirmation shows transfer.
- **FAIL:** Same as M08 for transfer.
- **Evidence:** Screenshot of confirmation.
- **Trace:** `sale-payment`.

### M11 — Transaction-number sequence

- **Preconditions:** At least two successful numbered operations in this business (e.g. two confirmed sales, or sale + void/close later). Prefer observing after M08–M10.
- **User action:** Note TRX on successive confirmations (format `TRX-######`).
- **Expected visible result:** Each new numbered outcome gets a new TRX; values increase for the business; display format stable.
- **PASS:** Distinct monotonic TRX across successive commits; no client-looking random ids as the merchant reference.
- **FAIL:** Missing TRX on new confirmed sale, duplicate TRX on distinct commits, malformed display, Flutter-looking local invent.
- **Evidence:** Screenshots of two successive TRX confirmations; visible app state.
- **Trace:** `transaction-references`.

### M12 — Sale void from Memoria

- **Preconditions:** Confirmed sale on **current open** day; Memoria shows “Venta registrada” (or compact equivalent) with server-authored Anular when eligible.
- **User action:** From Memoria, Anular → confirm void impact → confirm.
- **Expected visible result:** Timeline shows voided sale (“Venta anulada”); Inicio confirmation cards do not become the void entry point; Hoy/Inicio live totals exclude the voided sale.
- **PASS:** Void completes from Memoria; aggregates drop the sale; void event visible.
- **FAIL:** Cannot void open-day sale from Memoria; void deletes history; totals still include voided sale; Anular appears on closed-day ineligible sale without server auth.
- **Evidence:** Screenshots of Memoria before/after; Hoy totals after void.
- **Trace:** `sale-corrections`, `memoria-timeline`.

### M13 — Void gets own TRX and references original TRX

- **Preconditions:** Complete M12 on a sale that had `TRX-A`.
- **User action:** Inspect void confirmation / Memoria void row.
- **Expected visible result:** Void shows its own `TRX-B` ≠ `TRX-A`, and references original (`Anula TRX-A` or equivalent).
- **PASS:** Distinct void TRX + original reference visible.
- **FAIL:** Same TRX reused, missing original reference, missing void TRX.
- **Evidence:** Screenshot of void TRX line.
- **Trace:** `transaction-references`, `memoria-timeline`.

### M14 — Inicio operational state

- **Preconditions:** Open day with some confirmed sales (post-void totals coherent).
- **User action:** Open Inicio; observe light header / Business Stream compact state (not a KPI dashboard).
- **Expected visible result:** Concise operational state (e.g. sales sentence, Caja/close-related indicator as implemented); transcript + composer remain primary; no Daily Close CTAs crowding Inicio if operational-surfaces-v2 is live.
- **PASS:** Inicio readable as operation surface; state matches day; not a POS grid.
- **FAIL:** Blank/wrong state, crash, Inicio becomes analytics dashboard, stale closed CTAs when day open (or reverse).
- **Evidence:** Screenshot of Inicio header + transcript region.
- **Trace:** `business-stream`, `operational-surfaces-v2`, `pilot-ux-convergence`.

### M15 — Hoy sales/payment totals

- **Preconditions:** Mix of cash/card/transfer confirmed sales; voids excluded from live totals.
- **User action:** Open Hoy; read sales count/total and payment split.
- **Expected visible result:** Server-authored totals; payment methods split; close state / next close action as implemented; coverage limitation copy if present.
- **PASS:** Totals match the operator’s mental sum of live confirmed sales (within displayed precision); voided sales excluded.
- **FAIL:** Totals include voided, wrong split, client-invented math obvious mismatch, Hoy empty when sales exist.
- **Evidence:** Screenshot of Hoy summary.
- **Trace:** `business-stream`, `sales-export-ui` placement unchanged.

### M16 — Cash count

- **Preconditions:** Open day with cash sales (expected cash > 0 ideal).
- **User action:** From Hoy, open close workspace (**Preparar el cierre del día**); enter counted cash; submit count.
- **Expected visible result:** Server reconciliation shows counted vs expected and difference; workspace stays on Hoy path (no forced Inicio composer handoff).
- **PASS:** Count accepted; difference visible; proceeds toward close.
- **FAIL:** Count rejected incorrectly, no difference display, forces broken navigation, client-side wrong expected cash.
- **Evidence:** Screenshot of reconciliation in close workspace.
- **Trace:** `cash-count-foundation`, `operational-surfaces-v2`.

### M17 — Balanced close

- **Preconditions:** Counted cash equals expected cash (or re-count to balance before confirm if allowed).
- **User action:** Confirm close with balanced cash.
- **Expected visible result:** Day closes; confirmation shows balanced/closed state; Hoy shows closed day.
- **PASS:** Close succeeds when balanced; day status closed in UI.
- **FAIL:** Balanced close blocked, false imbalance, day remains open after successful confirm UX.
- **Evidence:** Screenshot of close confirmation + closed Hoy.
- **Trace:** `daily-close-confirmation`, close workspace.

### M18 — Short/over close

- **Preconditions:** Open day (new day or pre-confirm state) where counted cash ≠ expected (short or over). Use a fresh open day if M17 already closed today.
- **User action:** Count with intentional short or over; confirm close if product allows (Build A allows short/over close).
- **Expected visible result:** Difference visible before confirm; close still completable; difference retained in confirmation/Memoria facts as implemented.
- **PASS:** Short/over visible and close allowed; no false “cuadrada” when difference exists.
- **FAIL:** Difference hidden, close blocked solely for short/over when Build A allows it, or marked balanced incorrectly.
- **Evidence:** Screenshot of difference + closed confirmation.
- **Trace:** `daily-close-confirmation`, `cash-count-foundation`.

### M19 — Optional close note

- **Preconditions:** In close workspace before confirm.
- **User action:** Enter optional close note; confirm close.
- **Expected visible result:** Note accepted (or blank omitted); appears on confirmation and/or Memoria close entry when present.
- **PASS:** Note round-trips to visible close artifact when provided; blank note does not block.
- **FAIL:** Note crashes confirm, required incorrectly, never shown when provided.
- **Evidence:** Screenshot of note on confirm and/or Memoria.
- **Trace:** `operational-surfaces-v2` (`close_note`).

### M20 — Daily close confirmation

- **Preconditions:** Close workspace ready to confirm (token/action as implemented).
- **User action:** Tap **Cerrar el día** / confirm; dismiss completion.
- **Expected visible result:** Explicit closed confirmation; no stale open-day close CTAs; Inicio/Hoy refresh to closed.
- **PASS:** Single clear confirmation; day closed; no double-close success theater.
- **FAIL:** Confirm no-op, duplicate closes, stale CTAs after close, false success.
- **Evidence:** Screenshot of confirmation + Hoy closed.
- **Trace:** `daily-close-confirmation`, `daily-close-confirmed-ui`.

### M21 — Close receives TRX

- **Preconditions:** Successful daily close (M17/M18/M20).
- **User action:** Read close confirmation and Memoria close row.
- **Expected visible result:** Close shows `TRX-…`; cash-count events do **not** get TRX.
- **PASS:** Close TRX visible; cash count without TRX.
- **FAIL:** Missing close TRX; cash count incorrectly numbered.
- **Evidence:** Screenshot of close TRX; Memoria close vs cash-count rows.
- **Trace:** `transaction-references`.

### M22 — Memoria timeline

- **Preconditions:** Day with sale_confirmed, sale_voided (if done), cash_count_recorded, daily_close_completed as available.
- **User action:** Open Memoria; scan compact activity feed.
- **Expected visible result:** Newest-first chronological feed; date grouping; compact rows (not oversized cards); TRX secondary lines where applicable; void Anular only when server provides actions.
- **PASS:** Events present, ordered, readable; types correct.
- **FAIL:** Missing events, wrong order, UUID-primary clutter, client-invented eligibility actions, empty when events exist.
- **Evidence:** Screenshot of Memoria feed.
- **Trace:** `memoria-timeline` v2.

### M23 — CSV export

- **Preconditions:** Hoy has export; day has ≥1 sale item row (confirmed/voided as applicable).
- **User action:** Download CSV.
- **Expected visible result:** File shares/downloads; opens with expected columns including `sale_status`, `sale_transaction_number`, `void_transaction_number` (and established export schema).
- **PASS:** CSV present; schema columns present; voided rows marked; TRX columns populated for numbered sales.
- **FAIL:** Missing file, truncated schema, wrong grain (not per SaleItem), missing TRX columns post-0018.
- **Evidence:** Exported file + screenshot of share/download UI.
- **Trace:** `daily-sales-export`, `transaction-references`.

### M24 — XLSX export

- **Preconditions:** Same as M23.
- **User action:** Download Excel/XLSX.
- **Expected visible result:** Same schema/grain as CSV in spreadsheet form.
- **PASS:** XLSX opens; columns match contract; data coherent with CSV.
- **FAIL:** Corrupt file, schema drift vs CSV, empty sheet when sales exist.
- **Evidence:** Exported file + screenshot.
- **Trace:** `daily-sales-export`.

### M25 — Restart / persistence

- **Preconditions:** After meaningful state (open day with sales, or closed day, and/or open WorkItems if visible).
- **User action:** Force-quit app; relaunch; revisit Inicio / Hoy / Memoria.
- **Expected visible result:** Durable server state remains (sales, close status, Memoria events, totals); no “amnesia” of confirmed operations.
- **PASS:** Post-restart surfaces match pre-restart durable facts.
- **FAIL:** Confirmed sales disappear, closed day reopens, Memoria empty incorrectly.
- **Evidence:** Screenshots before/after restart.
- **Trace:** persistence / Event Memory / operational day archives.

### M26 — Closed-day mutation protection

- **Preconditions:** Day is `closed`.
- **User action:** Attempt void of a sale from that closed day (Memoria); attempt new sale if product routes to same closed day; attempt another close confirm.
- **Expected visible result:** Void refused for closed-day sales; no reopen; no second ClosingSnapshot success; operator sees clear refusal (not silent success).
- **PASS:** Closed day immutable for voids/reclose; safe refusal UX.
- **FAIL:** Void succeeds on closed day, reopen invented, second close succeeds, silent data mutate.
- **Evidence:** Screenshot of refusal; Memoria unchanged for illegal void.
- **Trace:** `sale-corrections`, `daily-close-confirmation`.

### M27 — Restart-safe Memoria actions where applicable

- **Preconditions:** Open day; confirmed sale still eligible for void; note any Anular action before restart.
- **User action:** Restart app; open Memoria; if sale still eligible, complete void (or observe action still server-authored).
- **Expected visible result:** Actions remain server-authored after restart; stale tokens fail safely; eligible void still works end-to-end.
- **PASS:** Post-restart void path works or safely reports stale/ineligible without corrupting state.
- **FAIL:** Phantom client-only Anular; crash; double-void; action succeeds against closed/ineligible sale.
- **Evidence:** Screenshot of Memoria actions post-restart + result.
- **Trace:** `memoria-timeline`, `generative-ui-actions`, `sale-corrections`.

---

## B. TECHNICAL / AUTOMATED ACCEPTANCE

Run as **one compact Cursor pass**. Record PASS/FAIL per item. Any FAIL that breaks integrity, tenancy, migrations, or pilot-critical contracts → `PILOT BLOCKER`. Tooling/noise → classify carefully (do not inflate blockers).

| ID | Check | How (compact) | PASS criteria |
|---|---|---|---|
| T01 | Backend targeted/full tests | `pytest` in `backend/` (full suite or documented targeted set covering sales, corrections, close, memory, export, TRX, tenancy) | Green; no new failures vs known baseline |
| T02 | Flutter tests | `flutter test` in `mobile/` | Green |
| T03 | flutter analyze | `flutter analyze` in `mobile/` | No error-level issues (warnings triage: non-blocking unless they indicate broken API use) |
| T04 | Migration base→head | Alembic upgrade from base through head (incl. `0018_transaction_references`) via existing migration tests/helpers | Completes cleanly |
| T05 | Migration integrity | Review/tests for CHECKs, backfill, counter init, close_note, corrections, TRX ordering | Constraints and backfill expectations hold |
| T06 | RLS / FORCE RLS | Integrity/tenancy/migration tests asserting RLS + FORCE RLS on business tables including counters | PASS |
| T07 | Tenant isolation | `test_tenant_isolation` / integrity suite | Cross-tenant reads/writes blocked |
| T08 | Idempotency | Sale pay/void/close replay tests | No duplicate commits; stable TRX on post-0018 replay |
| T09 | Transaction-reference concurrency | TRX allocator concurrency tests (incl. first allocation) | Unique monotonic sequences; one counter row |
| T10 | Event Memory integrity | Factual memory / source coverage tests; fact key CHECKs | Exact facts; void/close/sale events coherent |
| T11 | Export schema | Daily sales export tests | CSV/XLSX columns incl. status + TRX fields; grain = SaleItem |
| T12 | OpenSpec strict validation | `openspec validate build-a-carrota-pilot-final-acceptance --strict` and `openspec validate --all --strict` | All pass |
| T13 | Active onboarding untouched | Diff/status: no edits under `openspec/changes/build-a-conversational-onboarding-and-minimum-configuration/` | Unmodified by this acceptance work |
| T14 | Repo status / no unintended files | `git status` review | No accidental backend/mobile/onboarding edits from acceptance execution |
| T15 | No archived-change drift | Confirm acceptance does not rewrite `openspec/changes/archive/**` | Archives immutable |

Technical pass does **not** re-run manual UI cases.

---

## Evidence package (recommended)

When executing acceptance, collect:

1. Checklist sheet (M01–M27, T01–T15) with PASS/FAIL + classification per finding.
2. Screenshot set keyed by case id.
3. CSV + XLSX files from M23/M24.
4. Technical command log (pytest/flutter/openspec summaries).
5. Final verdict: `PILOT_READY` or `NOT_PILOT_READY` with open blockers listed.

## Risks / Trade-offs

- **[Risk] Manual day sequencing conflicts (close then need short/over)** → Mitigation: use a second open day or perform short/over before final balanced narrative; do not invent reopen.
- **[Risk] Operator mis-sums Hoy totals** → Mitigation: use small controlled sale set; technical export tests backstop schema, not mental math.
- **[Risk] Classifying UX nits as blockers** → Mitigation: strict three-way taxonomy; pilot-ready ignores non-blocking UX.
- **[Risk] Onboarding absence mistaken for Carrota blocker** → Mitigation: explicit non-goal; classify as post-pilot / separate change.
- **[Risk] Checklist drifts from product** → Mitigation: behavior traced to archived specs; do not invent features during FAIL analysis.

## Migration Plan

Not applicable — no schema or deploy migration in this change.

## Open Questions

- None blocking artifact creation. Execution-time only: which physical device/emulator and which provisioned Carrota tenant credentials the human tester uses (outside OpenSpec).
