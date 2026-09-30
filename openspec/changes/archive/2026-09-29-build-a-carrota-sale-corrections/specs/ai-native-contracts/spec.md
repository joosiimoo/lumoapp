## ADDED Requirements

### Requirement: Correction tools and policies are registered
`ToolRegistry` MUST register `sale.remove_item@1` and `sale.void@1`. `GenerativeUIRegistry` MUST continue to register `sale_item_added@1`, `sale_summary@1`, and `sale_confirmed@1` with the correction actions defined in their UI specs. `PolicyEngine` MUST evaluate remove and void under sale/integrity policies that deny remove on non-active sessions, require a non-empty void reason on the void **mutate** path, and deny void mutate on closed days. For `sale.void@1` / `sale.void.confirm@1`, policy MUST allow evaluation to continue when the session is `confirmed` (mutate candidate on an open day) or already `voided` (stable read-back candidate). Policy MUST deny void when status is `open`, `ready_to_charge`, or any status other than `confirmed` or `voided`. Policy MUST NOT deny solely because status is already `voided`, so the workflow can return the non-mutating voided read-back. The LLM MUST NOT mutate domain state to remove or void outside those tools.

#### Scenario: Boot registers correction tools
- **WHEN** the application boots
- **THEN** `sale.remove_item@1` and `sale.void@1` MUST be present in `ToolRegistry`

#### Scenario: Closed-day void mutate is denied by policy
- **WHEN** policy evaluates `sale.void@1` for a still-`confirmed` sale on a closed OperationalDay
- **THEN** the decision MUST be deny and no mutation MUST occur

#### Scenario: Already voided is not a policy deny
- **WHEN** policy evaluates `sale.void@1` for a session whose status is already `voided`
- **THEN** policy MUST NOT deny solely for that status, and the workflow MUST be able to return the voided read-back without a second mutation

#### Scenario: Open session void is denied by policy
- **WHEN** policy evaluates `sale.void@1` for an `open` or `ready_to_charge` session
- **THEN** the decision MUST be deny and no mutation MUST occur
