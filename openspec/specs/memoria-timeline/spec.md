# memoria-timeline Specification

## Purpose

Memoria is a bounded, deterministic timeline of confirmed business events. Flutter renders server facts. It does not calculate them, and the screen is not a place to ask questions.

## Requirements

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

### Requirement: The timeline API is a narrow read
The system MUST expose `GET /api/v1/memory/events`. The tenant MUST come from the authenticated context. Allowed query parameters MUST be only `limit` and `before`. `limit` MUST default to 20, MUST be at least 1, and MUST be at most 50. `before` MAY carry an opaque cursor of `occurred_at` and `id`. The server MUST return only events whose operational-day `business_date` is inside the last 7 business-local dates, including today. Order MUST be `occurred_at` descending, then `id` descending. The response MUST include `events`, `next_cursor`, `business_today`, and `business_yesterday`. Each event MUST include the business-event read DTO plus `local_time` as `HH:MM` in that operational day's business timezone. The route MUST NOT accept `event_type`, `business_id`, `query`, `q`, `filters`, free text, or SQL. An invalid `limit` or a malformed cursor MUST return HTTP 422 `VALIDATION_ERROR`. A well-formed cursor outside the 7-day window MUST return an empty event list and a null `next_cursor`. There MUST be no unbounded history. The route MUST NOT write an OperationalDay, a business event, source coverage, a sale, a payment, a CashCount, a ClosingSnapshot, an OutcomeRun, a WorkItem, audit, outbox, or idempotency. It MUST NOT use `BYPASSRLS`.

#### Scenario: The first page is the latest 20 events
- **WHEN** the tenant has 25 events inside the last 7 business dates
- **THEN** the first response MUST contain 20 events in `occurred_at` descending order and a non-null `next_cursor`

#### Scenario: The window does not walk full history
- **WHEN** the client repeats `before` until events older than 7 business dates would be next
- **THEN** those older events MUST NOT be returned

#### Scenario: A bad limit writes nothing
- **WHEN** the client sends `limit` 51
- **THEN** the response MUST be HTTP 422 `VALIDATION_ERROR` and no business row MUST change

#### Scenario: Another tenant cannot read the feed
- **WHEN** tenant B calls `GET /api/v1/memory/events` while tenant A has events
- **THEN** tenant B MUST NOT receive tenant A's events

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
When Memoria renders Anular from a server-provided `sale.void.request@1`, tapping MUST post that action through `POST /api/v1/lumo/actions` using the server `conversation_id`, then show the existing explicit confirmation with server before/after impact and collect a non-empty reason before posting `sale.void.confirm@1`. Flutter MUST NOT calculate impact. After a successful void, Memoria MUST refresh so the original Venta item no longer exposes Anular and Venta anulada is visible. History MUST keep both the original `sale_confirmed` item and the `sale_voided` item.

#### Scenario: Memoria Anular posts void request token
- **WHEN** the merchant taps Anular on a Memoria Venta item that includes `sale.void.request@1`
- **THEN** Flutter MUST post that action id and `context_token` with the server `conversation_id` and MUST NOT mint a client token

#### Scenario: History keeps both items without Anular on the original
- **WHEN** a sale is voided from Memoria
- **THEN** the feed MUST still show the original Venta item and Venta anulada, and neither item MUST expose Anular

### Requirement: Activity feed preserves existing pagination window
Memoria MUST continue to consume `GET /api/v1/memory/events` with the existing bounded window: default `limit` 20 (max 50), opaque `before` cursor, last 7 business-local dates, newest-first order. When `next_cursor` is present, the page MAY offer "Ver anteriores". This slice MUST NOT introduce infinite scroll unless that mechanism already exists (it does not). Flutter MUST NOT request unsupported query parameters.

#### Scenario: First page stays newest-first bounded
- **WHEN** the merchant opens Memoria and the tenant has more than one page of events inside the 7-day window
- **THEN** the first visible page MUST follow API newest-first order and MAY load older pages only through the existing cursor control
