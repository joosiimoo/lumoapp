## ADDED Requirements

### Requirement: Hoy offers today's two downloads
Hoy MUST replace its empty placeholder body with a minimal export panel inside the existing max-width 420px column. The panel MUST show the caption `Incluye las ventas confirmadas de hoy.` and two actions, `Descargar Excel` and `Descargar CSV`. Excel MUST request `GET /api/v1/operational-days/current/sales-export?format=xlsx`. CSV MUST request the same path with `format=csv`. The merchant MUST NOT type an OperationalDay id, a business date, or a filesystem path. The panel MUST NOT show a chart, a product report, a day picker, totals computed on the device, or a close control. Styling MUST use the existing outline-button treatment. A `404` for `current` MUST show `Todavía no hay actividad de hoy para exportar.` An existing day with zero confirmed sales MUST still download as `200` with a header and zero data rows, and MUST NOT show that sentence. Any other error MUST show the server envelope message.

#### Scenario: Excel and CSV from Hoy
- **WHEN** the signed-in merchant opens Hoy and taps `Descargar Excel`, then `Descargar CSV`, and today has an OperationalDay
- **THEN** the app MUST request `current` twice, once with `format=xlsx` and once with `format=csv`, and MUST NOT send an id typed by the merchant

#### Scenario: No day yet
- **WHEN** `current` returns `404 TENANT_SCOPE_VIOLATION`
- **THEN** Hoy MUST show `Todavía no hay actividad de hoy para exportar.` and MUST NOT show a stack trace or a UUID

### Requirement: Flutter shares the server file
The typed API client MUST download the bytes and the filename from `Content-Disposition`, attach `Authorization` and `X-Correlation-ID`, and MUST NOT send `Idempotency-Key` or decode a success body as JSON. After a `200`, Flutter MUST write those bytes to the app temporary directory under the exact server filename, using `path_provider`, and MUST open the platform share sheet through `share_plus` with an `XFile` whose path is that temporary file. The shared MIME type MUST be the response media type without a trailing charset parameter. CSV MUST be presented as `text/csv` and MUST keep a `.csv` filename. XLSX MUST be presented as `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` and MUST keep an `.xlsx` filename. Staging MUST NOT use `XFile.fromData`, because that constructor does not preserve the server filename on macOS and `share_plus` then names the file from the MIME type. The temporary file is a share transport detail and MUST NOT be a permanent export directory, an export history, or business persistence. The app MUST NOT request broad storage permission, MUST NOT ask the merchant for a filesystem path, and MUST NOT add a web target. Flutter MUST NOT build the CSV or XLSX itself and MUST NOT recalculate line totals.

#### Scenario: Share sheet receives the server CSV filename
- **WHEN** the server returns `lumo-carrota-ventas-2026-09-23.csv` with `Content-Type` `text/csv; charset=utf-8`
- **THEN** the shared file MUST use that filename, the bytes MUST be the response body, and the presented MIME type MUST be `text/csv`

#### Scenario: Share sheet receives the server Excel filename
- **WHEN** the server returns `lumo-carrota-ventas-2026-09-23.xlsx`
- **THEN** the shared file MUST use that filename and the XLSX MIME type, and the bytes MUST be the response body

#### Scenario: Client does not author the workbook
- **WHEN** the merchant taps `Descargar Excel`
- **THEN** the workbook MUST be the server bytes and Flutter MUST NOT write cells or sum money

### Requirement: Download is not generative UI
`GenerativeUIRegistry` and `UiActionRegistry` MUST NOT gain an export component or a download action. `export_ready_card` MUST stay unregistered. `operational_day_summary@1` `actions` MUST stay empty. The Hoy buttons MUST NOT post to `/api/v1/lumo/actions`.

#### Scenario: Summary card stays without a download
- **WHEN** Inicio renders `operational_day_summary@1`
- **THEN** that card MUST have no download action, and the export controls MUST exist only on Hoy
