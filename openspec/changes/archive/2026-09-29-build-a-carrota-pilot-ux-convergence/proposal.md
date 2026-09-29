## Why

Carrota’s first manual pilot already has Build A sales, cash count, Daily Close, Business Stream, Hoy exports, and conversation cards, but the operator surface is hard to use. Current operational state scrolls away with the transcript, Hoy is only a next-close prompt plus downloads, and `Revisar cierre` inserts a fake merchant turn (`cerrar el día`) before confirmation. Product authority remains `docs/PRD_Lumo_AI_Native_Managed_Business_Operations_v0.11.md`; implemented Build A is the functional source of truth. This slice improves hierarchy, next-action clarity, and Daily Close review without adding domain capabilities.

## What Changes

- Keep Inicio as operational state plus conversation. Pin **current** Business Stream as a compact header (concise state, relevant totals, one next action) separate from transcript history. It MUST NOT fill the viewport. Compact copy uses existing `GET /api/v1/business-stream/today` fields only. The transcript remains the main scrolling region.
- Reframe Hoy as “Así va {negocio} hoy”: sales count and total, payment split, close state, next closing action, coverage limitation, existing Excel/CSV. Stop treating Hoy as NBA-only.
- **BREAKING (client close CTA):** For `cash_difference` and `ready_to_close`, today GET `primary_action` is `kind` `request_close`, label `Revisar cierre`, `invocation` `review_surface`, `message` `cerrar el día` (technical identifier only; never rendered), `action_id` null unless a valid server-issued action token already exists without mutating the GET. GET MUST NOT mint a confirmation token.
- Tap `Revisar cierre` runs existing `request_close` silently via `POST /api/v1/lumo/messages` with that identifier, opens the review sheet, and MUST NOT append a merchant bubble, visible phrase, duplicate `daily_close_preparation@1` card, or a second `Confirmar cierre` on Inicio. If that POST would persist a visible merchant turn after transcript reload, do not hide it only locally; use the smallest existing `POST /api/v1/lumo/actions` `request_close` path instead. No new close workflow.
- `Confirmar cierre` posts existing `closing.confirm@1`. Then dismiss the sheet and refresh Inicio and Hoy from the today GET. Closed copy is `Día cerrado` with no stale close CTAs.
- Keep cash count as composer focus plus typed amount. Keep conversational sale. Typed composer `cerrar el día` may keep the historical card path.

## Capabilities

### New Capabilities

- None. This is a UX convergence on existing Build A capabilities.

### Modified Capabilities

- `business-stream`: Compact current-state presentation; panel is not a chat turn; pinned and compact on Inicio; `request_close` payload and `review_surface` invocation; same GET is Hoy’s daily read model.
- `mobile-shell`: Compact header plus scrolling transcript; silent `request_close` then review sheet; persisted-transcript safety; `closing.confirm@1`; refresh after mutations.
- `daily-close-preparation-ui`: Operator `Revisar cierre` MUST NOT append a preparation card; typed `cerrar el día` may keep the historical card path.
- `next-best-action-ui`: Hoy MUST NOT lead with NBA/`Cerrar el día`. Hoy `Revisar cierre` uses the same silent review path as Inicio.
- `sales-export-ui`: Excel/CSV remain on Hoy below the daily summary. Download contract unchanged.
- `generative-ui-actions`: Operator token mint is silent `request_close`; confirm is `closing.confirm@1`. Fallback to existing `closing.request@1` on `/lumo/actions` only if the message path would persist a visible merchant turn. Catalog unchanged.

## Impact

- Flutter: `InicioPage`, `BusinessStreamPanel`, `HoyPage`, `LumoHome` layout/refresh, new close-review sheet. Typed API client for existing today GET, silent `/lumo/messages` `request_close`, and `/lumo/actions` `closing.confirm@1`.
- Backend: `primary_action.invocation` `review_surface` with `message` `cerrar el día` on the today GET. No confirmation token on GET. No migration. No new table. `request_close` and `closing.confirm@1` workflows unchanged.
- Parallel change `build-a-conversational-onboarding-and-minimum-configuration` stays untouched: do not archive it, do not alter its product semantics, do not mark its remaining acceptance complete.
- No ADR: layout, sheet, and invocation change are not a new architectural boundary (ADR-027 remains the Business Stream read-model decision).

## Non-goals

- Onboarding implementation, acceptance, or product-semantic edits.
- RF-009, mixed payments, inventory, catalog redesign, analytics, graphs, hourly charts, historical comparison, top product, replenishment, forecasting, generative insights.
- New memory, outcome, close state machine, reopen, exception acceptance, Build B, policy @2.
- Migrations, archive, commit, push, or application implementation in this OpenSpec-only step.
- Lovable mock capabilities that Build A does not already implement.
- Turning Inicio into a KPI dashboard or Hoy into a generic analytics dashboard.
- Authoritative totals or close readiness calculated in Flutter.
