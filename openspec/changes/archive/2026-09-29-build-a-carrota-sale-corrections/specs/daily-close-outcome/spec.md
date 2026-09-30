## ADDED Requirements

### Requirement: Void re-syncs open-day OutcomeRun and WorkItems
A successful `sale.void@1` on an open day MUST run the existing open Daily Close maintenance path in the same transaction so OutcomeRun readiness and open WorkItems reflect live confirmed aggregates and live cash difference. When a previously balanced / ready-to-close day is no longer balanced after void, `close_confirmation_required` MUST NOT remain as if Caja cuadrada were still true.

#### Scenario: Ready-to-close invalidates after void
- **WHEN** an open day is ready to close with balanced cash and a cash sale is voided so expected cash no longer matches counted cash
- **THEN** maintenance MUST update WorkItems / OutcomeRun for the new live cash status and MUST NOT leave the day presenting unchanged ready-to-close balanced state
