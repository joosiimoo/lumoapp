## ADDED Requirements

### Requirement: Sales export reads an open or closed day
A sales export of an existing OperationalDay MUST be allowed when `status` is `open` and when `status` is `closed`. The export MUST NOT change `status`, MUST NOT insert an OperationalDay, and MUST NOT reopen a closed day. Line items MUST come from confirmed `SaleSession`, `SaleItem`, and `Payment` rows. `ClosingSnapshot` MUST NOT be the source of those lines. An open-day export MUST include only confirmed sales committed at request time.

#### Scenario: Open day export leaves the day open
- **WHEN** the merchant exports an open OperationalDay
- **THEN** `status` MUST remain `open` and the file MUST contain that day's confirmed item rows

#### Scenario: Closed day export is not the snapshot
- **WHEN** the merchant exports a closed OperationalDay whose live confirmed gross is `56.50`
- **THEN** the line items MUST come from the confirmed sales and the day MUST remain `closed`
