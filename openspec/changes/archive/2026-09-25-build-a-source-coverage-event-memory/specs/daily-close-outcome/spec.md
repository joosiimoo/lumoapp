## ADDED Requirements

### Requirement: A completed outcome is not full source coverage
`daily_close_ready@1` with `status=completed` MUST mean the Daily Close responsibility for operations represented in Lumo was completed. It MUST NOT mean that all real-world business operations were captured. Outcome evidence MUST keep the keys `daily-close-outcome` already requires and MUST NOT gain a source-coverage id, a coverage summary, a completeness percentage, or merchant prose. Completing the OutcomeRun MUST NOT by itself insert or update a coverage row; coverage writes stay on the hooks in `source-coverage`. `OutcomeEngine.evaluate` MUST NOT insert a coverage row or a business event.

#### Scenario: Completion leaves evidence without coverage
- **WHEN** `closing.confirm@1` completes the OutcomeRun
- **THEN** the OutcomeRun MUST be `completed` with `reason_code=closed_confirmed`, and its `evidence` object MUST NOT contain `source_coverage_id`, `coverage_summary`, or a completeness percentage

#### Scenario: Evaluation does not write coverage or memory
- **WHEN** a caller evaluates `daily_close_ready@1` with confirmed state
- **THEN** the engine MUST NOT insert or update a coverage row or a business event
