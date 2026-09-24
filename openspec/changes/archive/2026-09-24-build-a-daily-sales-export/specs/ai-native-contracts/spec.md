## ADDED Requirements

### Requirement: Daily sales export is not a tool or a model artifact
The daily sales file MUST be produced only by the deterministic HTTP read in `daily-sales-export`. `ToolRegistry` MUST NOT register `operational_day.export_sales@1` or any other export tool. `UiActionRegistry` MUST NOT register a download action. `GenerativeUIRegistry` MUST NOT register `export_ready_card`. No `LLMProvider` MUST generate export bytes, column names, product names, prices, reasons, quantities, or totals. The export query MUST NOT run inside the orchestrator.

#### Scenario: Export tool stays unregistered
- **WHEN** the application boots
- **THEN** `ToolRegistry` MUST report `operational_day.export_sales@1` as unregistered and the existing tool list MUST be unchanged

#### Scenario: Model output is not a file
- **WHEN** an interpreter returns text that looks like CSV or a workbook
- **THEN** that text MUST NOT be stored or returned as the sales export
