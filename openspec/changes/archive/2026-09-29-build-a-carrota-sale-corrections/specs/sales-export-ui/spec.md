## MODIFIED Requirements

### Requirement: Hoy offers today's two downloads
Hoy MUST keep a minimal export panel inside the existing max-width 420px column, below the structured daily summary cards from `business-stream`. The panel MUST show a caption that today's download includes confirmed and voided sales with explicit status, and that operational totals elsewhere exclude voided sales. It MUST keep two actions, `Descargar Excel` and `Descargar CSV`. Excel MUST request `GET /api/v1/operational-days/current/sales-export?format=xlsx`. CSV MUST request the same path with `format=csv`. The merchant MUST NOT type an OperationalDay id, a business date, or a filesystem path. The export panel MUST NOT show a chart, a product report, a day picker, totals computed on the device, or a close control. Styling MUST use the existing outline-button treatment. A `404` for `current` MUST show `Todavía no hay actividad de hoy para exportar.` An existing day with zero confirmed or voided sales MUST still download as `200` with a header and zero data rows, and MUST NOT show that sentence. Any other error MUST show the server envelope message. The export requests MUST NOT create or resolve a conversation turn.

#### Scenario: Caption mentions voided status
- **WHEN** Hoy renders the export panel
- **THEN** the caption MUST state that voided sales can appear with explicit status and MUST NOT claim the file is only live confirmed sales

#### Scenario: Excel and CSV still hit current
- **WHEN** the merchant taps Excel or CSV
- **THEN** Flutter MUST request `operational-days/current/sales-export` with the matching format
