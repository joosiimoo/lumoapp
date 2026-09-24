## Why

Carrota writes the day's sales on paper and later types them into Excel. PRD §7.11 and SRS RF-A-100 through RF-A-103 require a CSV and XLSX extract of confirmed sales. This slice does that for one OperationalDay, as a faithful file of persisted rows, so the merchant can stop transcribing.

## What Changes

- Add a synchronous authenticated download of one OperationalDay's confirmed sales as CSV or XLSX. Both files carry the same logical rows: one row per persisted `SaleItem`.
- The backend builds the file from `SaleSession`, `SaleItem`, and `Payment`. It does not ask the model to write cells, and it does not read `Product.current_price` or `ClosingSnapshot` for line values.
- Hoy gains two download actions for the current business day. The merchant does not type an id. Chat does not gain an export tool or a file attachment.
- No migration, export history, outbox event, or audit row. Day-summary and close-preparation reads are already unaudited; this read follows them. SRS RF-A-104 evidence and the broader range/multi-sheet export stay out of this slice.

## Non-goals

- Week, month, date-range, multi-day, or multi-branch export.
- PDF, email, scheduled export, Google Sheets, cloud storage, background jobs, object storage, or export history.
- Accounting, SAT/CFDI, invoices, tax reports, bank reconciliation, inventory, purchases, suppliers, or receipt printing.
- Custom columns, saved templates, charts, pivots, macros, logos, or extra workbook sheets (`Detalle`, `Resumen`, `Metadatos`).
- A summary or footer row inside the file.
- A new permission, tool, generative UI action, or chat download card.
- Changing sale, payment, catalog, cash-count, or close behavior.

## Capabilities

### New Capabilities

- `daily-sales-export`: Deterministic one-day line export: query, CSV, XLSX, HTTP download, tenant safety, and reconciliation with the day's confirmed gross.
- `sales-export-ui`: Hoy download actions and the Flutter share of the server file. No generative UI contract.

### Modified Capabilities

- `operational-day-foundation`: An export may read an open or closed day and must not change the day or use `ClosingSnapshot` as the line source.
- `operational-day-summary-ui`: The summary card stays on Inicio with empty actions. Hoy may host the export panel and is no longer required to stay an empty placeholder.
- `persistence`: This slice adds no table, column, or `export_jobs` row. Head stays `0009_catalog_price_override`.
- `ai-native-contracts`: The file is not a tool and not a generative UI action. The model must not author export values. `operational_day.export_sales@1` stays unregistered.
- `conversational-sale-runtime`: Phrases such as "exporta las ventas de hoy" do not become a new intent or a tool call.

## Impact

- Backend: one GET route, a read-only projection, CSV and XLSX adapters. New dependency `openpyxl`. No Alembic revision.
- Mobile: Hoy replaces its placeholder body with two download actions. Dependencies `share_plus` and `path_provider`. The share stages server bytes in the app temporary directory under the server filename. iOS, Android, and macOS only.
- Docs: ADR-022. ADR-015 through ADR-021 stay unchanged.
- API shape: `GET /api/v1/operational-days/{operational_day_ref}/sales-export?format=csv|xlsx`.
