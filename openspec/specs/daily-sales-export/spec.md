# daily-sales-export Specification

## Purpose

Deterministic download of one OperationalDay's confirmed sales as CSV or XLSX. One row is one confirmed SaleItem. The backend writes the file from persisted sale, item, and payment rows. The export adds no reporting storage.

## Requirements
### Requirement: One OperationalDay downloads as CSV or XLSX
The API MUST expose `GET /api/v1/operational-days/{operational_day_ref}/sales-export`. `format` MUST be the query value `csv` or `xlsx`. The ref MUST be a UUID or the exact token `current`. `current` MUST resolve to today's business date with the same UTC clock and `identity.businesses.timezone` rule as `operational_day.summary@1`, and MUST NOT use the device timezone. A successful response MUST be `200`, `Cache-Control: no-store`, and `Content-Disposition: attachment` with the server filename. CSV `Content-Type` MUST be `text/csv; charset=utf-8`. XLSX `Content-Type` MUST be `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`. The body MUST be the finished file, not the conversational JSON envelope. Missing, empty, differently cased, or any other `format` MUST be `422 VALIDATION_ERROR`. A ref that is neither `current` nor a UUID MUST be `422 VALIDATION_ERROR`. The route MUST NOT require `Idempotency-Key`.

#### Scenario: Open day CSV
- **WHEN** an authenticated merchant exports `format=csv` for an open OperationalDay that has confirmed sales
- **THEN** the response MUST be `200` with `Content-Type` `text/csv; charset=utf-8` and a CSV body of those confirmed lines

#### Scenario: Same day XLSX
- **WHEN** the same day is exported with `format=xlsx`
- **THEN** the response MUST be `200` with the XLSX content type and a workbook of the same logical rows

#### Scenario: Invalid format
- **WHEN** `format` is omitted, `CSV`, `pdf`, or any value other than `csv` or `xlsx`
- **THEN** the response MUST be `422 VALIDATION_ERROR` and MUST NOT return a file

### Requirement: The file is one row per confirmed SaleItem
The export MUST include only `SaleSession` rows with `status=confirmed` whose `operational_day_id` is the target day, their persisted `SaleItem` rows, and that sale's recorded `Payment`. `open` and `ready_to_charge` sessions MUST be excluded. The grain MUST be one row per `SaleItem`. A sale with several lines MUST produce several rows. The file MUST NOT collapse a sale into one row and MUST NOT aggregate products across sales. Both formats MUST use this column order: `business_date`, `sale_session_id`, `sale_confirmed_at`, `sale_item_id`, `product_name`, `source_type`, `product_id`, `quantity`, `unit`, `catalog_unit_price`, `unit_price`, `price_override_reason`, `line_total`, `currency`, `payment_id`, `payment_method`, `payment_amount`. `product_name` MUST be `product_name_snapshot`. `quantity` MUST be `quantity_normalized` and `unit` MUST be `unit_normalized`. The file MUST NOT include `quantity_input`, `unit_input`, `operational_day_id`, `payment_status`, `created_at`, actor ids, policy ids, audit ids, outbox ids, idempotency keys, normalized aliases, or model text.

#### Scenario: Mixed sale
- **WHEN** one confirmed sale contains a catalog line and a free-concept line
- **THEN** the file MUST contain two rows, one for each `sale_item_id`

#### Scenario: Active sales stay out
- **WHEN** the day has a confirmed sale and the tenant also has an `open` session and a `ready_to_charge` session
- **THEN** only the confirmed sale's items MUST appear

#### Scenario: Confirmed sale is present
- **WHEN** a sale is `confirmed` on the target day
- **THEN** each of its `SaleItem` rows MUST appear with that `sale_session_id`

### Requirement: Prices come from the SaleItem snapshot
A normal catalog line MUST export `catalog_unit_price` equal to `catalog_unit_price_snapshot`, `unit_price` equal to the charged price, and a blank `price_override_reason`. A catalog override MUST export the snapshot, the charged price, and the persisted reason, and `source_type` MUST remain `catalog`. A free concept MUST export a blank `catalog_unit_price`, a blank `price_override_reason`, the explicit `unit_price`, a blank `product_id`, and `source_type` `free_concept`. Blank MUST be an empty CSV field and an empty XLSX cell, not the text `null`. The export MUST NOT read `Product.current_price` or `Product.name`.

#### Scenario: Normal catalog line
- **WHEN** a catalog line was charged at its snapshot price
- **THEN** `catalog_unit_price` MUST equal `unit_price` and `price_override_reason` MUST be blank

