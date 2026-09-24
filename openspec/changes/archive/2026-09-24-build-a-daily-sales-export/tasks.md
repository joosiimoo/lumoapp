## 1. Canonical export projection

- [x] 1.1 Add `backend/app/infrastructure/persistence/sales_export.py` with one `SELECT` for the tenant day: business name, currency, day timezone and `business_date`, confirmed `SaleItem` rows left-joined to the recorded `Payment`, plus a count of confirmed sessions missing an item or missing exactly one recorded payment. Order by `confirmed_at`, `sale_session_id`, `sale_items.created_at`, `sale_item_id`. No `FOR UPDATE` and no per-row query
- [x] 1.2 Add `backend/app/application/queries/export_daily_sales.py` to resolve `current` with `business_date_for` or a UUID, return plain rows and filename parts, and fail before serialization on a broken payment/item invariant (`500`) or a currency mismatch (`422`). Do not import FastAPI or `openpyxl`

## 2. CSV serializer

- [x] 2.1 Add `backend/app/infrastructure/export/daily_sales_csv.py` for UTF-8 BOM, comma, `QUOTE_MINIMAL`, CRLF, the 17-column header, two-decimal money, stripped quantity, blank optionals, and ISO `sale_confirmed_at` in the day timezone

## 3. XLSX serializer

- [x] 3.1 Add `openpyxl>=3.1,<4` to backend dependencies
- [x] 3.2 Add `backend/app/infrastructure/export/daily_sales_xlsx.py` for one `Ventas` sheet: bold header, frozen row, autofilter, fixed widths, numeric money and quantity, date and business-local datetime cells, no formulas or extra sheets. Workbook metadata may be set with a simple property assignment. Do not canonicalize the ZIP or require byte-identical XLSX output

## 4. HTTP endpoint and authorization

- [x] 4.1 Add `GET /api/v1/operational-days/{operational_day_ref}/sales-export` on the existing bearer tenant dependency. `format` is only `csv` or `xlsx`. Return `200` with the content types, `Content-Disposition`, and `Cache-Control: no-store`. Map a bad ref or format to `422`, and a missing or foreign day to `404 TENANT_SCOPE_VIOLATION` / `operational day not found`. Build the bytes before writing the body
- [x] 4.2 Do not add `export.create`, a `PolicyEngine` rule, or an idempotency requirement

## 5. Audit and outbox

- [x] 5.1 Keep the export free of audit, outbox, and idempotency writes. Do not add `operational_day.export_sales@1` or an export event

## 6. Hoy surface

- [x] 6.1 Replace the Hoy placeholder body with the caption and `Descargar Excel` / `Descargar CSV` actions that call `current`. On `404` for `current`, show `Todavía no hay actividad de hoy para exportar.` Leave the empty-day `200` file behavior unchanged. Leave `operational_day_summary@1` actions empty and do not register a generative UI download

## 7. Flutter download

- [x] 7.1 Add a typed download on the API client that returns bytes and the server filename, with auth and correlation id and without an idempotency key
- [x] 7.2 Add `share_plus` and `path_provider`. Stage the response bytes in the app temporary directory under the exact server filename, strip a trailing charset from the share MIME, and share an `XFile` from that path on iOS, Android, and macOS. Do not use `XFile.fromData`. Do not request storage permission, ask for a user path, or add web

## 8. Conversation guard

- [x] 8.1 Keep `exporta las ventas de hoy`, `exportar ventas`, `descargar excel`, and `descargar csv` on the unsupported path so they do not call the export query or a new tool

## 9. Regression tests

- [x] 9.1 Cover open-day CSV and XLSX, identical logical rows, byte-identical repeated CSV, logically equal repeated XLSX without a byte-identity assertion, normal catalog, override, free concept, mixed sale, repeated payment, cash/card/transfer, deterministic order, excluded open and ready-to-charge sessions, empty day headers, invalid format, quoting, accents, numeric XLSX money, sanitized filename, business-zone timestamp, and both gross reconciliations: `SUM(line_total)` and `SUM(payment_amount)` once per distinct `payment_id`
- [x] 9.2 Assert a later `Product.current_price` change does not affect the file, the export writes no domain/audit/outbox/idempotency rows, a missing payment returns `500` without a file, and a closed day is not read from `ClosingSnapshot`

## 10. RLS and API acceptance

- [x] 10.1 Assert another tenant's day and an unknown UUID share `404` / `operational day not found`, RLS hides the other tenant's lines, and `current` with no row uses that same response

## 11. ADR

- [x] 11.1 Add `docs/adr/ADR-022-daily-sales-export.md` with the design's decision record. Do not edit ADR-015 through ADR-021
