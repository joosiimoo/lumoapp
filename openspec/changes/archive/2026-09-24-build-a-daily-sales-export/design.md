## Context

Carrota's operational file is one day's confirmed sales. Build A already persists that truth: a confirming `sale.commit@1` attaches a `SaleSession` to an `OperationalDay`, writes immutable `SaleItem` rows (catalog snapshot, charged price, optional override reason, or a free concept), and writes exactly one `Payment`. `UNIQUE (sales.payments.sale_session_id)` plus `status = recorded` is the Build A payment shape. `operational_day.summary@1` sums those payments for the day and does not write audit, outbox, or idempotency. `ClosingSnapshot` is close evidence, not the line source. Hoy is still a placeholder. The tool catalog already says export tools stay unregistered. There is no file route, no `openpyxl`, and no Flutter download package. Flutter targets are iOS, Android, and macOS.

PRD §7.11 and SRS RF-A-100–RF-A-105 describe a wider export (ranges, four XLSX sheets, persisted export evidence, `export.create`, temporary URLs). Architecture §10.3 allows a small export to be generated in process and treats CSV/XLSX as output adapters. This slice is the one-day in-process adapter. The wider reporting module stays deferred.

## Goals / Non-Goals

**Goals:**

- One synchronous file for one OperationalDay, open or closed, containing only confirmed sales that exist at request time.
- CSV and XLSX are the same logical dataset: one row per `SaleItem`, same order, same values.
- Historical prices come from the `SaleItem` snapshot. Payment facts repeat on each line of that sale and are not allocated.
- The merchant downloads today's file from Hoy without typing an id. The model does not author cells.

**Non-Goals:**

- See the proposal. In particular: no range export, no extra sheets, no footer, no export history, no new permission, no tool, no generative UI action, no migration.

## Decisions

### 1. API route

`GET /api/v1/operational-days/{operational_day_ref}/sales-export?format=csv|xlsx`

`operational_day_ref` is either a UUID or the exact token `current`. `current` resolves with the same clock and `business_date_for` rule as `operational_day.summary@1`: one UTC instant converted through `identity.businesses.timezone`. Hoy calls `current` only. A UUID addresses one persisted day, including a closed past day, and is how tests prove tenant isolation. A business date in the path is not accepted. There is no second summary endpoint and no `GET /api/v1/exports/*` job resource.

`format` is required and is the closed lowercase enum `csv` | `xlsx`. Missing, empty, differently cased, or any other value is `422 VALIDATION_ERROR`. A ref that is neither `current` nor a UUID is `422 VALIDATION_ERROR`.

Success is `200` with the bytes, after the whole file is built in memory. The handler does not start the body and then fail.

| Format | `Content-Type` |
| --- | --- |
| csv | `text/csv; charset=utf-8` |
| xlsx | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |

`Content-Disposition` is `attachment; filename="<server filename>"`. `Cache-Control` is `no-store`. The success body is not the JSON message envelope. Errors use the existing error envelope. No `Idempotency-Key`. `Authorization` and `X-Correlation-ID` follow the other `/api/v1` routes.

### 2. Tool and action

No tool. `ToolRegistry` already requires export tools to stay unregistered, and a tool result is JSON inside the orchestrator, which cannot carry this file without putting bytes where the model can rewrite them. `operational_day.export_sales@1` is not registered. `UiActionRegistry` stays the five existing ids. `POST /api/v1/lumo/actions` is not a download transport.

### 3. Canonical columns, in this order

1. `business_date`
2. `sale_session_id`
3. `sale_confirmed_at`
4. `sale_item_id`
5. `product_name`
6. `source_type`
7. `product_id`
8. `quantity`
9. `unit`
10. `catalog_unit_price`
11. `unit_price`
12. `price_override_reason`
13. `line_total`
14. `currency`
15. `payment_id`
16. `payment_method`
17. `payment_amount`

Sources:

- `business_date` is `operations.operational_days.business_date`.
- `product_name` is `product_name_snapshot`.
- `quantity` is `quantity_normalized`. `unit` is `unit_normalized`. `line_total` is `quantity_normalized * unit_price`, so the exported quantity is the one that reconciles. `quantity_input` and `unit_input` are not columns.
- `catalog_unit_price` is `catalog_unit_price_snapshot`.
- `unit_price`, `price_override_reason`, `line_total`, `source_type`, `product_id`, and `currency` are the `SaleItem` columns.
- `sale_confirmed_at` is `sale_sessions.confirmed_at`.
- `payment_id`, `payment_method`, and `payment_amount` are the sale's one `Payment` (`id`, `method`, `amount`).

