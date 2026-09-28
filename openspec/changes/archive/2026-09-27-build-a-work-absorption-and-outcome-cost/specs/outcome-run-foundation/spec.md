## ADDED Requirements

### Requirement: OutcomeRun remains the economic unit without embedded cost
`operations.outcome_runs` MUST continue to store no `cost_summary`, token counts, infrastructure amounts, or work-absorption fields. Cost MUST live only on `operations.outcome_costs`. Work absorption MUST live only on `operations.work_absorption_records`. Completing an OutcomeRun MUST finalize related absorption and cost rows in the same parent transaction before `status` becomes `completed`. After `status=completed`, absorption and cost rows for that run MUST NOT be inserted or updated. Database triggers MUST enforce both `INSERT` and `UPDATE` rejection. Repair paths MUST NOT leave an OutcomeRun `completed` until instrumentation for that close exists in the same transaction.

#### Scenario: Completed run keeps a slim outcome row
- **WHEN** a Daily Close OutcomeRun is `completed`
- **THEN** its columns MUST match the pre-instrumentation contract and cost MUST be readable only from `operations.outcome_costs`

#### Scenario: Merchant outcome evidence is unchanged
- **WHEN** `closing.confirm@1` completes an OutcomeRun
- **THEN** outcome `evidence` MUST NOT gain absorption percentages, cost fields, or token counts
