## Context

Carrota is running a manual Build A pilot. Inicio already loads `GET /api/v1/business-stream/today` and renders `BusinessStreamPanel` above the conversation, but the whole page is one `ListView`, so current state scrolls away with sale and close cards. Hoy loads `GET /api/v1/operational-days/current/next-best-action` and otherwise only exports; it does not show the day’s sales, tenders, or close figures. `Revisar cierre` on Inicio calls `_sendPhrase`, which inserts a merchant bubble `cerrar el día` and then the existing `request_close` ask (`¿Confirmas el cierre?`) plus `daily_close_preparation@1`. Hoy still labels the same step `Cerrar el día`.

Functional source of truth: implemented Build A (OperationalDay, CashCount, ClosingSnapshot, `summarize_day`, `closing.confirm@1`, Business Stream GET). Visual/IA reference: Lovable mock from product review. Product vision: PRD v0.11. Parallel OpenSpec change `build-a-conversational-onboarding-and-minimum-configuration` is in progress or paused and MUST stay separable.

## Goals / Non-Goals

**Goals:**

- Make current operational state always discoverable on Inicio without scrolling history.
- Make Hoy a structured “Así va {negocio} hoy” view from the same deterministic facts.
- Replace the synthetic close utterance with a dedicated review surface and consistent CTAs.
- Keep conversational sale and conversational cash count.
- Refresh Inicio current state and Hoy after sale commit, cash count, and close confirm.

**Non-Goals:**

- New domain behavior, close state machine, reopen, exception policy, RF-009, mixed payments, inventory, analytics, memory, outcomes, Build B, policy @2.
- Onboarding product semantics, archive, migrations, commit/push, or implementation in this artifact step.
- Copying Lovable capabilities that Build A does not implement.
- A new Hoy REST resource if `GET /api/v1/business-stream/today` already contains the fields.

## Decisions

### 1. Pin current state; scroll only the transcript

Inicio layout becomes:

1. Eyebrow `LUMO · {BUSINESS}`
2. Greeting (`Buenos días` stays)
3. **Current operational state** (`BusinessStreamPanel`) — not a `InicioTurn`
4. Recent conversation (merchant bubbles, Lumo prose, sale/payment/close cards already in the stream)
5. Composer (existing shell footer)

The current-state region MUST NOT share a single unbounded `ListView` with the transcript. Use a column: compact fixed/header current state; independently scrolling conversation as the main content. The pinned region MUST stay compact: concise state, relevant totals, one next action. It MUST NOT consume most of the viewport or become a dashboard. Returning to the Inicio tab MUST show that region without restoring a scroll offset that hid it.

**Alternative considered:** Keep one `ListView` and jump to offset 0 on tab focus. Rejected: growing conversation still pushes the panel off-screen while the merchant is on Inicio.

**Alternative considered:** Append a new Business Stream card into the transcript on every refresh. Rejected: that is the current “buried turn” failure mode.

### 2. Compact panel copy is Flutter presentation of existing GET fields

Do not add money fields. Do not invent a second `operator_state` table. Flutter formats server decimals and maps `cash_status` / `operator_state` to the compact hierarchy:

| State | Compact current-state content | CTA |
| --- | --- | --- |
| `no_active_day` | `Cuando empiece la actividad, organizo el día.` | none |
| `organizing` (contract-only) | sales line + tender line from `factual_summary` | none |
| Active open day with sales (`cash_count_required` after first sale is the merchant-reachable active case) | `{n} venta(s) · ${gross}`; `Efectivo … · Tarjeta … · Transferencia …` using server tenders | per state |
| `cash_count_required` | `Falta contar efectivo`; `Esperado ${expected}` | `Registrar conteo` |
| `cash_difference` | `Faltante` or `Sobrante`; expected, counted, server difference | `Revisar cierre` |
| `ready_to_close` | `Caja cuadrada`; expected, counted, difference | `Revisar cierre` |
| `closed` | `Día cerrado`; `{n} venta(s) · ${gross}` from snapshot-backed summary | none |
| `unavailable` | existing failure copy + retry | retry |

Omit long `responsibility`/`detail` paragraphs from the compact panel when the table above already states the fact. Amounts stay server strings. Coverage stays on Hoy, not as a dense Inicio footer.

Server `primary_action.label` values stay `Registrar conteo` and `Revisar cierre`. Closed panel MUST NOT show `Registrar conteo`, `Revisar cierre`, or `Confirmar cierre`.

### 3. Hoy consumes the same today GET

Hoy title: `Así va {business_name} hoy` from session business name (Carrota in the pilot).

Hoy loads `GET /api/v1/business-stream/today` when the tab becomes visible (same body as Inicio). It MUST NOT sum tenders, subtract cash, or choose `operator_state`.

Minimum cards:

- Summary: confirmed `sale_count`, `gross_sales_total`
- Payments: `cash_total`, `card_total`, `transfer_total`
- Closing: `operator_state` / `cash_status`, expected/counted/difference when the GET provides them, next action from `primary_action` when non-null
- Coverage: existing `Este cierre considera las operaciones registradas en Lumo.` when `coverage` is non-null
- Exports: existing `Descargar Excel` / `Descargar CSV` (`sales-export-ui`)

