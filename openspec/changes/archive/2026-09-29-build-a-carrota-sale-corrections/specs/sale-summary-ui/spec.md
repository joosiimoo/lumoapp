## ADDED Requirements

### Requirement: sale_summary@1 exposes per-line remove actions
While status is `ready_to_charge`, `sale_summary@1` MUST keep the three payment actions and MUST also expose one `sale.remove_item@1` action per persisted line, each token bound to that line's `sale_session_id` and `sale_item_id`. Payment action tokens on that card MUST bind the current persisted server `sale_revision` for the session. After a successful remove with remaining items, the composer MUST emit an updated `sale_summary@1` whose total equals the remaining lines and whose payment and remove actions are freshly minted for the advanced persisted `sale_revision`. After a remove that empties the session, the response MUST NOT keep payment actions for that empty sale. Flutter MUST render server totals only and MUST NOT recompute them or invent a client revision.

#### Scenario: Summary lists remove per line
- **WHEN** a two-item ready_to_charge summary is composed
- **THEN** `actions` MUST include the three pay actions plus two `sale.remove_item@1` actions

#### Scenario: Summary recomposes after remove with fresh pay actions
- **WHEN** one of two ready_to_charge lines is removed
- **THEN** the next UI MUST be `sale_summary@1` with one item, the server total of that item, and new pay action tokens whose `sale_revision` differs from the pre-remove tokens

#### Scenario: Empty summary path has no pay actions
- **WHEN** the last ready_to_charge line is removed
- **THEN** the response MUST NOT include `sale.pay.cash@1`, `sale.pay.card@1`, or `sale.pay.transfer@1`
