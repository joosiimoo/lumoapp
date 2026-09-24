## MODIFIED Requirements

### Requirement: Summary fits Inicio and does not build Hoy
The summary MUST appear in the existing Inicio conversation stream as an assistant artifact: unbubbled, Lumo-mark gutter, warm canvas, max-width 420px. Navigation, the four-tab shell, the composer, and the theme MUST be unchanged. The summary card MUST NOT add a chart, a weekly comparison, a dashboard layout, or a download action. `actions` MUST remain empty. Hoy MAY show the sales export panel from `sales-export-ui` and MUST NOT be required to stay an empty placeholder. Hoy MUST NOT become a daily-close screen, a chart, or a reporting dashboard because of the summary card.

#### Scenario: Ventas de hoy on Inicio
- **WHEN** the signed-in Carrota user submits `ventas de hoy`
- **THEN** the stream MUST show the user bubble and a Lumo-mark `operational_day_summary@1` card whose count and totals match the server payload, and the Hoy tab MUST NOT become a daily-close screen

#### Scenario: Summary card does not download
- **WHEN** `operational_day_summary@1` is composed for an open or closed day
- **THEN** `actions` MUST be empty and the card MUST NOT include a CSV or XLSX control
