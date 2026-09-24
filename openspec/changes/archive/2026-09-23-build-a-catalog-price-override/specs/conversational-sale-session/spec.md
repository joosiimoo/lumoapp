## ADDED Requirements

### Requirement: Override reason completes one session line
A catalog price-override reason that `catalog-price-override` allows to commit MUST insert one `SaleItem` on the open session for that interaction context, creating the session when none exists. It MUST NOT insert a line on the question turn and another on the reason turn. `sale.totalize@1` and `sale.commit@1` MUST keep their current session rules and MUST sum persisted `line_total` values. Cash, card, and transfer MUST confirm that session without a pricing branch. Commit into a closed operational day MUST still refuse.

#### Scenario: Reason then totalize
- **WHEN** a Carrota actor completes the Tomate override at `27.00` and then posts `totalizar`
- **THEN** the open session MUST contain that one Tomate line and the summary total MUST include `27.00`

#### Scenario: Question turn leaves no session
- **WHEN** no session exists and the actor posts `900gr tomate a 30`
- **THEN** no `SaleSession` MUST exist after that turn

### Requirement: A new sale replaces a pending override
If `catalog_price_override` is pending and the actor sends a complete sale utterance, that pending MUST be cleared and the new utterance MUST follow normal add-item rules. The pending text MUST NOT be stored as `price_override_reason`.

#### Scenario: Galleta replaces a pending Tomate override
- **WHEN** a Tomate override question is pending and the actor posts `2 galletas A`
- **THEN** no Tomate override line MUST exist and the Galleta utterance MUST be interpreted on its own
