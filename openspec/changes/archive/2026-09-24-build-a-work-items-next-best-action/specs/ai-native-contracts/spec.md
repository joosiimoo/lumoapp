## ADDED Requirements

### Requirement: Next Best Action tool and component are registered
`ToolRegistry` MUST include `operational_day.next_best_action@1` as specified by `next-best-action`. `PolicyEngine` MUST include `NBA-001`. `GenerativeUIRegistry` MUST include `next_best_action` version `1`. `UiActionRegistry` MUST NOT gain an action id. `closing.reopen@1`, `operational_day.export_sales@1`, and `payment.resolve` MUST remain unregistered. The outcome definition registry MUST remain empty of `daily_close_ready@1`; the projection constant `outcome_type=daily_close_ready` MUST NOT insert an OutcomeRun.

#### Scenario: Boot catalog gains the read tool and the card
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `operational_day.next_best_action@1`, `GenerativeUIRegistry` MUST report `next_best_action` version `1`, and `UiActionRegistry` MUST still contain exactly `sale.pay.cash@1`, `sale.pay.card@1`, `sale.pay.transfer@1`, `closing.request@1`, and `closing.confirm@1`

#### Scenario: OutcomeRun stays absent
- **WHEN** a Next Best Action is projected for an open day
- **THEN** no OutcomeRun row MUST be created
