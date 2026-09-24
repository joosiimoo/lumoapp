## ADDED Requirements

### Requirement: Export phrases are not a sale intent
The normalized phrases `exporta las ventas de hoy`, `exportar ventas`, `descargar excel`, and `descargar csv` MUST stay on the existing unsupported clarification path. They MUST NOT select a tool, MUST NOT call `operational_day.export_sales@1`, MUST NOT execute the daily sales export query, and MUST NOT run `operational_day.summary@1`, `sale.commit@1`, or a payment operation. The file MUST remain available only through `GET /api/v1/operational-days/{operational_day_ref}/sales-export`.

#### Scenario: Export utterance does not download
- **WHEN** the merchant sends `exporta las ventas de hoy`
- **THEN** the response MUST be the existing unsupported clarification, no export file MUST be returned, and no sale, audit, or outbox row MUST be written

#### Scenario: Download words are not payment or summary
- **WHEN** the merchant sends `descargar excel` or `descargar csv`
- **THEN** the orchestrator MUST NOT run `operational_day.summary@1`, `sale.commit@1`, a payment operation, or the export query
