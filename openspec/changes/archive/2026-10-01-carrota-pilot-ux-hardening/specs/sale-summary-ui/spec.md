## ADDED Requirements

### Requirement: Removed summary row shows Quitado
After a successful `sale.remove_item@1` for one row of a historical `sale_summary@1` card, the visible confirmation MUST include that row's `product_name`. That historical row MUST show `Quitado` and MUST NOT keep an enabled `Quitar`. Other rows on that same historical card MUST NOT keep an enabled `Quitar`. The next server `sale_summary@1` for any remaining lines MUST be the actionable card and MUST keep the server total. Flutter MUST NOT recompute that total and MUST NOT mark a remaining row `Quitado`. A failed remove MUST NOT show `Quitado` on the row.

#### Scenario: One of two summary lines is removed
- **WHEN** a `sale_summary@1` card lists Zanahoria and Galleta A and the merchant successfully removes Galleta A
- **THEN** the confirmation MUST include `Galleta A`, the historical Galleta A row MUST show `Quitado`, and the next summary MUST be the server payload for the remaining line

#### Scenario: Historical summary keeps no enabled remove
- **WHEN** that removal succeeds
- **THEN** the historical summary card MUST NOT show an enabled `Quitar` on Galleta A or on Zanahoria
