# ADR-022: Daily sales export is a deterministic projection of operational truth

- Status: Accepted
- Date: 2026-09-23

## Decision

One OperationalDay's confirmed sales can be downloaded as CSV or XLSX. The file is a projection of rows that already exist. It does not create a reporting model, an export history, a job, a queue, object storage, or a new table.

The row grain is `SaleItem`. A row is included only when its `SaleSession` is `confirmed` and belongs to the requested day. Each row carries that session's one recorded `Payment` in full: `payment_id`, `payment_method`, and `payment_amount` repeat on every line of the sale. The payment is not allocated across lines and there is no allocation column. `SUM(payment_amount)` down every row is not the day's gross. Valid gross reconciliation is `SUM(line_total)` across exported rows, and, separately, `SUM(payment_amount)` once per distinct `payment_id`. Both equal the operational-day confirmed gross.

CSV and XLSX carry the same logical dataset, the same 17 columns, and the same order. The backend writes the file. The model does not author cells. There is no `operational_day.export_sales@1` tool and no generative UI download action.

Price history is the persisted `SaleItem`: `product_name_snapshot`, `catalog_unit_price_snapshot`, the charged `unit_price`, and `price_override_reason`. The export does not read `Product.current_price`, `Product.name`, or `ClosingSnapshot` lines.

Nothing new is persisted. There is no Alembic migration, no checksum column, and no object-storage pointer. Alembic head stays `0009_catalog_price_override`. The read does not write audit, outbox, or idempotency rows.

`sale_confirmed_at` is stored as UTC `timestamptz` and formatted with `operational_days.timezone`. An invalid day timezone fails the request. The domain does not hardcode `America/Mexico_City`.

Hoy offers the two downloads for `current` and opens the platform share sheet with the server bytes and server filename. `XFile.fromData` does not keep that filename on macOS, so the app writes the bytes to its temporary directory under the exact `Content-Disposition` filename and shares an `XFile` from that path. CSV is presented as `text/csv` so the `.csv` name is preserved. XLSX keeps its spreadsheet MIME type. `path_provider` is a direct dependency for that temporary directory. The temporary file is share transport, not export history or a merchant-chosen path, and the app does not request broad storage permission. A missing current day says there is no activity yet. An existing day with no confirmed sales still downloads a header-only file.

A repeated CSV of unchanged persisted data is byte-for-byte identical. A repeated XLSX matches in sheet count, sheet name, header, row count, row order, values, relevant cell types, and formatting. XLSX bytes are not required to match, and the export does not canonicalize the workbook ZIP to force them to match.

ADR-015 through ADR-021 are unchanged.

## Consequences

The merchant can take today's confirmed sales to Excel without a second source of truth. A multi-line sale repeats the payment, so a spreadsheet sum of the payment column overcounts unless payments are counted once. The file can be generated only while the confirmed-sale invariant holds: at least one item and exactly one recorded payment, in the business currency.
