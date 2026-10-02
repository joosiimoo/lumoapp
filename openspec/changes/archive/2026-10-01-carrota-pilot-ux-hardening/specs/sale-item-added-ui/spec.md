## ADDED Requirements

### Requirement: Removed item card names the product and shows Quitado
After a successful `sale.remove_item@1` posted from a `sale_item_added@1` card, the visible confirmation MUST include that card's `data.product_name` and MUST NOT substitute a name that is not on the card. When the server response includes a remaining count or total, the confirmation MUST show those server values and Flutter MUST NOT recompute them. The historical card MUST remain in the Inicio transcript, MUST show the label `Quitado`, and MUST NOT show an enabled `Quitar`. A failed or refused remove MUST leave that card without `Quitado` and MUST keep its remove control available when the day is open. This requirement MUST NOT add a Generative UI version, a backend field, or a Memoria row.

#### Scenario: Galleta A removal names the product
- **WHEN** the merchant successfully removes a `sale_item_added@1` card whose `product_name` is `Galleta A`
- **THEN** the confirmation MUST include `Galleta A` and that historical card MUST show `Quitado` without an enabled `Quitar`

#### Scenario: Failed remove does not mark Quitado
- **WHEN** `sale.remove_item@1` from that card fails or is refused
- **THEN** the card MUST NOT show `Quitado` and MUST still offer `Quitar` while the day is open