#### Scenario: Catalog override
- **WHEN** a catalog line has snapshot `20.00`, charged `unit_price` `30.00`, and reason `promoción del día`
- **THEN** the row MUST show those three values and `source_type` `catalog`

#### Scenario: Free concept
- **WHEN** a free-concept line has an explicit price and a null snapshot
- **THEN** `catalog_unit_price` and `price_override_reason` MUST be blank, `product_id` MUST be blank, and `source_type` MUST be `free_concept`

#### Scenario: Later catalog price does not rewrite history
- **WHEN** `Product.current_price` changes after the sale was confirmed and the day is exported
- **THEN** `catalog_unit_price` and `product_name` MUST still be the `SaleItem` snapshot values

### Requirement: Payment facts repeat and are not allocated
Every item row MUST repeat its sale's `payment_id`, `payment_method`, and full `payment_amount`. The amount MUST NOT be divided across lines. The file MUST NOT add a calculated payment-allocation column. `payment_amount` MUST NOT be summed down every row, because a multi-item sale repeats that payment. Valid gross reconciliation is `SUM(line_total)` across export rows and, independently, `SUM(payment_amount)` once per distinct `payment_id`. Both MUST equal the operational-day confirmed gross. `payment_method` MUST be the persisted `cash`, `card`, or `transfer`. Every confirmed session on the day MUST have exactly one `recorded` payment and at least one `SaleItem`. If any confirmed session does not, the response MUST be `500 INTERNAL_ERROR` with message `confirmed sales export is inconsistent` and MUST NOT include a partial file. A currency on a line or payment that differs from the business currency MUST be `422 VALIDATION_ERROR` and MUST NOT include a file.

#### Scenario: Cash, card, and transfer
- **WHEN** the day has one confirmed cash sale, one confirmed card sale, and one confirmed transfer sale
- **THEN** each row MUST show that sale's method and the full payment amount

#### Scenario: Repeated payment
- **WHEN** one cash sale has two items and payment amount `47.00`
- **THEN** both rows MUST show the same `payment_id`, `payment_method` `cash`, and `payment_amount` `47.00`, and the file MUST NOT contain an allocated share of `47.00`

#### Scenario: Missing payment fails closed
- **WHEN** a confirmed session on the day has no recorded payment
- **THEN** the response MUST be `500 INTERNAL_ERROR` and the body MUST NOT be a CSV or XLSX file

### Requirement: CSV is UTF-8 RFC 4180 text
CSV MUST be UTF-8 with a leading BOM, comma-separated, using `"` as the quote character, doubling internal quotes, and `\r\n` line endings including after the last line. The header row MUST always be present. Money MUST be dot-decimal strings with two places and no currency symbol. Quantity MUST be a plain decimal without an exponent and without trailing zeros. `business_date` MUST be `YYYY-MM-DD`. Fields that contain a comma, quote, or newline MUST be quoted. Two CSV exports of the same unchanged persisted day MUST be byte-for-byte identical.

#### Scenario: Accents survive
- **WHEN** a row contains `Café Orgánico` and `promoción del día`
- **THEN** the CSV bytes MUST start with the UTF-8 BOM and MUST decode to those exact strings

#### Scenario: Quoting
- **WHEN** a product name or reason contains a comma, a double quote, or a newline
- **THEN** that field MUST be wrapped in double quotes and each internal quote MUST be doubled

#### Scenario: Unchanged day CSV is byte-identical
- **WHEN** CSV is exported twice for the same unchanged OperationalDay
- **THEN** the two response bodies MUST be byte-for-byte identical

### Requirement: XLSX is one operational sheet
XLSX MUST be a real workbook with exactly one sheet named `Ventas`, the same header, and the same logical rows as CSV. The header MUST be bold, the freeze pane MUST be `A2`, and an autofilter MUST cover the used range. Column widths MUST be fixed at 14, 38, 22, 38, 28, 16, 38, 12, 14, 20, 14, 36, 14, 12, 38, 16, and 16 in column order. Money and quantity MUST be numeric cells. `business_date` MUST be a date cell. `sale_confirmed_at` MUST be a datetime cell of the business-local wall time. The sheet MUST NOT contain formulas, charts, pivots, macros, logos, a totals row, or another sheet. Two XLSX exports of the same unchanged persisted day MUST have the same sheet count, sheet name, header, row count, row order, logical values, relevant cell types, and declared formatting. They MUST NOT be required to be byte-identical. Workbook metadata MAY be fixed with a simple property assignment. That assignment MUST NOT be an acceptance criterion. The implementation MUST NOT add ZIP canonicalization, ZIP post-processing, or a custom package writer in order to make XLSX bytes match.

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

