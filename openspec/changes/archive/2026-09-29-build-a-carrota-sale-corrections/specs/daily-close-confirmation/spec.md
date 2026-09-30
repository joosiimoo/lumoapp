## ADDED Requirements

### Requirement: Void can stale an outstanding close confirmation
When a sale void on an open day changes preparation figures that were embedded in an outstanding `closing.confirm@1` fingerprint, a later confirm attempt MUST fail as confirmation stale, MUST NOT write a ClosingSnapshot, and MUST require a fresh prepare/confirm path. The void itself MUST NOT close the day and MUST NOT rewrite an existing snapshot.

#### Scenario: Confirm after void is stale
- **WHEN** the merchant prepares close while balanced, then voids a cash sale that changes expected cash, then posts the old confirmation token
- **THEN** the confirm MUST be rejected as stale and the OperationalDay MUST remain `open`
