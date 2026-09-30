## MODIFIED Requirements

### Requirement: Memoria shows a bounded factual timeline
`MemoriaPage` MUST show a compact chronological activity feed of confirmed business events for the authenticated business. The screen MUST use canvas `#FCFAF4`, forest-green accents, and restrained type chips. For each `business_date` group, the page MUST render one shared white Activity surface (not a stack of independent event cards) that includes an `ACTIVIDAD` label and the group's events as a vertical timeline: one small green circular node per event and a thin subtle vertical connector between nodes that stops at the first and last event. Events MUST NOT be separated by horizontal divider widgets. Events MUST NOT receive independent rounded-card chrome, per-row shadows, or nested card containers. The page header MUST keep the Memoria eyebrow and the Instrument Serif title "Lo que Lumo recuerda". Body text MUST use Inter. Events MUST be grouped by `business_date` with typographic date labels (`Hoy` / `Ayer` / calendar). The page MUST NOT add a composer, a search field, question chips, suggested memory questions, patterns observed, calculated insights, inventory entries, alerts, price-history features not already live, authorization codes, analytics/comparisons, or the actions Corregir, Explicar, Olvidar, and Ver evidencia. It MUST NOT register a new `UiAction` id. It MUST NOT be a Generative UI component. Questions stay on Inicio. When a feed item includes a server-authored `sale.void.request@1` action, Memoria MAY render secondary Anular (right-aligned on the time/chip line when layout allows) and run the existing void confirmation path; Flutter MUST NOT invent Anular when `actions` is absent or empty.

#### Scenario: Memoria remains non-chat
- **WHEN** the merchant opens Memoria
- **THEN** the page MUST NOT show a composer, search field, or question chips

#### Scenario: The placeholder is gone
- **WHEN** the merchant opens Memoria after at least one business event exists
- **THEN** the page MUST show that event as a timeline row inside a shared Activity surface and MUST NOT show "La memoria factual se habilitará cuando existan eventos confirmados."

#### Scenario: Date groups use one Activity timeline surface
- **WHEN** a date group has two or more events
- **THEN** those events MUST appear as timeline rows inside one shared white container labeled ACTIVIDAD, MUST each show a green timeline node, MUST connect with a vertical line between nodes, and MUST NOT render horizontal dividers between events or separate rounded cards

#### Scenario: Single-event group has a node without a broken connector
- **WHEN** a date group has exactly one event
- **THEN** that event MUST show one timeline node and MUST NOT require connector segments above or below

#### Scenario: Unsupported Lovable features stay out
- **WHEN** the merchant opens Memoria
- **THEN** the page MUST NOT show Ver evidencia, Corregir, Olvidar, Explicar, memory search, suggested memory questions, patterns, or calculated insights

### Requirement: Timeline events render from typed facts
The client MUST render only these compact feed items from server facts. Flutter MUST NOT sum sales, subtract cash, infer cash status, count day totals, recompute the business timezone, or otherwise calculate a domain total. It MUST use server `business_date` and server `local_time`. A leading `$` on money strings is presentation decoration only. Unknown event types MUST be omitted. Event ids, source ids, and `limitation_code` MUST NOT be shown. Each item MUST show `local_time`, a short type label, one primary line, and secondary detail only when useful, without repeating the same values.

`sale_confirmed` MUST use type label "Venta" and primary sentence from `payment_method`: `cash` → `Venta en efectivo por ${amount}`, `card` → `Venta con tarjeta por ${amount}`, `transfer` → `Venta por transferencia de ${amount}`. Anular only when `actions` includes `sale.void.request@1`.

`sale_voided` MUST use type label "Venta anulada", the same sale primary sentence mapping as `sale_confirmed`, secondary `Motivo: {void_reason}` when `void_reason` is present and non-empty, and MUST NOT show Anular.

`cash_count_recorded` MUST use type label "Conteo", primary `Efectivo contado ${counted_cash}`, and secondary including esperado and diferencia from `facts`. For `cash_status` `short` or `over`, the item MUST show status chip Faltante or Sobrante respectively. For `cash_status` `balanced`, the item MUST NOT show a standalone Cuadrado status chip or replacement balanced label. Flutter MUST NOT invent amounts.

`daily_close_completed` MUST use type label "Cierre", primary `Cierre completado · ${gross_sales_total} en ventas` from `facts.gross_sales_total` (MUST NOT use `sale_count` as the sales-total line), secondary cash status and diferencia from `facts`, and MUST show `facts.close_note` when present and non-empty. Optional `{sale_count} operaciones` MAY appear only as secondary detail that does not replace or duplicate the sales-total primary line.

#### Scenario: A confirmed sale uses the stored amount
- **WHEN** a `sale_confirmed` event has amount `120.00`, currency `MXN`, and `payment_method` `card`
- **THEN** the feed item MUST show type "Venta", time from `local_time`, and primary text including `120.00` and Tarjeta without Flutter recomputing the amount

#### Scenario: A voided sale shows reason once
- **WHEN** a `sale_voided` event has amount `22.50`, `payment_method` `cash`, and `void_reason` `cobro duplicado`
- **THEN** the feed item MUST show type "Venta anulada", primary including `22.50` and Efectivo, secondary `Motivo: cobro duplicado`, and MUST NOT show Anular

