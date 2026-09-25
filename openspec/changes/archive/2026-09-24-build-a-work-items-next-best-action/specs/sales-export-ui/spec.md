## MODIFIED Requirements

### Requirement: Hoy offers today's two downloads
Hoy MUST keep a minimal export panel inside the existing max-width 420px column, below any next-best-action block. The panel MUST show the caption `Incluye las ventas confirmadas de hoy.` and two actions, `Descargar Excel` and `Descargar CSV`. Excel MUST request `GET /api/v1/operational-days/current/sales-export?format=xlsx`. CSV MUST request the same path with `format=csv`. The merchant MUST NOT type an OperationalDay id, a business date, or a filesystem path. The export panel MUST NOT show a chart, a product report, a day picker, totals computed on the device, or a close control. Styling MUST use the existing outline-button treatment. A `404` for `current` MUST show `Todavía no hay actividad de hoy para exportar.` An existing day with zero confirmed sales MUST still download as `200` with a header and zero data rows, and MUST NOT show that sentence. Any other error MUST show the server envelope message. The export requests MUST NOT create or resolve a WorkItem.

#### Scenario: Excel and CSV from Hoy
- **WHEN** the signed-in merchant opens Hoy and taps `Descargar Excel`, then `Descargar CSV`, and today has an OperationalDay
- **THEN** the app MUST request `current` twice, once with `format=xlsx` and once with `format=csv`, and MUST NOT send an id typed by the merchant

#### Scenario: No day yet
- **WHEN** `current` returns `404 TENANT_SCOPE_VIOLATION`
- **THEN** Hoy MUST show `Todavía no hay actividad de hoy para exportar.` and MUST NOT show a stack trace or a UUID

#### Scenario: Export does not sync WorkItems
- **WHEN** the merchant downloads CSV for the current day
- **THEN** that download MUST NOT insert or update a WorkItem

### Requirement: Download is not generative UI
`GenerativeUIRegistry` and `UiActionRegistry` MUST NOT gain an export component or a download action. `export_ready_card` MUST stay unregistered. `operational_day_summary@1` `actions` MUST stay empty. The Excel and CSV buttons MUST NOT post to `/api/v1/lumo/actions`.

#### Scenario: Summary card stays without a download
- **WHEN** Inicio renders `operational_day_summary@1`
- **THEN** that card MUST have no download action, and the export controls MUST exist only on Hoy