### Requirement: Filename and timestamp are server-owned
The filename MUST be `lumo-{slug}-ventas-{business_date}.csv` or `.xlsx`. `slug` MUST be derived from the business name by ASCII folding, lowercasing, collapsing non-alphanumeric runs to a single hyphen, trimming, and cutting to 40 characters, or `negocio` when nothing remains. The filename MUST NOT contain a UUID, a slash, `..`, or a quote. `sale_confirmed_at` in CSV MUST be ISO 8601 with second precision and the offset of `operational_days.timezone`. The XLSX datetime MUST be that same wall clock. `business_date` MUST be the day row's date. An invalid day timezone MUST fail with `500` and no file.

#### Scenario: Carrota filename
- **WHEN** the business name is `Carrota` and the business date is `2026-09-23`
- **THEN** the CSV filename MUST be `lumo-carrota-ventas-2026-09-23.csv`

#### Scenario: Unsafe name is folded
- **WHEN** the business name contains spaces, accents, or path characters
- **THEN** the filename slug MUST be a single safe ASCII token with no path separator

#### Scenario: Business zone formats the instant
- **WHEN** `confirmed_at` is `2026-09-23T20:05:00Z` and the day timezone is `America/Mexico_City`
- **THEN** the CSV timestamp MUST be `2026-09-23T14:05:00-06:00` and the XLSX wall time MUST be `2026-09-23 14:05:00`

### Requirement: Order and snapshot are deterministic
Rows MUST be ordered by `sale_confirmed_at` ascending, then `sale_session_id` ascending, then `SaleItem.created_at` ascending, then `sale_item_id` ascending. The export MUST load the day and its lines in one SQL statement on the request's existing `READ COMMITTED` transaction, without `FOR UPDATE`, `LOCK TABLE`, `SERIALIZABLE`, a per-row query, or a row cap. There is no maximum row count for one day. The serializers MUST receive that list and MUST NOT query again. The export MUST NOT write.

#### Scenario: Several sales
- **WHEN** two confirmed sales exist and the earlier one has two items
- **THEN** CSV and XLSX MUST list the earlier sale's items first, in `created_at` then `sale_item_id` order, and then the later sale

### Requirement: Open and empty days still download
Export MUST be allowed for `status=open` and `status=closed`. It MUST NOT change `status`. An existing day with zero confirmed sales MUST return `200` with a header and zero data rows in both formats. A day that does not exist for this tenant, another tenant's day, and `current` when today has no row MUST all return `404 TENANT_SCOPE_VIOLATION` with message `operational day not found`.

#### Scenario: Open day is not final
- **WHEN** the OperationalDay is `open` and has confirmed sales
- **THEN** the export MUST succeed and MUST include only the confirmed sales persisted at that request

#### Scenario: Closed day
- **WHEN** the OperationalDay is `closed`
- **THEN** the export MUST succeed and MUST NOT read line items from `ClosingSnapshot`

#### Scenario: Empty day
- **WHEN** the OperationalDay exists and has no confirmed sales
- **THEN** both formats MUST return `200` with the header and no data rows

#### Scenario: Missing or foreign day
- **WHEN** the UUID does not exist, belongs to another business, or `current` has no OperationalDay
- **THEN** the response MUST be `404 TENANT_SCOPE_VIOLATION` with message `operational day not found`

### Requirement: Export is read-only and reconciles
The request MUST NOT insert, update, or delete a sale, payment, day, audit row, outbox row, or idempotency row. It MUST NOT call an LLM. Cell values MUST come from the database rows. `SUM(line_total)` across export rows MUST equal that day's confirmed gross sales total from the live payment aggregate. `SUM(payment_amount)` once per distinct `payment_id` MUST equal the same total. Summing `payment_amount` on every row MUST NOT be treated as that gross. The file MUST NOT add a totals row or a payment-allocation column.

#### Scenario: No side effects
- **WHEN** a successful export completes
- **THEN** sale, payment, and day rows MUST be unchanged, and no audit, outbox, or idempotency row MUST have been written for the export

#### Scenario: Line totals match the day
- **WHEN** the day's confirmed payments sum to `90.50` and one of those sales has two item rows
- **THEN** `SUM(line_total)` MUST be `90.50`, `SUM(payment_amount)` once per distinct `payment_id` MUST be `90.50`, and the sum of `payment_amount` down every row MUST be greater than `90.50`

#### Scenario: Model does not author cells
- **WHEN** the export runs
- **THEN** product names, prices, reasons, and totals MUST be the persisted values and MUST NOT be produced by model output
