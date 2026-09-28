# Acceptance notes

Manual acceptance PASS. Tasks 30/30. ADR-028 Accepted.

## A. Automated acceptance

- Backend suite: **328 passed**
- Targeted instrumentation tests (`test_work_absorption_outcome_cost.py`, migration `0012` → `0013`): **passed**
- Tenant isolation (RLS): **passed**
- Intervention semantics (NULL vs measured zero, negatives rejected): **passed**
- Post-complete INSERT/UPDATE freeze on absorption and cost: **passed** (automated)
- OpenSpec: **40/40** (`--strict`)

## B. Manual 8.1 PASS — Carrota 2026-09-27

Product flow only (no synthetic SQL): sale → payment → cash count → close confirmation.

- OutcomeRun `01a0e422-0448-7703-b0e0-626635eaea1b`: `daily_close_ready` v1, **completed**, linked to ClosingSnapshot `01a0e422-0507-75f5-8d28-d42ba33e73d1`
- Exactly **6** `WorkAbsorptionRecord` rows, **1** `OutcomeCost` `01a0e422-0464-7ab0-8ae9-d25d137efe58`, no duplicates

## C. Six tasks

`organize_registered_sales`, `calculate_expected_cash`, `record_cash_count`, `reconcile_cash`, `prepare_close`, `confirm_close`

## D. Execution modes

2× `fully_automated`, 2× `prepared_by_lumo`, 2× `executed_with_confirmation`

## E. Automation rollup

2× `automated`, 4× `assisted` (no percentages or scores)

## F. Baseline

`daily_close_ready@1/work_absorption_baseline@1`

Totals: `human_steps_before` **6**, `human_steps_after` **2**, `estimated_minutes_saved` **8**

Two minutes per eliminated human step is a **provisional pilot estimate**, not measured elapsed time, not a merchant-facing ROI claim; baseline is **versioned**.

## G. Intervention

All six absorption rows and OutcomeCost: `business_intervention_seconds` **NULL**, `internal_intervention_seconds` **NULL** (unknown / not measured).

Semantics: **NULL** = unknown; **0** = measured zero; **>0** = measured duration.

## H. OutcomeCost

USD; model/token **unavailable** (NULL counts/amounts); infrastructure **unavailable** (NULL); `retry_count` **0** measured; intervention **NULL**; `estimated_total_cost_amount` **NULL**; `cost_completeness` **partial**. Unavailable is not zero.

## I. Merchant experience — PASS

No absorption, minutes-saved, cost, token/infra, or automation UI. Business Stream and Daily Close behavior unchanged.
