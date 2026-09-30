## MODIFIED Requirements

### Requirement: Timeline events render from typed facts
The client MUST render only these titles and bodies. `sale_confirmed` MUST use title "Venta registrada" and body `{amount} · {payment method}`, with `cash` shown as Efectivo, `card` as Tarjeta, and `transfer` as Transferencia. `sale_voided` MUST use title "Venta anulada" and body `{amount} · {payment method}` plus the server `void_reason` when present, with the same payment method labels. `cash_count_recorded` MUST use title "Conteo de efectivo" and MUST show esperado, contado, and diferencia from `facts`, plus the existing status chip Cuadrado, Faltante, or Sobrante for `balanced`, `short`, or `over`. `daily_close_completed` MUST use title "Cierre completado" and MUST show "Ventas registradas" from `facts.gross_sales_total`, the localized cash status, and the difference from `facts`. When `facts.close_note` is present and non-empty, the card MUST also show that server note text. That sales line MUST NOT use `sale_count`. The time caption MUST be the server `local_time`. The client MUST NOT render event ids, source ids, or `limitation_code`. An unknown event type MUST be omitted. Flutter MUST NOT sum sales, subtract cash, infer cash status, count day totals, recompute the business timezone, or otherwise calculate a domain total. It MUST use server `business_date` and server `local_time`.

#### Scenario: A card sale uses the stored amount
- **WHEN** a `sale_confirmed` event has amount `120.00`, currency `MXN`, and `payment_method` `card`
- **THEN** the card MUST show "Venta registrada" and "120.00 · Tarjeta" without Flutter recomputing the amount

#### Scenario: A voided sale uses Venta anulada
- **WHEN** a `sale_voided` event has amount `22.50`, `payment_method` `cash`, and `void_reason` `cobro duplicado`
- **THEN** the card MUST show title "Venta anulada" and MUST include `22.50`, Efectivo, and the reason without Flutter calculating totals

#### Scenario: A short count shows the stored difference
- **WHEN** a `cash_count_recorded` event has expected `820.00`, counted `805.00`, difference `-15.00`, and `cash_status` `short`
- **THEN** the card MUST show those three amounts and the chip Faltante

#### Scenario: A close card uses the stored gross total
- **WHEN** a `daily_close_completed` event has `gross_sales_total` `22.50`, `sale_count` 1, `cash_status` `short`, and `cash_difference` `-2.50`
- **THEN** the card MUST show "Ventas registradas 22.50", "Caja Faltante", and "Diferencia -2.50", and MUST NOT show the sale count as the sales line

#### Scenario: A close note is shown when present
- **WHEN** a `daily_close_completed` event includes `close_note` `Faltaron dos billetes`
- **THEN** the card MUST show that note text and MUST NOT invent additional explanation
