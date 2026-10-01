## ADDED Requirements

### Requirement: Export download remains server-authored with transaction columns
Hoy export actions MUST continue to download the server CSV/XLSX bytes and MUST NOT build transaction numbers on the device. The downloaded file MAY include additive `sale_transaction_number` and `void_transaction_number` columns authored by the backend. Flutter MUST NOT invent those columns or values. Download UX (Excel/CSV buttons, share sheet, temporary file) MUST otherwise remain unchanged. No general transaction-only export MUST be added.

#### Scenario: Client does not invent TRX columns
- **WHEN** the merchant taps Descargar CSV
- **THEN** any transaction reference columns in the file MUST come from the server body and Flutter MUST NOT synthesize TRX values
