## ADDED Requirements

### Requirement: Close confirmation presents transaction number subtly
`daily_close_confirmed@1` MUST include server `data.transaction_number` when the ClosingSnapshot has a sequence. Flutter MUST present it subtly (for example `Día cerrado · TRX-000110` or an equivalent secondary reference beside the existing confirmed-close treatment) without redesigning Inicio/Hoy and without generating numbers on the client.

#### Scenario: Confirmed close shows TRX
- **WHEN** the renderer receives `daily_close_confirmed@1` with `transaction_number` `TRX-000110`
- **THEN** it MUST show that number subtly with the close-confirmed treatment and MUST NOT invent a different number

#### Scenario: Unknown version still falls back
- **WHEN** the payload is `daily_close_confirmed` version `2`
- **THEN** Flutter MUST show `fallback_text` and MUST NOT execute actions
