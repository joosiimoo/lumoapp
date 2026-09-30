## MODIFIED Requirements

### Requirement: The file is one row per confirmed SaleItem
The export MUST include `SaleSession` rows with `status` `confirmed` or `voided` whose `operational_day_id` is the target day, their persisted `SaleItem` rows, and that sale's recorded `Payment`. `open` and `ready_to_charge` sessions MUST be excluded. The grain MUST be one row per `SaleItem`. A sale with several lines MUST produce several rows. The file MUST NOT collapse a sale into one row and MUST NOT aggregate products across sales. Both formats MUST use this column order: `business_date`, `sale_session_id`, `sale_status`, `sale_confirmed_at`, `sale_item_id`, `product_name`, `source_type`, `product_id`, `quantity`, `unit`, `catalog_unit_price`, `unit_price`, `price_override_reason`, `line_total`, `currency`, `payment_id`, `payment_method`, `payment_amount`. `sale_status` MUST be `confirmed` or `voided`. `product_name` MUST be `product_name_snapshot`. `quantity` MUST be `quantity_normalized` and `unit` MUST be `unit_normalized`. The file MUST NOT include `quantity_input`, `unit_input`, `operational_day_id`, `payment_status`, `created_at`, actor ids, policy ids, audit ids, outbox ids, idempotency keys, normalized aliases, or model text.

#### Scenario: Mixed sale
- **WHEN** one confirmed sale contains a catalog line and a free-concept line
- **THEN** the file MUST contain two rows, one for each `sale_item_id`, each with `sale_status` `confirmed`

#### Scenario: Active sales stay out
- **WHEN** the day has a confirmed sale and the tenant also has an `open` session and a `ready_to_charge` session
- **THEN** only the confirmed or voided sale's items MUST appear

#### Scenario: Voided sale is present with status
- **WHEN** a sale on the target day is `voided`
- **THEN** each of its `SaleItem` rows MUST appear with that `sale_session_id` and `sale_status` `voided`

### Requirement: Payment facts repeat and are not allocated
Every item row MUST repeat its sale's `payment_id`, `payment_method`, and full `payment_amount`. The amount MUST NOT be divided across lines. The file MUST NOT add a calculated payment-allocation column. `payment_amount` MUST NOT be summed down every row, because a multi-item sale repeats that payment. Valid operational gross reconciliation is `SUM(line_total)` across export rows whose `sale_status` is `confirmed` and, independently, `SUM(payment_amount)` once per distinct `payment_id` among those confirmed rows. Both MUST equal the operational-day live confirmed gross. Voided rows MUST be present for audit and MUST NOT be included in that reconciliation. `payment_method` MUST be the persisted `cash`, `card`, or `transfer`. Every confirmed or voided session on the day MUST have exactly one `recorded` payment and at least one `SaleItem`. If any such session does not, the response MUST be `500 INTERNAL_ERROR` with message `confirmed sales export is inconsistent` and MUST NOT include a partial file. A currency on a line or payment that differs from the business currency MUST be `422 VALIDATION_ERROR` and MUST NOT include a file.

#### Scenario: Cash, card, and transfer
- **WHEN** the day has one confirmed cash sale, one confirmed card sale, and one confirmed transfer sale
- **THEN** each row MUST show that sale's method and the full payment amount with `sale_status` `confirmed`

#### Scenario: Repeated payment
- **WHEN** one cash sale has two items and payment amount `47.00`
- **THEN** both rows MUST show the same `payment_id`, `payment_method` `cash`, and `payment_amount` `47.00`, and the file MUST NOT contain an allocated share of `47.00`

#### Scenario: Voided rows excluded from operational reconciliation
- **WHEN** the day has one confirmed sale of `24.50` and one voided sale of `22.50`
- **THEN** confirmed-only `SUM(line_total)` MUST equal `24.50` while voided rows remain in the file with `sale_status` `voided`

#### Scenario: Missing payment fails closed
- **WHEN** a confirmed or voided session on the day has no recorded payment
- **THEN** the response MUST be `500 INTERNAL_ERROR` and the body MUST NOT be a CSV or XLSX file
