## MODIFIED Requirements

### Requirement: The file is one row per confirmed SaleItem
The export MUST include `SaleSession` rows with `status` `confirmed` or `voided` whose `operational_day_id` is the target day, their persisted `SaleItem` rows, and that sale's recorded `Payment`. `open` and `ready_to_charge` sessions MUST be excluded. The grain MUST be one row per `SaleItem`. A sale with several lines MUST produce several rows. The file MUST NOT collapse a sale into one row and MUST NOT aggregate products across sales. Both formats MUST use this column order: `business_date`, `sale_session_id`, `sale_transaction_number`, `void_transaction_number`, `sale_status`, `sale_confirmed_at`, `sale_item_id`, `product_name`, `source_type`, `product_id`, `quantity`, `unit`, `catalog_unit_price`, `unit_price`, `price_override_reason`, `line_total`, `currency`, `payment_id`, `payment_method`, `payment_amount`. `sale_status` MUST be `confirmed` or `voided`. `sale_transaction_number` MUST be the formatted sale `transaction_number`. For `confirmed` rows `void_transaction_number` MUST be blank. For `voided` rows `void_transaction_number` MUST be the formatted void number. A multi-item sale MUST repeat the same `sale_transaction_number` on every item row, and when voided MUST repeat the same `void_transaction_number` on every item row. `product_name` MUST be `product_name_snapshot`. `quantity` MUST be `quantity_normalized` and `unit` MUST be `unit_normalized`. The file MUST NOT include `quantity_input`, `unit_input`, `operational_day_id`, `payment_status`, `created_at`, actor ids, policy ids, audit ids, outbox ids, idempotency keys, normalized aliases, or model text. Existing technical id columns MUST remain.

#### Scenario: Mixed sale
- **WHEN** one confirmed sale contains a catalog line and a free-concept line
- **THEN** the file MUST contain two rows, one for each `sale_item_id`, each with `sale_status` `confirmed`

#### Scenario: Active sales stay out
- **WHEN** the day has a confirmed sale and the tenant also has an `open` session and a `ready_to_charge` session
- **THEN** only the confirmed or voided sale's items MUST appear

#### Scenario: Voided sale is present with status
- **WHEN** a sale on the target day is `voided`
- **THEN** each of its `SaleItem` rows MUST appear with that `sale_session_id` and `sale_status` `voided`

#### Scenario: Confirmed row has sale TRX only
- **WHEN** a confirmed sale has `transaction_number` `TRX-000101`
- **THEN** each item row MUST show `sale_transaction_number` `TRX-000101` and blank `void_transaction_number`

#### Scenario: Voided row has sale and void TRX
- **WHEN** a voided sale has sale number `TRX-000102` and void number `TRX-000105`
- **THEN** each item row MUST show `sale_transaction_number` `TRX-000102`, `void_transaction_number` `TRX-000105`, and `sale_status` `voided`

#### Scenario: Multi-item sale repeats references
- **WHEN** a voided sale has three SaleItems
- **THEN** all three rows MUST repeat the same `sale_transaction_number` and the same `void_transaction_number`

### Requirement: XLSX is one operational sheet
XLSX MUST be a real workbook with exactly one sheet named `Ventas`, the same header, and the same logical rows as CSV. The header MUST be bold, the freeze pane MUST be `A2`, and an autofilter MUST cover the used range. Column widths MUST be fixed at 14, 38, 18, 18, 22, 38, 28, 16, 38, 12, 14, 20, 14, 36, 14, 12, 38, 16, and 16 in column order. Money and quantity MUST be numeric cells. `business_date` MUST be a date cell. `sale_confirmed_at` MUST be a datetime cell of the business-local wall time. The sheet MUST NOT contain formulas, charts, pivots, macros, logos, a totals row, or another sheet. Two XLSX exports of the same unchanged persisted day MUST have the same sheet count, sheet name, header, row count, row order, logical values, relevant cell types, and declared formatting. They MUST NOT be required to be byte-identical. Workbook metadata MAY be fixed with a simple property assignment. That assignment MUST NOT be an acceptance criterion. The implementation MUST NOT add ZIP canonicalization, ZIP post-processing, or a custom package writer in order to make XLSX bytes match.

#### Scenario: Workbook opens
- **WHEN** the XLSX bytes are loaded
- **THEN** they MUST be a valid workbook whose only sheet is `Ventas` and whose header matches the CSV header

#### Scenario: Money stays numeric
- **WHEN** a line total is `27.00`
- **THEN** that XLSX cell MUST be numeric and MUST equal `27.00` when quantized to cents

#### Scenario: Same logical rows
- **WHEN** CSV and XLSX are requested for the same unchanged day
- **THEN** they MUST contain the same values in the same row order

#### Scenario: Repeated XLSX matches logically
- **WHEN** XLSX is exported twice for the same unchanged OperationalDay
- **THEN** both workbooks MUST match in sheet count, sheet name, header, row count, row order, logical values, cell types, and formatting, and the bytes MUST NOT be required to be identical