#### Scenario: A short count shows counted primary and expected/diff secondary
- **WHEN** a `cash_count_recorded` event has expected `820.00`, counted `805.00`, difference `-15.00`, and `cash_status` `short`
- **THEN** the feed item MUST show type "Conteo", primary including counted `805.00`, secondary including esperado `820.00` and diferencia `-15.00`, and status Faltante

#### Scenario: A balanced count omits the Cuadrado chip
- **WHEN** a `cash_count_recorded` event has `cash_status` `balanced`
- **THEN** the feed item MUST show primary counted and secondary esperado/diferencia and MUST NOT show a standalone Cuadrado chip

#### Scenario: A close item uses the stored gross total
- **WHEN** a `daily_close_completed` event has `gross_sales_total` `22.50`, `sale_count` 1, `cash_status` `short`, and `cash_difference` `-2.50`
- **THEN** the feed item MUST show type "Cierre", primary including `22.50` en ventas, secondary cash status and diferencia, and MUST NOT use sale count as the sales-total primary line

#### Scenario: A close note is shown when present
- **WHEN** a `daily_close_completed` event includes `close_note` `Faltaron dos billetes`
- **THEN** the feed item MUST show that note text once and MUST NOT invent additional explanation

#### Scenario: Facts are not duplicated unnecessarily
- **WHEN** any supported event is rendered
- **THEN** the same money or status value MUST NOT appear as both redundant primary and secondary restatement beyond the defined matrix

### Requirement: Grouping uses the business date
The client MUST group events by the server `business_date` into temporal sections. It MUST label a date `Hoy` only when it equals server `business_today`, and `Ayer` only when it equals server `business_yesterday`. Any other date MUST be formatted from that calendar date (for example `d de {month} de yyyy`). The client MUST NOT derive the group from `occurred_at`, from the device timezone, or from the UTC date. The client MUST NOT invent speculative relative labels such as "Hace 2 días" or "La semana pasada". Within a date, the client MUST keep the API order (newest first overall).

#### Scenario: A 23:30 local sale stays under its business date
- **WHEN** an event has `business_date` equal to business today and `occurred_at` on the next UTC date
- **THEN** the item MUST appear under Hoy and MUST NOT appear under the UTC date

#### Scenario: Older dates use calendar labels
- **WHEN** an event’s `business_date` is neither `business_today` nor `business_yesterday`
- **THEN** the group label MUST be derived from that `business_date` calendar value

### Requirement: Empty state and coverage copy stay factual
When the feed has no events, the page MUST show the lightweight empty state "Aún no hay actividad registrada." and MUST NOT render fake example activity. The page MUST NOT say "No hubo actividad." The page MUST NOT show the footer "Memoria muestra operaciones confirmadas registradas en Lumo." It MUST NOT show a coverage percentage, a complete state, or a health score.

#### Scenario: No events use the lightweight empty state
- **WHEN** the timeline response contains no events
- **THEN** the empty copy "Aún no hay actividad registrada." MUST be shown and the page MUST NOT claim that no activity happened

#### Scenario: Footer is absent
- **WHEN** the merchant opens Memoria with or without events
- **THEN** the page MUST NOT show "Memoria muestra operaciones confirmadas registradas en Lumo."

### Requirement: Memoria Anular uses the existing void confirmation path
When Memoria renders Anular from a server-provided `sale.void.request@1`, tapping MUST post that action through `POST /api/v1/lumo/actions` using the server `conversation_id`, then show the existing explicit confirmation with server before/after impact and collect a non-empty reason before posting `sale.void.confirm@1`. Flutter MUST NOT calculate impact. After a successful void, Memoria MUST refresh so the original Venta item no longer exposes Anular and Venta anulada is visible. History MUST keep both the original `sale_confirmed` item and the `sale_voided` item.

#### Scenario: Memoria Anular posts void request token
- **WHEN** the merchant taps Anular on a Memoria Venta item that includes `sale.void.request@1`
- **THEN** Flutter MUST post that action id and `context_token` with the server `conversation_id` and MUST NOT mint a client token

#### Scenario: History keeps both items without Anular on the original
- **WHEN** a sale is voided from Memoria
- **THEN** the feed MUST still show the original Venta item and Venta anulada, and neither item MUST expose Anular

## ADDED Requirements

### Requirement: Activity feed preserves existing pagination window
Memoria MUST continue to consume `GET /api/v1/memory/events` with the existing bounded window: default `limit` 20 (max 50), opaque `before` cursor, last 7 business-local dates, newest-first order. When `next_cursor` is present, the page MAY offer "Ver anteriores". This slice MUST NOT introduce infinite scroll unless that mechanism already exists (it does not). Flutter MUST NOT request unsupported query parameters.

#### Scenario: First page stays newest-first bounded
- **WHEN** the merchant opens Memoria and the tenant has more than one page of events inside the 7-day window
- **THEN** the first visible page MUST follow API newest-first order and MAY load older pages only through the existing cursor control