Omitted on purpose: `operational_day_id` (constant for the file; the request already names the day), `payment_status` (Build A stores only `recorded`), `created_at` (sort key only), actor ids, conversation ids, normalized aliases, policy ids, audit ids, outbox ids, and idempotency keys. No Spanish display labels in the cells. `payment_method` stays `cash`, `card`, or `transfer`. `source_type` stays `catalog` or `free_concept`.

### 4. Price semantics

| Line | `catalog_unit_price` | `unit_price` | `price_override_reason` |
| --- | --- | --- | --- |
| Catalog, snapshot equals charged price | snapshot | charged price | empty |
| Catalog override | snapshot | charged price | persisted reason |
| `free_concept` | empty | explicit price | empty |

Empty means a blank CSV field and an empty XLSX cell, never the text `null`. The export does not read `Product.current_price` or `Product.name`. A later catalog edit does not change a past file.

### 5. Payment representation

Each item row repeats that sale's full `payment_id`, `payment_method`, and `payment_amount`. The amount is not divided across lines and is not recomputed. There is no calculated payment-allocation column. `payment_amount` must not be summed down every row: a multi-item sale repeats that payment. Valid gross reconciliation is two independent sums, and both must equal the operational-day confirmed gross: `SUM(line_total)` across export rows, and `SUM(payment_amount)` once per distinct `payment_id`.

Build A has at most one payment row per session. The export additionally requires every confirmed session on that day to have exactly one `recorded` payment and at least one `SaleItem`. If any confirmed session breaks that, the request fails with `500 INTERNAL_ERROR`, message `confirmed sales export is inconsistent`, and no file bytes. Mixed payment is not represented.

A line or payment currency that differs from `identity.businesses.currency` fails with `422 VALIDATION_ERROR` and no file, matching the summary read's currency check.

### 6. CSV

UTF-8 with BOM (`utf-8-sig`). Excel on Windows, and commonly on macOS, otherwise misreads `Café Orgánico` and `promoción del día`. Delimiter is comma, because the quoting scenario is defined for commas and SRS RF-A-103 requires a decimal point. Dialect is Python `csv.excel`: `QUOTE_MINIMAL`, quote `"`, internal quotes doubled, lineterminator `\r\n`, header included, file ends with CRLF. Mexican Excel often expects `;` and a decimal comma; that combination would change the required `20.00` amounts. XLSX is the Excel file. CSV is the RFC 4180 text twin.

Money columns are plain strings quantized to `0.01`: `20.00`, `27.00`. No currency symbol. Quantity is `format(value, "f")` with trailing zeros and a trailing dot stripped (`0.900000` → `0.9`, `1.000000` → `1`). `business_date` is `YYYY-MM-DD`. Blank cells are empty fields. Two CSV exports of the same unchanged day are byte-for-byte identical, because the application controls the entire serialization.

### 7. XLSX

True workbook via `openpyxl>=3.1,<4`, added to the backend dependencies. The domain and the application query do not import it. One sheet, named `Ventas`. Header row uses the same names, bold. Freeze pane `A2`. Auto-filter covers the header through the last data row, or `A1:Q1` when there are no data rows. No formulas, charts, pivots, macros, logos, or extra sheets. `line_total` is the stored number, not a formula.

Money and quantity cells are numeric, number format `0.00` for money and `0.######` for quantity. OOXML stores numbers as IEEE floats; the contract is that the value quantized back to cents equals the persisted decimal. Dates: `business_date` is a date cell `yyyy-mm-dd`. `sale_confirmed_at` is a naive datetime of the business-local wall time, format `yyyy-mm-dd hh:mm:ss`. Empty optionals are empty cells.

Column widths are fixed: business_date 14, sale_session_id 38, sale_confirmed_at 22, sale_item_id 38, product_name 28, source_type 16, product_id 38, quantity 12, unit 14, catalog_unit_price 20, unit_price 14, price_override_reason 36, line_total 14, currency 12, payment_id 38, payment_method 16, payment_amount 16.

For the same unchanged persisted day, two XLSX exports must have the same sheet count, sheet name, header, row count, row order, logical values, relevant cell types, and declared formatting. They do not need to be byte-identical. XLSX is a ZIP container, and fixing workbook metadata does not make openpyxl output reproducible. Workbook `created`, `modified`, and `lastModifiedBy` may be set to fixed values when that is a simple property assignment. That is not an acceptance criterion. The implementation must not add ZIP canonicalization, package post-processing, or a custom package writer in order to make the bytes match.

