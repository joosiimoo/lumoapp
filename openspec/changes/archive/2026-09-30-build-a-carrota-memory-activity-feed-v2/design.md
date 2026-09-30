## Context

Memoria already ships as a bounded factual timeline:

- `GET /api/v1/memory/events` returns newest-first events inside a 7 business-date window (`limit` default 20, max 50; opaque `before` cursor; `business_today` / `business_yesterday`; per-event `local_time`, `facts`, optional `actions`).
- Flutter `MemoriaPage` + `memoria_timeline.dart` group by `business_date` (`Hoy` / `Ayer` / calendar date) and render each event as a large `LumoCard` with multi-line detail.
- Build A event types live today: `sale_confirmed`, `sale_voided`, `cash_count_recorded`, `daily_close_completed`. Fact keys are complete for concise presentation (including optional `close_note` on close).
- Sale corrections already attach restart-safe `sale.void.request@1` on eligible open-day confirmed sales. Flutter must not invent Anular.
- Operational-surfaces-v2 explicitly deferred “Memoria Slice 3” activity-feed redesign; this change is that slice.
- Design system §4.17: typographic date groups, no vertical rail. Lovable is density/hierarchy reference only.

Product authority: PRD v0.11 — Memoria is factual/persistent business memory; Build A embeds a factual timeline without Build B search/evidence/contextual memory.

## Goals / Non-Goals

**Goals:**

- Make Memoria scan as an operational activity stream: chronological, compact, typed, timed, one primary fact per row.
- Keep server facts authoritative; Flutter only maps labels and layout.
- Preserve void-action behavior, pagination/window, header copy, and immutability of Event Memory.
- Raise information density without a dashboard look.

**Non-Goals:**

- Backend/API changes (unless a truly missing presentation fact appears — inspect found none).
- Changing what Lumo writes/remembers; new event types; Build B features.
- Memory search, suggested questions, patterns, insights, inventory, Ver evidencia / Corregir / Olvidar / Explicar.
- Infinite scroll, composer on Memoria, paused onboarding edits, ADR, migration.
- Speculative relative groups (“Hace 2 días”, “La semana pasada”).
- Client-side money math or eligibility inference.

## Decisions

### 1. No backend or API change

**Choice:** Presentation-only Flutter change against the existing DTO.

| Field / response key | Already present | Feed use |
|---|---|---|
| `event_type` | yes | type chip |
| `local_time` (`HH:MM`) | yes | timestamp |
| `business_date` | yes | grouping |
| `business_today` / `business_yesterday` | yes | Hoy / Ayer labels |
| `facts.*` | yes | primary / secondary text |
| `actions[]` + `conversation_id` | yes | Anular when present |
| `next_cursor` | yes | “Ver anteriores” |
| `occurred_at` | yes | order already applied by API |

**Alternative rejected:** Adding display strings or “feed_item” shaping on the server — duplicates presentation logic and expands the API surface without a missing fact.

### 2. Single Activity surface with vertical timeline (Lovable-inspired)

**Choice:** Each date section (`Hoy` / `Ayer` / calendar) owns **one** shared white Activity container. Inside that container:

1. Header label `ACTIVIDAD`
2. Events as a vertical timeline — **no horizontal dividers between events**
3. Small forest-green circular node per event
4. Thin subtle vertical line connecting nodes; line stops at first/last event (single-event groups show node only)
5. Outer radius = design-system card radius; no nested cards, per-row shadows, or borders

Row anatomy:

1. Timeline rail (node + connector) + `local_time` + type chip (+ right-aligned Anular when present)
2. Primary sentence
3. Optional secondary detail / status / close note

**Sale primary mapping (deterministic):**

| `payment_method` | Primary |
|---|---|
| `cash` | `Venta en efectivo por $X` |
| `card` | `Venta con tarjeta por $X` |
| `transfer` | `Venta por transferencia de $X` |

`$X` is the server money string with a leading `$` decoration only. Same mapping applies to `sale_voided` primary (reason stays secondary).

**Alternative rejected:** Horizontal dividers between rows — reads as stacked mini-cards. Independent rounded cards — rejected earlier.

**Design-system note:** One Activity surface + light timeline rail is intentional for scanability. This is not a heavy dashboard rail.

### 3. Deterministic rendering matrix (Build A only)

Currency display: use server money strings as-is; a leading `$` is allowed as pure decoration (no recomputation, no FX). Payment and cash-status labels stay the existing Spanish maps.

