## ADDED Requirements

### Requirement: Onboarding tool and choice card
`ToolRegistry` MUST include `onboarding.apply@1` as a write tool that requires idempotency. Its handler MUST be an application workflow. The LLM interpreter MUST NOT insert or update business rows and MUST NOT decide `start_using_lumo`. `GenerativeUIRegistry` MUST include `onboarding_choice` version `1` for closed currency, timezone, and payment-method choices, and `onboarding_confirmation` version `1` showing name, currency, timezone, and enabled payment methods with an explicit `start_using_lumo` action. The outcome registry MUST NOT gain an onboarding outcome. `UiActionRegistry` MUST NOT gain a sale or closing action for this change. The confirmation action id MUST NOT be inferred from free text.

#### Scenario: Unregistered mutation
- **WHEN** an interpreter result attempts to write a business without `onboarding.apply@1`
- **THEN** no business row MUST be inserted

#### Scenario: Tool is registered
- **WHEN** `ToolRegistry` is queried for `onboarding.apply@1`
- **THEN** it MUST report a write tool that requires idempotency
