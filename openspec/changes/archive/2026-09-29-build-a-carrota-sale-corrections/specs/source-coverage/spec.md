## ADDED Requirements

### Requirement: Void does not reverse observed sales coverage
Voiding a confirmed sale MUST NOT delete or update `operations.source_coverage_records`. If the day already has `sales` + `manual_capture` coverage from a prior confirm, that row MUST remain `observed` after void even when no confirmed sale remains. Coverage writes MUST still not run on `sale.void@1` or `sale.remove_item@1`.

#### Scenario: Coverage survives last-sale void
- **WHEN** a day had one confirmed sale that created sales coverage and that sale is voided
- **THEN** the sales coverage row MUST still exist with status `observed`

#### Scenario: Void is not a coverage write hook
- **WHEN** `sale.void@1` commits
- **THEN** no new coverage row MUST be inserted by the void path
