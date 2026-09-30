## MODIFIED Requirements

### Requirement: Timeline events render from typed facts
The client MUST render only these titles and bodies. `sale_confirmed` MUST use title "Venta registrada" and body `{amount} · {payment method}`, with `cash` shown as Efectivo, `card` as Tarjeta, and `transfer` as Transferencia. `sale_voided` MUST use title "Venta anulada" and body `{amount} · {payment method}` plus the server `void_reason` when present, with the same payment method labels. `cash_count_recorded` MUST use title "Conteo de efectivo" and MUST show esperado, contado, and diferencia from `facts`, plus the existing status chip Cuadrado, Faltante, or Sobrante for `balanced`, `short`, or `over`. `daily_close_completed` MUST use title "Cierre completado" and MUST show "Ventas registradas" from `facts.gross_sales_total`, the localized cash status, and the difference from `facts`. That sales line MUST NOT use `sale_count`. The time caption MUST be the server `local_time`. The client MUST NOT render event ids, source ids, or `limitation_code`. An unknown event type MUST be omitted. Flutter MUST NOT sum sales, subtract cash, infer cash status, count day totals, recompute the business timezone, or otherwise calculate a domain total. It MUST use server `business_date` and server `local_time`.

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

### Requirement: Memoria shows a bounded factual timeline
`MemoriaPage` MUST replace the placeholder with a timeline of confirmed business events for the authenticated business. The screen MUST use canvas `#FCFAF4`, soft white cards, 24px radius, no hard border, and the existing soft shadow. The header MUST keep the Memoria eyebrow and the Instrument Serif title "Lo que Lumo recuerda". Body text MUST use Inter. Events MUST be grouped by `business_date` with typographic headers and without a vertical rail. The page MUST NOT add a composer, a search field, question chips, or the actions Corregir, Explicar, Olvidar, and Ver evidencia. It MUST NOT register a new `UiAction` id. It MUST NOT be a Generative UI component. Questions stay on Inicio. When a timeline event includes a server-authored `sale.void.request@1` action, Memoria MAY render secondary Anular and run the existing void confirmation path; Flutter MUST NOT invent Anular when `actions` is absent or empty.

#### Scenario: Memoria remains non-chat
- **WHEN** the merchant opens Memoria
- **THEN** the page MUST NOT show a composer or question chips

## ADDED Requirements

### Requirement: Timeline API may attach server-authored void request actions
`GET /api/v1/memory/events` MUST keep the existing event read fields (`event_id`, `event_type`, `business_date`, `occurred_at`, `source_type`, `source_entity_type`, `source_entity_id`, `facts`, plus `local_time`) and MAY add an optional `actions` array on each event. Each action object MUST be the generative UI action envelope (`action_id`, `option_id`, `context_token`, `idempotency_key`) plus a server-authored `conversation_id` that MUST equal the JWT `conversation_id` claim so the client can `POST /api/v1/lumo/actions` after reload. Tokens MUST reuse existing `typ=ui_action` infrastructure. This slice MUST NOT invent a second void mechanism or a new action id.

For a `sale_confirmed` event, the server MUST include exactly one `sale.void.request@1` action when and only when all of the following hold at response time:

1. The referenced `SaleSession.status` is `confirmed`
2. The sale’s `operational_day_id` is the tenant’s current OperationalDay
3. That OperationalDay `status` is `open`

Otherwise `actions` MUST be omitted or an empty list. `sale_voided`, `cash_count_recorded`, and `daily_close_completed` events MUST NOT include void actions. Flutter MUST treat presence of the action as eligibility and MUST NOT infer eligibility from facts, amounts, or local status.

#### Scenario: Open-day confirmed sale exposes Anular
- **WHEN** Memoria lists a `sale_confirmed` for a session that is still `confirmed` on the current open OperationalDay
- **THEN** that event’s `actions` MUST contain exactly one `sale.void.request@1` with a verifiable `context_token` and server `conversation_id`

#### Scenario: Already-voided sale does not expose Anular
- **WHEN** the session is `voided` and both `sale_confirmed` and `sale_voided` events exist
- **THEN** the `sale_confirmed` event MUST NOT include `sale.void.request@1` and the `sale_voided` event MUST NOT include void actions

#### Scenario: Closed-day confirmed sale does not expose Anular
- **WHEN** a `sale_confirmed` event belongs to a closed OperationalDay and the session is still `confirmed`
- **THEN** that event’s `actions` MUST be absent or empty

#### Scenario: Reload remints Memoria void actions
- **WHEN** the merchant restarts the app and reloads Memoria while the sale remains void-eligible
- **THEN** `GET /api/v1/memory/events` MUST again return `sale.void.request@1` with a fresh token and idempotency key for that event

### Requirement: Memoria Anular uses the existing void confirmation path
When Memoria renders Anular from a server-provided `sale.void.request@1`, tapping MUST post that action through `POST /api/v1/lumo/actions` using the server `conversation_id`, then show the existing explicit confirmation with server before/after impact and collect a non-empty reason before posting `sale.void.confirm@1`. Flutter MUST NOT calculate impact. After a successful void, Memoria MUST refresh so the original "Venta registrada" no longer exposes Anular and "Venta anulada" is visible.

#### Scenario: Memoria Anular posts void request token
- **WHEN** the merchant taps Anular on a Memoria "Venta registrada" card that includes `sale.void.request@1`
- **THEN** Flutter MUST post that action id and `context_token` with the server `conversation_id` and MUST NOT mint a client token

#### Scenario: History keeps both cards without Anular on the original
- **WHEN** a sale is voided from Memoria
- **THEN** the timeline MUST still show "Venta registrada" and "Venta anulada", and neither card MUST expose Anular
