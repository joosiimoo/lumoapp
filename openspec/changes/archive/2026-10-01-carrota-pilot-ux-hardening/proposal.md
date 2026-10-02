## Why

Final Carrota acceptance is `PILOT_READY`, but five non-blocking UX findings still make the operator transcript unreliable before the pilot starts. A priced catalog line with an inline reason is stored as a free concept, item removal does not name what was removed, and Inicio hides recent activity behind layout and scroll bugs. This change fixes only those findings. Product authority remains `docs/PRD_Lumo_AI_Native_Managed_Business_Operations_v0.11.md` for conversation-first Inicio and `docs/LUMO_DESIGN_SYSTEM_v1.0.md` for visual treatment. Build A implemented behavior stays the functional baseline.

## What Changes

- Interpret `1 galleta A a 10 por promoción` as catalog product Galleta A, unit-price override `10.00`, and reason `promoción`. Do not persist a free-concept line whose name is the whole phrase.
- Keep the existing two-step override question when the utterance has a different price and no inline reason (`2 galletas A a 10`).
- After a successful item remove, the confirmation names the removed product, and the historical card shows a clear `Quitado` state.
- Stop the Inicio transcript and the operational summary from overlapping or crowding each other while the transcript scrolls.
- When the merchant returns to Inicio, show the recent transcript activity instead of resetting to the first turn. The light operational header stays visible at the top.
- Show `HH:MM` on Inicio transcript events and generated cards. User bubbles stay without a timestamp, as in design-system §4.6. Card time uses the caption treatment already used on memory cards (§4.16).

## Capabilities

### New Capabilities

- None. These are corrections to existing sale interpretation and Inicio presentation.

### Modified Capabilities

- `catalog-price-override`: A same-utterance `por {motivo}` that is not a kilogram basis completes one catalog override. A price difference without that clause still asks and writes nothing. An over-long inline reason writes nothing, leaves the pending override without that reason, and lets a later valid reason complete it.
- `noncatalog-sale-item`: Price and inline-reason tails are removed before resolution. A unique catalog match stays catalog. A free-concept snapshot is the cleaned span, never the whole priced phrase, and still stores no override reason.
- `conversational-sale-runtime`: The scripted interpreter and pending-override store treat an inline reason as completion, not as a new product name and not as a leftover pending question.
- `sale-item-added-ui`: Successful remove confirms the product name already on the card and marks that historical card `Quitado`.
- `sale-summary-ui`: The removed summary row shows `Quitado` and loses its enabled `Quitar`.
- `mobile-shell`: Inicio keeps a non-overlapping operational summary, restores the latest transcript activity on return, and shows event time on transcript cards.

## Impact

- Backend, only for the inline catalog reason: sale utterance parsing and the existing catalog add-item completion path. No migration, no new column, no new tool, no Generative UI version bump.
- Flutter: Inicio layout, transcript scroll position, card timestamps, and the historical remove state. Confirmation uses `product_name` already present on the removed card and server counts/totals already in the remove response.
- Untouched: onboarding, Daily Close, Memoria, exports, Hoy close workspace, and catalog CRUD.

## Non-goals

- Expanding product scope, new sale types, discounts, percentages, or a general reason grammar beyond `por {motivo}`.
- Onboarding copy, flow, or acceptance.
- Daily Close, cash count, Memoria timeline, factual memory, or Excel/CSV exports.
- Migrations, new tables, or backend changes for remove copy, scroll, overlap, or timestamps.
- Redesigning Inicio, adding a dashboard, charts, or POS grid.
- Implementing this change in the same step as the OpenSpec artifacts.
