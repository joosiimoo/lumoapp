## ADDED Requirements

### Requirement: Mixed catalog and free-concept lines
An `open` `SaleSession` MUST accept catalog lines and free-concept lines together. Totalize MUST include every persisted line. A later confirmation MUST keep both. The session status machine MUST stay `open`, `ready_to_charge`, and `confirmed`.

#### Scenario: Second line joins the open session
- **WHEN** an open session already contains Zanahoria and the actor adds a free-concept line on the same `conversation_id`
- **THEN** both items MUST belong to that same session and the session MUST stay `open`

### Requirement: Free-concept clarification does not duplicate
A price or quantity clarification that completes a free concept MUST insert one `SaleItem`. It MUST NOT insert one item for the incomplete turn and another for the completing turn.

#### Scenario: One line after the price
- **WHEN** the actor clarifies the price of a pending free concept
- **THEN** the session MUST contain exactly one new line for that concept

### Requirement: Post-close commit guard is unchanged
A free-concept line MAY be added on a new `open` session after the operational day is `closed`, because add-item does not consult the day. `sale.commit@1` MUST still refuse to confirm that session into the closed day.

#### Scenario: Commit after close refuses
- **WHEN** the day is `closed` and a `ready_to_charge` session contains a free-concept line
- **THEN** commit MUST NOT record a `Payment` and MUST NOT set the session to `confirmed`
