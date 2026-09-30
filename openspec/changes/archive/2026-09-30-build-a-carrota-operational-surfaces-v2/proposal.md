## Why

Manual acceptance showed Daily Close still feels fragmented: Hoy → Inicio composer for count → Hoy again → review → confirm. Product authority (`docs/PRD_Lumo_AI_Native_Managed_Business_Operations_v0.11.md`) treats Hoy as the day/close surface. This change keeps conversation-first Inicio and makes Daily Close one Hoy-owned task with a dedicated close workspace.

## What Changes

- Keep Inicio light: greeting, short sales sentence, two informative indicators (Ventas hoy, Caja), transcript + composer. No Daily Close CTAs on Inicio.
- Hoy remains day summary + payments + export from `GET /api/v1/business-stream/today`.
- **BREAKING (operator close UX):** Replace Hoy `Registrar conteo` / `Revisar cierre` / inline A–D progression with one suggested action **Preparar el cierre del día** (supporting copy: *Confirma efectivo y revisa pendientes*) that opens a dedicated close bottom sheet/modal workspace.
- Inside the workspace: server facts → numeric counted-cash input (no Inicio navigation) → server reconciliation/difference → optional close note → **Cerrar el día** (`closing.confirm@1`) → short completion → **Listo** returns to closed Hoy.
- Structured cash count MUST reuse `closing.submit_cash_count@1` domain semantics via a new structured action path (today count is message/phrase-only).
- Optional close note is a new product requirement: no persisted note exists today; smallest additive persistence on `ClosingSnapshot` + confirm payload (migration required).
- Typed `cerrar el día` remains conversational fallback on Inicio.
- Remove obsolete operator presentation: Hoy→Inicio composer handoff, inline review progression, `Registrar conteo` / `Revisar cierre` CTAs.
- Navbar and export unchanged. Lovable is hierarchy reference only (no charts / comparisons / top products / replenishment / forecasting).

## Capabilities

### New Capabilities

- None. Extends existing Daily Close / Business Stream capabilities.

### Modified Capabilities

- `business-stream`: Inicio light header unchanged in intent; Hoy `primary_action` becomes single `Preparar el cierre del día` / `close_workspace` for open close-eligible states.
- `mobile-shell`: Operator Daily Close is Hoy → dedicated close workspace (sheet/modal); no Inicio composer handoff for operator count.
- `daily-close-preparation-ui`: Operator path is structured workspace (count + difference + note + confirm); conversational preparation card remains fallback-only.
- `generative-ui-actions`: Add structured cash-count action path; confirm may carry optional `close_note`; silent `request_close` still mints confirm token inside workspace.
- `next-best-action-ui`: Hoy CTA aligns with prepare-close workspace (not Registrar/Revisar).
- `sales-export-ui`: Export remains below Hoy operational/close content; unchanged schema.
- `cash-count-foundation`: Clarify structured action may invoke the same tool; CashCount still stores no note.
- `closing-snapshot-foundation`: Additive nullable merchant close note on snapshot.
- `daily-close-confirmation`: Confirm accepts optional note; fingerprint/staleness unchanged.
- `factual-event-memory`: `daily_close_completed` facts MAY include `close_note` when present.
- `memoria-timeline`: Show close note on closed-day timeline entry when fact present (display only).

## Impact

- Flutter: keep Inicio light header; rewrite Hoy close entry + new close workspace sheet; remove obsolete inline review / composer-focus operator path.
- Backend: structured cash-count via `/lumo/actions` (or approved equivalent); optional `close_note` on confirm + Alembic migration for `closing_snapshots`; business-stream `primary_action` shape update; Memoria display if facts include note.
- Parallel onboarding change stays untouched.
- ADR: **yes** (action catalog + snapshot persistence contract).

## Non-goals

- Memoria activity-feed redesign (Slice 3) beyond displaying an existing close-note fact.
- Onboarding product-semantic edits.
- RF-009, mixed payments, refunds, reopen, inventory, analytics/graphs, comparative trends, top products, forecasting, authorization codes, replenishment.
- Client-side money math or inventing unsupported warnings/pendientes counts.
- Archive, commit, push, or application implementation in this OpenSpec-only refinement step.
- Lovable mock capabilities Build A does not already support.