| `event_type` | Type label | Primary | Secondary (only if useful) | Actions |
|---|---|---|---|---|
| `sale_confirmed` | Venta | `{payment label} · ${amount}` e.g. `Efectivo · $12.00` (or `Venta en efectivo · $12.00` style — pick one deterministic template in implementation; prefer short: `{payment} · ${amount}`) | none | Anular iff `actions` contains `sale.void.request@1` |
| `sale_voided` | Venta anulada | `{payment} · ${amount}` | `Motivo: {void_reason}` when present | never Anular |
| `cash_count_recorded` | Conteo | `Efectivo contado ${counted_cash}` | `Esperado ${expected_cash} · diferencia ${cash_difference}` + status text/chip from `cash_status` (`Cuadrado` / `Faltante` / `Sobrante`; balanced may read `Caja cuadrada` as status copy) | none |
| `daily_close_completed` | Cierre | `Cierre completado · ${gross_sales_total} en ventas` | cash status + `diferencia ${cash_difference}`; `close_note` when present; optional `sale_count` as `{n} operaciones` only if it does not duplicate the sales total line | none |

Rules:

- Unknown `event_type` → omit.
- Do not show event ids, source ids, `limitation_code`, or `voided_by_actor_id`.
- Do not use `sale_count` as the sales-total line (still `gross_sales_total`).
- Avoid repeating the same amount/status in primary and secondary.

### 4. Temporal grouping stays server-date deterministic

**Choice:** Keep existing grouping logic:

- `business_date == business_today` → `Hoy` (required section when events exist for today)
- `== business_yesterday` → `Ayer`
- else → `d de {month} de yyyy` from `business_date`

Within a group, preserve API order (newest first overall). Do not group from device clock, UTC date, or `occurred_at` calendar day.

**Rejected:** Speculative “Hace 2 días” / “La semana pasada” from Lovable/DS examples — not deterministic enough for this slice and not required when calendar labels work inside the 7-day window.

### 5. Footer removed; empty state shortened

**Footer decision: remove** `"Memoria muestra operaciones confirmadas registradas en Lumo."`

Rationale: the feed itself communicates confirmed operational history; the footer adds vertical weight without new information.

**Empty state:** lightweight single line — `Aún no hay actividad registrada.`  
Do not render fake example rows. Drop the longer secondary empty body (or keep it only if tests prove a one-liner is too abrupt; default is one line).

### 6. Actions and pagination unchanged

- Anular only from server `actions`.
- Existing void request → confirmation sheet → `sale.void.confirm@1` path stays.
- After void / closed day / ineligible sale: no Anular (server omits action).
- Restart/reload remints tokens via GET (unchanged).
- Keep `limit`/`before` and “Ver anteriores”; do not add infinite scroll.

### 7. Spec / ADR / migration scope

| Artifact | Decision |
|---|---|
| `memoria-timeline` | MODIFIED (presentation, empty/footer, row language) |
| `mobile-shell` | light MODIFIED (Memoria = compact activity feed; void refresh still required) |
| `factual-event-memory` | untouched |
| `generative-ui-actions` | untouched |
| ADR | **no** |
| Alembic migration | **no** |

## Risks / Trade-offs

- **[Density vs clarity]** Compact rows may hide secondary detail → Mitigation: secondary line only when useful; cash status remains visible; close note stays when present.
- **[Copy churn vs existing tests]** Current tests assert card titles/lines → Mitigation: update `memoria_timeline_test.dart` with the new matrix; keep void/API regression coverage.
- **[Temptation to add Lovable features]** Search/chips/insights look nearby in mocks → Mitigation: explicit non-goals in specs; forbid those UI elements.
- **[Subtle rail creep]** DS forbids vertical rail; product brief allows “if useful” → Mitigation: default to typographic groups + soft dividers only.

## Migration Plan

None. Ship Flutter presentation change only. Rollback = revert mobile Memoria UI; API unchanged.

## Open Questions

Resolved:

1. Sale primary = sentence mapping (`Venta en efectivo por` / `Venta con tarjeta por` / `Venta por transferencia de`).
2. Conteo suppresses standalone `Cuadrado` chip when balanced; keeps `Faltante` / `Sobrante`. Cierre keeps `Cuadrado` / `Faltante` / `Sobrante` in its secondary summary.
3. Timeline uses green nodes + connector; no horizontal dividers between events.

None blocking.
