## ADDED Requirements

### Requirement: Transaction numbers are server contracts only
AI-native contracts MUST document additive `transaction_number` fields on confirmed sale, voided sale, and completed close response/fact surfaces. The closed tool catalog MUST NOT gain a client allocation tool. The LLM MUST NOT invent or mutate transaction numbers. Allocation remains inside deterministic workflows for `sale.commit@1`, `sale.void@1`, and `closing.confirm@1`.

#### Scenario: No client allocation tool
- **WHEN** the registered tool catalog is inspected
- **THEN** it MUST NOT include a tool whose purpose is to mint or choose a transaction number
