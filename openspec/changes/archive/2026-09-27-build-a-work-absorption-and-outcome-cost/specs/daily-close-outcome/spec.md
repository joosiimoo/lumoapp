## MODIFIED Requirements

### Requirement: Outcome writes join the parent transaction only
Outcome sync MUST run only inside successful `sale.commit@1`, a new current CashCount insert, and successful `closing.confirm@1`, in the order `daily-close-outcome` design records. The same transactions MUST upsert `WorkAbsorptionRecord` rows and maintain `OutcomeCost` as `work-absorption` and `outcome-cost` require. `closing.prepare@1`, `operational_day.summary@1`, daily sales export, the Next Best Action GET, `GET /api/v1/business-stream/today`, `operational_day.next_best_action@1`, an equal-amount cash-count read-back, a clarify, a stale confirmation, an idempotent replay, and an already-closed read-back MUST NOT insert or update an OutcomeRun, a WorkAbsorptionRecord, or an OutcomeCost. A failure before commit MUST leave no new OutcomeRun, absorption row, cost row, or outcome audit from that attempt. Export column names, file bytes, close phrases, close gates, reason codes, and merchant-visible close behavior MUST stay unchanged.

#### Scenario: Preparation does not write the outcome
- **WHEN** the actor posts `preparar el cierre` for an open day that already has an OutcomeRun
- **THEN** that OutcomeRun MUST be unchanged, no outcome audit MUST be written, and absorption and cost row counts MUST be unchanged

#### Scenario: Export does not write the outcome
- **WHEN** a tenant downloads the daily sales export
- **THEN** OutcomeRun, WorkAbsorptionRecord, OutcomeCost, audit, outbox, and idempotency row counts MUST be unchanged by that download

#### Scenario: A rolled-back commit leaves no outcome
- **WHEN** the first commit of the day fails before commit after preparing an OutcomeRun insert
- **THEN** that OutcomeRun MUST NOT remain and no absorption or cost row from that attempt MUST remain

#### Scenario: Business Stream does not write the outcome
- **WHEN** `GET /api/v1/business-stream/today` runs for an open day that already has an OutcomeRun
- **THEN** that OutcomeRun MUST be unchanged, no outcome audit MUST be written, and absorption and cost row counts MUST be unchanged

#### Scenario: Close instrumentation does not change gates
- **WHEN** a short or over day is closed with `closing.confirm@1`
- **THEN** ClosingSnapshot, WorkItem resolution, and OutcomeRun completion semantics MUST match the pre-instrumentation contract while six absorption rows and one OutcomeCost row exist

## ADDED Requirements

### Requirement: Instrumentation is written before OutcomeRun completion
Any transaction that creates or repairs an OutcomeRun and writes work-absorption or outcome-cost rows MUST insert or upsert all required instrumentation while the OutcomeRun `status` is `in_progress` or `ready`, then transition the OutcomeRun to `completed` in that same transaction. A repair that previously inserted an OutcomeRun born `completed` MUST instead use a non-completed state until instrumentation is present, then set `completed` before commit. The database MUST reject `INSERT` or `UPDATE` on absorption or cost rows when the owning OutcomeRun is already `completed`.

#### Scenario: Repair close orders instrumentation before completed
- **WHEN** `closing.confirm@1` repairs a missing OutcomeRun for a day that is closing
- **THEN** absorption and cost rows MUST exist before the OutcomeRun row becomes `completed`, and no instrumentation insert MAY succeed after the run is `completed`


### Requirement: Daily Close instrumentation observes existing behavior
Instrumentation for `daily_close_ready@1` MUST NOT add merchant steps, WorkItem types, OutcomeRun statuses, reason codes, or close gates solely to improve metrics. It MUST record how the existing flow produced the outcome. E26 product intent applies: six formerly manual administrative tasks, two eliminated as merchant work, two prepared by Lumo, two executed with confirmation, with minutes derived from the versioned baseline. The implemented mapping MUST use the six `task_type` values in `work-absorption`, not one row per sale or message. If pilot reporting needs "avoided cost," that MUST use internal baseline minutes only and MUST NOT be exposed as a merchant savings claim in Build A.

#### Scenario: No new close gate for metrics
- **WHEN** the API route table and Daily Close tools are inspected after instrumentation
- **THEN** no new merchant route, tool, or WorkItem type MUST exist solely for work absorption or outcome cost