`GET /api/v1/operational-days/current/next-best-action` remains for conversational `qué sigue` / `next_best_action@1`. Hoy MUST stop using it as the primary Hoy body and MUST NOT show `Cerrar el día`.

No new export API. `daily-sales-export` file contract is unchanged.

### 4. Daily Close review is a bottom sheet, not a fake utterance

**Default surface:** Flutter modal bottom sheet (Lumo canvas, max-width 420px column). Not a new Generative UI component and not a new tool.

**Today GET `primary_action` for `cash_difference` and `ready_to_close` (closed):**

- `kind`: `request_close`
- `label`: `Revisar cierre`
- `invocation`: `review_surface`
- `message`: `cerrar el día` (technical identifier only; never a merchant bubble, never a visible CTA label, never conversational copy)
- `action_id`: `null`, unless the current implementation already has a valid server-issued action token **without mutating the GET**
- GET MUST NOT mint `confirmation_token` and MUST NOT include `closing.confirm@1`

`cash_count_required` stays `message` null, `invocation` `composer`, label `Registrar conteo`.

**Approved operator path (one path):**

1. `cash_count_required` → `Registrar conteo` → composer focus → typed cash phrase → existing cash-count workflow
2. Count recorded → `ready_to_close` or `cash_difference`
3. Tap `Revisar cierre` (Inicio or Hoy) → silent `POST /api/v1/lumo/messages` with `primary_action.message` on the shell `conversation_id` → existing `request_close` returns `closing.request@1` / `confirmation_token` → open the sheet populated from server facts (today GET plus that response)
4. Sheet `Confirmar cierre` → existing `closing.confirm@1`
5. Sheet closes; Inicio and Hoy reload `GET /api/v1/business-stream/today`; copy is `Día cerrado`; no stale `Registrar conteo` / `Revisar cierre` / `Confirmar cierre`

The operator path MUST NOT append a merchant turn `cerrar el día`, MUST NOT display that phrase, MUST NOT append a duplicate `daily_close_preparation@1` into the visible transcript, and MUST NOT show a second `Confirmar cierre` on Inicio.

**Persisted-conversation safety:** A silent review-surface `request_close` MUST NOT later reappear as a visible merchant `cerrar el día` turn after transcript reload. Implementation MUST inspect current `/lumo/messages` persistence. If that path necessarily persists a visible merchant turn, implementation MUST NOT hide it only in local UI. Stop, report the constraint, and use the smallest existing `POST /api/v1/lumo/actions` path that runs `request_close` (`closing.request@1`) without creating a merchant turn. Do not invent a new close workflow or state machine.

Typed composer `cerrar el día` MAY keep the historical conversational card path.

**Sheet contents (server fields only):** sale count, gross total, cash/card/transfer, expected cash, counted cash, difference, close status label, coverage sentence. Primary: `Confirmar cierre`. Secondary: dismiss without calling confirm.

**Difference:** show server `cash_difference` and `cash_status`. Short and over remain confirmable under existing Daily Close rules. No new acceptance policy.

GET still writes nothing. The silent message uses the identifier the GET already returned; Flutter MUST NOT invent a different close phrase or a new action id.

### 5. Refresh

After successful sale commit, cash-count message/action, and close confirm: reload `GET /api/v1/business-stream/today` for Inicio current state and for Hoy if that tab is built from the same model. Do not treat a stale local card as current close state.

### 6. Lovable

Adopt: hierarchy, readable daily summary, payment breakdown, whitespace, structured close surface, one primary CTA, clear closed success.

Do not adopt: inventory, stock alerts, authorization codes, mixed payments, hourly chart, historical %, top product, replenishment, forecasting, unsupported insights.

### 7. ADR

No new ADR. ADR-027 still owns the Business Stream read model. A bottom sheet and a pinned header are UI composition, not a persistence or tenancy boundary.

### 8. Directory structure

- Flutter: `mobile/lib/features/inicio/` (panel, layout), `mobile/lib/features/hoy/hoy_page.dart`, new focused widget under `mobile/lib/features/inicio/` or `mobile/lib/features/hoy/` for the close review sheet, `mobile/lib/app/lumo_app.dart` for refresh and CTA wiring.
- Backend: `backend/app/domain/operations/business_stream.py` (`invocation` `review_surface`, `message` `cerrar el día`) and `backend/tests/test_business_stream.py`.
- Do not add Alembic revisions. Do not edit onboarding specs or `apply_onboarding`.

## Risks / Trade-offs

- [`POST /lumo/messages` may persist a merchant turn] → Mitigation: inspect persistence before shipping. If it would reappear after reload, do not local-hide; switch to existing `/lumo/actions` `closing.request@1` without a new workflow.
- [Hoy and Inicio could drift if they used different endpoints] → Mitigation: both read `business-stream/today`.
- [Historical typed `cerrar el día` cards remain in old transcripts] → Mitigation: allowed as history; operator CTA path must not add new ones.
- [Onboarding change in the same working tree] → Mitigation: do not touch onboarding files, remaining acceptance, or archive.

## Migration Plan

None. No schema change. Rollback is reverting the Flutter shell and the `primary_action.invocation` field without data repair.

## Open Questions

None.
