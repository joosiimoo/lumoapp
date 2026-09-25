## MODIFIED Requirements

### Requirement: OutcomeEngine contract
`OutcomeEngine` MUST accept versioned outcome definitions and evaluate gates deterministically from confirmed state. The LLM MUST NOT overwrite a gate result. The engine port MUST register `daily_close_ready@1` as specified by `daily-close-outcome` and MUST NOT register `daily_sales_operations_ready@1`. `evaluate` MUST ignore model text. An unknown outcome id MUST return the evaluation verdict `not_ready` and MUST NOT write. `not_ready` MUST NOT be an `OutcomeRun.status`, a persisted reason, or a value of the `operations.outcome_runs` status check. Persisted statuses MUST remain `in_progress`, `ready`, and `completed`. Evaluating `daily_close_ready@1` MUST return one of those three predicate statuses and MUST NOT insert or update an OutcomeRun. Cash-count, preparation, and close-confirmation activity MUST change an OutcomeRun only through the write hooks in `daily-close-outcome`, not through `evaluate`.

#### Scenario: Unknown outcome fails closed
- **WHEN** a caller evaluates `daily_sales_operations_ready@1`
- **THEN** the engine MUST return the evaluation verdict `not_ready`, MUST NOT write an OutcomeRun, and MUST NOT store `not_ready` as a status or reason

#### Scenario: Model text cannot complete a gate
- **WHEN** a model response claims an outcome is complete
- **THEN** the engine MUST ignore that claim and use only the registered gate function

#### Scenario: Balanced cash is ready only through the write hook
- **WHEN** a balanced cash count is recorded for today's OperationalDay
- **THEN** the persisted OutcomeRun MUST be `ready` because the cash-count transaction ran the write hook, and a later `evaluate` call MUST NOT insert a second row

#### Scenario: Confirmed close completes the registered outcome
- **WHEN** `closing.confirm@1` commits a snapshot
- **THEN** the persisted OutcomeRun MUST be `completed` and `daily_close_ready.execute@1` MUST remain unregistered

### Requirement: Next Best Action tool and component are registered
`ToolRegistry` MUST include `operational_day.next_best_action@1` as specified by `next-best-action`. `PolicyEngine` MUST include `NBA-001`. `GenerativeUIRegistry` MUST include `next_best_action` version `1`. `UiActionRegistry` MUST NOT gain an action id. `closing.reopen@1`, `operational_day.export_sales@1`, `payment.resolve`, and `daily_close_ready.execute@1` MUST remain unregistered. The outcome definition registry MUST contain `daily_close_ready@1`. Projecting `outcome_type=daily_close_ready` MUST NOT by itself insert an OutcomeRun.

#### Scenario: Boot catalog gains the read tool and the card
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `operational_day.next_best_action@1`, `GenerativeUIRegistry` MUST report `next_best_action` version `1`, the outcome registry MUST report `daily_close_ready@1`, and `UiActionRegistry` MUST still contain exactly `sale.pay.cash@1`, `sale.pay.card@1`, `sale.pay.transfer@1`, `closing.request@1`, and `closing.confirm@1`

#### Scenario: A projection does not create an outcome
- **WHEN** a Next Best Action is projected for an open day that already has an OutcomeRun
- **THEN** no additional OutcomeRun row MUST be created
