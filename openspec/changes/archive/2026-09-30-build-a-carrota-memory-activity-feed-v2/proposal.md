## Why

Memoria currently renders each confirmed business event as a large standalone card. That weight makes chronological scanning slow and makes the tab feel like a stack of detail panels instead of an operational history. For the Carrota pilot, Memoria must answer quickly: “What happened in my business?” — as a compact activity stream, not a dashboard and not oversized cards.

## What Changes

- Replace Memoria’s one-card-per-event layout with a compact chronological activity feed (newest first).
- Keep the existing header: eyebrow `MEMORIA` and Instrument Serif title `Lo que Lumo recuerda`.
- Keep deterministic date grouping (`Hoy` / `Ayer` / calendar date) from server `business_date`, `business_today`, and `business_yesterday`.
- Redefine per-event presentation for live Build A types only: `sale_confirmed`, `sale_voided`, `cash_count_recorded`, `daily_close_completed` — short type label, timestamp, concise primary fact, secondary detail only when useful.
- Preserve backend-authoritative contextual actions (`sale.void.request@1` → Anular). Flutter must not infer eligibility.
- Update empty-state copy to a lightweight single line; remove the page footer that restates what Memoria is.
- Preserve existing `GET /api/v1/memory/events` pagination/window (`limit` default 20 / max 50, `before` cursor, 7 business-date window, “Ver anteriores”).
- Prefer **no backend/API change**. No migration. No ADR unless an architectural contract changes (expected: none).
- Lovable is UX/hierarchy reference only (density, chips, grouping). Do not copy unsupported features (search, suggested questions, patterns, insights, inventory, Ver evidencia, Corregir, Olvidar, Explicar, auth codes, analytics).

## Capabilities

### New Capabilities

- None. This is a presentation redesign of the existing Memoria factual timeline.

### Modified Capabilities

- `memoria-timeline`: Compact activity-feed presentation, type labels, denser rows, empty-state/footer copy, same API and void-action rules.
- `mobile-shell`: Memoria tab remains factual memory; clarify compact activity-feed presentation; void wiring unchanged in intent.

`factual-event-memory` and `generative-ui-actions` are **not** modified: Event Memory fact keys and the void-action envelope already supply everything needed for concise rendering.

## Impact

- Flutter: `memoria_page.dart`, `memoria_timeline.dart`, related widget/tests (`memoria_timeline_test.dart`).
- Backend/API: none expected — DTO already exposes `event_type`, `business_date`, `occurred_at`, `local_time`, `facts`, optional `actions`, `business_today`, `business_yesterday`, `next_cursor`.
- Parallel paused onboarding change stays untouched.
- Design system: warm canvas, compact white activity surface / subtle timeline, soft dividers, forest green accents, restrained chips, Inter / Instrument Serif.
- ADR: **no** (presentation contract only).
- Migration: **no**.

## Non-goals

- Implementation in this OpenSpec-only step; archive; commit; push.
- Paused onboarding (`openspec/changes/build-a-conversational-onboarding-and-minimum-configuration/`).
- Build B memory capabilities (search, evidence, contextual memory, reopen, corrections beyond existing void).
- Changing Event Memory write contracts, fact keys, or inventing Lovable event types.
- Infinite scroll, memory search, composer on Memoria, question chips, client-side financial math, eligibility inference.