Rows only. No totals section. The canonical dataset stays one row per item. Carrota can sum `line_total` in Excel. A footer is not part of the file. Summing `payment_amount` down every row is not a valid gross.

### 8. Filename

`lumo-{slug}-ventas-{business_date}.csv` or `.xlsx`.

`slug` comes from `identity.businesses.name` in the export read: NFKD, strip combining marks, lowercase, replace every run outside `[a-z0-9]` with one hyphen, trim hyphens, cut to 40 characters, trim hyphens again. Empty result becomes `negocio`. The path segment, extension, and date are chosen by the server. The result is ASCII and cannot contain quotes, slashes, or `..`. Example: `lumo-carrota-ventas-2026-09-23.xlsx`. No UUID in the name. Open and closed days share this pattern; the name does not say the day is final.

### 9. Ordering

`sale_confirmed_at ASC`, `sale_session_id ASC`, `sale_items.created_at ASC`, `sale_item_id ASC`. The same order is the list both serializers receive. `created_at` is not a column.

### 10. Timezone

Stored `confirmed_at` stays a UTC `timestamptz`. The exported civil time uses `operational_days.timezone` (the IANA name copied onto the day), through `zoneinfo`. CSV is ISO 8601 with that offset and second precision, for example `2026-09-23T14:05:00-06:00`. XLSX stores that same wall clock without an offset, because a worksheet cell has no IANA zone. `business_date` is the day row's date, not the device clock and not a recomputation from `confirmed_at`. An invalid day timezone fails the request with `500` and no file. The domain does not hardcode `America/Mexico_City`.

### 11. Open day, empty day, missing day

Open and closed days both export. An open-day file is the confirmed snapshot at request time. Hoy's caption is `Incluye las ventas confirmadas de hoy.` It does not call the file a close.

An existing day with zero confirmed sales returns `200`, a header, and zero data rows in both formats. It is not `404`.

A missing day, another tenant's day, and `current` when this tenant has no row for today all return `404 TENANT_SCOPE_VIOLATION` with message `operational day not found`. The same code and message cover all three. The lookup is `business_id` from `TenantContext` plus the ref. RLS stays on. The client cannot learn that another tenant's id exists.

### 12. Read consistency

`get_tenant` already begins the request transaction when it sets `app.current_business_id`, so the export cannot raise isolation afterward. The file is one `SELECT` under that `READ COMMITTED` statement snapshot: the day row, business name, currency, and timezone, every confirmed item left-joined to its recorded payment, and a scalar count of confirmed sessions on that day that lack an item or lack exactly one recorded payment. No `FOR UPDATE`, no `LOCK TABLE`, no `SERIALIZABLE`. Confirmed items are immutable, so the statement cannot mix two versions of one line. A sale that commits after the statement starts is absent; the next download sees it. The request lifecycle may commit the session, and that commit must persist nothing: no audit, outbox, idempotency, or domain change.

### 13. Authorization

The route uses the existing bearer `TenantContext`. It ignores a client `business_id`. It does not add `export.create`, `operational_day.read`, or `sale.read`. Those strings are not an enforced grant table today; `operational_day.summary@1` is authorized the same way and only declares `sale.create` on the tool. This route is not a tool and does not call `PolicyEngine`. A future permission catalog should gate it with whatever grant covers the summary read.

### 14. Audit and outbox

No audit row and no outbox event. Summary and close-preparation reads are the precedent: significant day reads are not audited, and this slice must not invent a one-off audit or an `export_jobs` record. SRS RF-A-104 (requester, filters, checksum, persisted status) waits for an export-evidence slice. The existing access log may keep method, route, status, duration, and correlation id. It must not record file bytes or row payloads. No idempotency row.

### 15. Primary UI

Hoy, inside the existing 420px column. Two outline actions, `Descargar Excel` and `Descargar CSV`, using the current border, white fill, and type. They GET `current` with `format=xlsx` and `format=csv`. No metric hero, chart, product list, day picker, or close control. `404` on `current` shows `Todavía no hay actividad de hoy para exportar.` An existing day with zero confirmed sales is still `200` with a header and no data rows; that case does not use this sentence. Other failures show the envelope message. Inicio's `operational_day_summary@1` card stays as it is, with empty `actions`.

### 16. Flutter download

