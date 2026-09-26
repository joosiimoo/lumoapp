# memoria-timeline Specification

## Purpose

Memoria is a bounded, deterministic timeline of confirmed business events. Flutter renders server facts. It does not calculate them, and the screen is not a place to ask questions.

## Requirements

### Requirement: Memoria shows a bounded factual timeline
`MemoriaPage` MUST replace the placeholder with a timeline of confirmed business events for the authenticated business. The screen MUST use canvas `#FCFAF4`, soft white cards, 24px radius, no hard border, and the existing soft shadow. The header MUST keep the Memoria eyebrow and the Instrument Serif title "Lo que Lumo recuerda". Body text MUST use Inter. Events MUST be grouped by `business_date` with typographic headers and without a vertical rail. The page MUST NOT add a composer, a search field, question chips, or the actions Corregir, Explicar, Olvidar, and Ver evidencia. It MUST NOT add a new UiAction. It MUST NOT be a Generative UI component. Questions stay on Inicio.

#### Scenario: The placeholder is gone
- **WHEN** the merchant opens Memoria after at least one business event exists
- **THEN** the page MUST show that event as a card and MUST NOT show "La memoria factual se habilitará cuando existan eventos confirmados."

### Requirement: Timeline events render from typed facts
The client MUST render only these titles and bodies. `sale_confirmed` MUST use title "Venta registrada" and body `{amount} · {payment method}`, with `cash` shown as Efectivo, `card` as Tarjeta, and `transfer` as Transferencia. `cash_count_recorded` MUST use title "Conteo de efectivo" and MUST show esperado, contado, and diferencia from `facts`, plus the existing status chip Cuadrado, Faltante, or Sobrante for `balanced`, `short`, or `over`. `daily_close_completed` MUST use title "Cierre completado" and MUST show "Ventas registradas" from `facts.gross_sales_total`, the localized cash status, and the difference from `facts`. That sales line MUST NOT use `sale_count`. The time caption MUST be the server `local_time`. The client MUST NOT render event ids, source ids, or `limitation_code`. An unknown event type MUST be omitted. Flutter MUST NOT sum sales, subtract cash, infer cash status, count day totals, recompute the business timezone, or otherwise calculate a domain total. It MUST use server `business_date` and server `local_time`.

#### Scenario: A card sale uses the stored amount
- **WHEN** a `sale_confirmed` event has amount `120.00`, currency `MXN`, and `payment_method` `card`
- **THEN** the card MUST show "Venta registrada" and "120.00 · Tarjeta" without Flutter recomputing the amount

#### Scenario: A short count shows the stored difference
- **WHEN** a `cash_count_recorded` event has expected `820.00`, counted `805.00`, difference `-15.00`, and `cash_status` `short`
- **THEN** the card MUST show those three amounts and the chip Faltante

#### Scenario: A close card uses the stored gross total
- **WHEN** a `daily_close_completed` event has `gross_sales_total` `22.50`, `sale_count` 1, `cash_status` `short`, and `cash_difference` `-2.50`
- **THEN** the card MUST show "Ventas registradas 22.50", "Caja Faltante", and "Diferencia -2.50", and MUST NOT show the sale count as the sales line

### Requirement: Grouping uses the business date
The client MUST group events by the server `business_date`. It MUST label a date `Hoy` only when it equals server `business_today`, and `Ayer` only when it equals server `business_yesterday`. Any other date MUST be formatted from that calendar date. The client MUST NOT derive the group from `occurred_at`, from the device timezone, or from the UTC date. Within a date, the client MUST keep the API order.

#### Scenario: A 23:30 local sale stays under its business date
- **WHEN** an event has `business_date` equal to business today and `occurred_at` on the next UTC date
- **THEN** the card MUST appear under Hoy and MUST NOT appear under the UTC date

### Requirement: Empty state and coverage copy stay factual
When the timeline has no events, the title MUST be "Todavía no hay actividad registrada" and the body MUST be "Las ventas, conteos y cierres confirmados aparecerán aquí." The page MUST NOT say "No hubo actividad." The page MUST show the footer "Memoria muestra operaciones confirmadas registradas en Lumo." once, not on every card. It MUST NOT show a coverage percentage, a complete state, or a health score.

#### Scenario: No events use the registered-activity empty state
- **WHEN** the timeline response contains no events
- **THEN** the empty title and body above MUST be shown and the page MUST NOT claim that no activity happened

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
