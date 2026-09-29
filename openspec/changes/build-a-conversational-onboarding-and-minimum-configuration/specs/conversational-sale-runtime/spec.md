## ADDED Requirements

### Requirement: Sales require completed onboarding
`sale.start@1`, `sale.add_item@1`, `sale.totalize@1`, and `sale.commit@1` MUST reject a business whose onboarding status is not `completed`, including `ready_to_complete` while status is still `in_progress`. For a completed business whose `enabled_payment_methods` is a non-null non-empty set, `sale.commit@1` MUST reject a payment method outside that set. A legacy `completed` business with `enabled_payment_methods IS NULL` MUST keep the existing commit acceptance of `cash`, `card`, and `transfer`. An empty array MUST NOT be treated as that legacy wildcard.

#### Scenario: Incomplete business cannot sell
- **WHEN** onboarding status is `in_progress` and the merchant starts a sale
- **THEN** the sale tool MUST reject the request and MUST NOT insert a sale session

#### Scenario: Enabled method enforced after new completion
- **WHEN** onboarding completed with enabled methods `cash` and `transfer` and the merchant commits with `card`
- **THEN** `sale.commit@1` MUST reject `card`
