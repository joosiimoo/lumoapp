## MODIFIED Requirements

### Requirement: Timeline events render from typed facts
The client MUST render only these compact feed items from server facts. Flutter MUST NOT sum sales, subtract cash, infer cash status, count day totals, recompute the business timezone, otherwise calculate a domain total, or generate transaction numbers. It MUST use server `business_date` and server `local_time`. A leading `$` on money strings is presentation decoration only. Unknown event types MUST be omitted. Event ids, source ids, and `limitation_code` MUST NOT be shown. Each item MUST show `local_time`, a short type label, one primary line, and secondary detail only when useful, without repeating the same values. Transaction references MUST be visually secondary support/audit identifiers, not the primary event content. Search-by-TRX MUST NOT be added.

`sale_confirmed` MUST use type label "Venta", a secondary line with `facts.transaction_number` when present, and primary sentence from `payment_method`: `cash` → `Venta en efectivo por ${amount}`, `card` → `Venta con tarjeta por ${amount}`, `transfer` → `Venta por transferencia de ${amount}`. Anular only when `actions` includes `sale.void.request@1`.

`sale_voided` MUST use type label "Venta anulada", a secondary reference line `"{transaction_number} · Anula {original_transaction_number}"` from facts when both are present, the same sale primary sentence mapping as `sale_confirmed`, secondary `Motivo: {void_reason}` when `void_reason` is present and non-empty, and MUST NOT show Anular.

`cash_count_recorded` MUST use type label "Conteo", primary `Efectivo contado ${counted_cash}`, and secondary including esperado and diferencia from `facts`. For `cash_status` `short` or `over`, the item MUST show status chip Faltante or Sobrante respectively. For `cash_status` `balanced`, the item MUST NOT show a standalone Cuadrado status chip or replacement balanced label. Flutter MUST NOT invent amounts. Cash-count items MUST NOT show a transaction number.

`daily_close_completed` MUST use type label "Cierre", a secondary line with `facts.transaction_number` when present, primary `Cierre completado · ${gross_sales_total} en ventas` from `facts.gross_sales_total` (MUST NOT use `sale_count` as the sales-total line), secondary cash status and diferencia from `facts`, and MUST show `facts.close_note` when present and non-empty. Optional `{sale_count} operaciones` MAY appear only as secondary detail that does not replace or duplicate the sales-total primary line.

#### Scenario: A confirmed sale uses the stored amount
- **WHEN** a `sale_confirmed` event has amount `120.00`, currency `MXN`, and `payment_method` `card`
- **THEN** the feed item MUST show type "Venta", time from `local_time`, and primary text including `120.00` and Tarjeta without Flutter recomputing the amount

#### Scenario: A confirmed sale shows TRX secondarily
- **WHEN** a `sale_confirmed` event includes `transaction_number` `TRX-000101`
- **THEN** the feed item MUST show that number as a secondary support line and MUST NOT make TRX the primary event content

#### Scenario: A voided sale shows reason once
- **WHEN** a `sale_voided` event has amount `22.50`, `payment_method` `cash`, and `void_reason` `cobro duplicado`
- **THEN** the feed item MUST show type "Venta anulada", primary including `22.50` and Efectivo, secondary `Motivo: cobro duplicado`, and MUST NOT show Anular

#### Scenario: A voided sale shows void and original TRX
- **WHEN** a `sale_voided` event has `transaction_number` `TRX-000105` and `original_transaction_number` `TRX-000101`
- **THEN** the feed item MUST show `TRX-000105 · Anula TRX-000101` from those facts

#### Scenario: A short count shows counted primary and expected/diff secondary
- **WHEN** a `cash_count_recorded` event has expected `820.00`, counted `805.00`, difference `-15.00`, and `cash_status` `short`
- **THEN** the feed item MUST show type "Conteo", primary including counted `805.00`, secondary including esperado `820.00` and diferencia `-15.00`, status Faltante, and MUST NOT show a TRX line

#### Scenario: A balanced count omits the Cuadrado chip
- **WHEN** a `cash_count_recorded` event has `cash_status` `balanced`
- **THEN** the feed item MUST show primary counted and secondary esperado/diferencia and MUST NOT show a standalone Cuadrado chip

#### Scenario: A close item uses the stored gross total
- **WHEN** a `daily_close_completed` event has `gross_sales_total` `22.50`, `sale_count` 1, `cash_status` `short`, and `cash_difference` `-2.50`
- **THEN** the feed item MUST show type "Cierre", primary including `22.50` en ventas, secondary cash status and diferencia, and MUST NOT use sale count as the sales-total primary line

#### Scenario: A close shows TRX secondarily
- **WHEN** a `daily_close_completed` event includes `transaction_number` `TRX-000110`
- **THEN** the feed item MUST show that number as a secondary support line

#### Scenario: A close note is shown when present
- **WHEN** a `daily_close_completed` event includes `close_note` `Faltaron dos billetes`
- **THEN** the feed item MUST show that note text once and MUST NOT invent additional explanation

#### Scenario: Facts are not duplicated unnecessarily
- **WHEN** any supported event is rendered
- **THEN** the same money or status value MUST NOT appear as both redundant primary and secondary restatement beyond the defined matrix