The typed client gains a download that returns bytes plus the `Content-Disposition` filename, sends `Authorization` and `X-Correlation-ID`, and does not send `Idempotency-Key` or parse the body as JSON. `XFile.fromData` does not preserve that filename on macOS: `share_plus` then names the staged file from the MIME type, and `text/csv; charset=utf-8` becomes `.bin`. The accepted share path writes the response bytes to the app temporary directory with `path_provider`, using the exact server filename, strips a trailing charset so CSV is presented as `text/csv`, and shares an `XFile` from that temporary path. The temporary file is transport for the share sheet, not a permanent export directory or export history. The merchant saves or opens the file from the sheet on iOS, Android, and macOS. No shared storage permission, no user path, no web target.

### 17. Generative UI

No new component, version, or action. `export_ready_card` stays unregistered. Download buttons are ordinary Hoy controls, not `action_id` posts.

### 18. Conversation

`exporta las ventas de hoy`, `exportar ventas`, `descargar excel`, and `descargar csv` stay on the existing unsupported path. They do not select a tool and do not run the export query. The file is only the HTTP read.

### 19. Row limit and totals

No row cap. One day is the bound. No footer and no totals sheet.

### 20. Migration

None. Head stays `0009_catalog_price_override`. No `export_jobs`, history, or checksum column. The feature reads tables that already exist.

### 21. ADR-022

Add `docs/adr/ADR-022-daily-sales-export.md`. Do not edit ADR-015 through ADR-021. The decision is: daily sales export is a deterministic projection of operational truth; row grain is `SaleItem`; source is confirmed `SaleSession` + `SaleItem` + the one `Payment`; CSV and XLSX share that logical dataset; CSV of an unchanged day is byte-for-byte identical; XLSX of an unchanged day matches in sheet, header, row count, order, values, cell types, and formatting, and is not required to be byte-identical; no ZIP canonicalization is added to force XLSX bytes to match; the backend writes the file; the model does not; nothing new is persisted; there is no object storage or job; price history is the sale snapshot; payment repeats in full on every line of the sale and is not allocated; gross reconciliation is `SUM(line_total)` and, separately, `SUM(payment_amount)` once per distinct `payment_id`; timestamps use the day's IANA zone; there is no audit or outbox row; Hoy downloads through the share sheet after staging the server bytes in the app temporary directory under the server filename.

### 22. Directory layout

- `backend/app/application/queries/export_daily_sales.py` — resolve the ref, run the one read, validate, return plain rows plus filename parts. No FastAPI and no `openpyxl`.
- `backend/app/infrastructure/persistence/sales_export.py` — the single SQL read, with `set_current_business_id`.
- `backend/app/infrastructure/export/daily_sales_csv.py` and `daily_sales_xlsx.py` — serializers. `openpyxl` stays here.
- `backend/app/api/routes/operational_days.py` — the GET route.
- `mobile/lib/features/hoy/hoy_page.dart` and a download method on the existing API client.

Domain models are unchanged. `sales-session-foundation` needs no delta: status, immutability, and one payment per session stay as they are. The export only reads them.

### 23. Reconciliation

An acceptance test checks two independent sums against `operational_day.summary` `gross_sales_total` for that day. The first is `SUM(line_total)` across export rows. The second is `SUM(payment_amount)` taken once per distinct `payment_id`. Summing `payment_amount` on every row is not that test. No payment-allocation column is added. `ClosingSnapshot.gross_sales_total` is not the export source; on a closed day both sums still match the live summary, which is what the snapshot copied at close.

## Risks / Trade-offs

- [Excel es-MX opens a comma/dot CSV as one column or as text] → XLSX is the merchant file; CSV stays RFC 4180 so accents, quoting, and `20.00` are specified once.
- [OOXML money is binary floating point] → write decimals, format `0.00`, and assert the cent-quantized cell value.
- [XLSX ZIP bytes differ between two openpyxl writes of the same rows] → accept logical workbook equality. Do not canonicalize the ZIP. CSV remains the byte-stable text copy.
- [Request `commit()` runs after a read] → the query only selects; tests show no new audit, outbox, idempotency, or changed sale rows.
- [`current` and the file are two moments if the day is created mid-request] → the file itself is one statement. A `404` because the day appeared a moment later succeeds on retry.
- [Open-day file looks final in Excel] → filename has the business date only; Hoy says the file includes confirmed sales of today.
- [SRS RF-A-104 wants a stored export record] → explicitly deferred. No silent checksum table.

## Migration Plan

Deploy the API with `openpyxl` and the Flutter app with `share_plus` and `path_provider`. No Alembic step and no backfill. Rollback is reverting the release. Existing sales, days, and closes are untouched.

## Open Questions

None. Sections 1–23 are the implementation contract.
