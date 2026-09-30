## Context

Implemented v2 work lightened Inicio and moved close CTAs to Hoy, but acceptance showed the operator still experiences a fragmented loop: Hoy `Registrar conteo` → Inicio composer phrase → return Hoy → `Revisar cierre` → inline confirm. Product decision: Hoy owns **one** Daily Close task via **Preparar el cierre del día** opening a dedicated close workspace (Lovable hierarchy reference only).

**Current backend facts (inspected, not assumed):**

- Cash count domain: `closing.submit_cash_count@1` / `RecordCashCount`; input `{ amount }`; computes expected/difference server-side; emits `daily_close_preparation@1`.
- Cash count exposure today: **only** `POST /api/v1/lumo/messages` via counted phrases (`tengo X en caja`, …). **No** UiAction for cash count; generative-ui-actions forbids an inline cash-count action today.
- Confirm: `closing.confirm@1` with server JWT (`confirmation_token`) + live preparation fingerprint; mint via `request_close` (`cerrar el día` technical message or `closing.request@1`).
- **No** persisted Daily Close note on `CashCount`, `ClosingSnapshot`, or `OperationalDay`. Snapshot foundation explicitly forbids a note column today. Difference copy intentionally does not explain why.
- Business Stream `primary_action` today: `Registrar conteo` (`composer`) or `Revisar cierre` (`review_surface`).

## Goals / Non-Goals

**Goals:**

- Conversation-first Inicio (light header) unchanged in intent.
- Hoy day summary + one prepare-close entry point.
- Dedicated close workspace: facts → numeric count → server difference → optional note → confirm → completion → Listo.
- Reuse cash-count and confirm domain guarantees; Flutter never calculates money.
- Typed `cerrar el día` remains fallback.
- Remove obsolete fragmented operator presentation.

**Non-Goals:**

- Lovable analytics (charts, % change, top products, sales-by-hour, replenishment, auth-code warnings, predictions).
- Memoria Slice 3 redesign; onboarding; Build B; reopen; RF-009.
- Client-only notes or fake reconciliation.

## Decisions

### 1. Inicio stays light (unchanged contract)

Greeting → `Llevas $<gross> en ventas.` (or idle `responsibility`) → VENTAS HOY + CAJA indicators → transcript + composer. No close CTAs. Refresh after mutations.

### 2. Hoy entry: one suggested close action

When `operator_state` is `cash_count_required`, `cash_difference`, or `ready_to_close`, Hoy shows a single operational CTA:

- Label: `Preparar el cierre del día`
- Supporting copy (approved static operator copy): `Confirma efectivo y revisa pendientes`
- Does **not** invent a pendientes count or unsupported exception list

**Today GET `primary_action` (revised):**

| Field | Value |
| --- | --- |
| `kind` | `prepare_daily_close` |
| `label` | `Preparar el cierre del día` |
| `invocation` | `close_workspace` |
| `message` | `null` |
| `action_id` | `null` |

Closed / idle / unavailable: `primary_action` null. Export stays below operational/close content.

**Obsolete on Hoy chrome:** `Registrar conteo`, `Revisar cierre`, inline A/B/C review card, Inicio composer focus for operator count.

### 3. Close workspace (primary operator UX)

Tap opens a dedicated bottom sheet/modal (focused workflow; does not navigate to Inicio).

**Initial pane (server facts from today GET + optional preparation refresh):**

- Title: `Cierre del día`
- Short Lumo preparation message (server `responsibility` / `detail` / approved template from existing fields—no invented warnings)
- Sales total, operation count, payment split when present
- Expected cash
- Coverage / attention.why when present

**Cash count pane:**

- Prompt: `Según las ventas, deberías tener $<expected> en efectivo. ¿Cuánto contaste?` (expected from server)
- Numeric money input
- Submit records counted cash **without** conversational text entry and **without** Inicio navigation

**After successful count:** refresh server facts (workspace and Hoy today GET). Show balanced vs short/over using server `cash_status` / `cash_difference` only. Short/over remain confirmable under existing Daily Close policy. Workflow stays open until confirm or dismiss.

**Optional note:**

- Control: `Agregar nota`
- Free-text optional reason/context before final confirm
- Visible in workspace prior to `Cerrar el día`

**Final close:**

- Primary: `Cerrar el día` → mint confirmation token (silent `request_close` / existing `closing.request@1` safety path) → `closing.confirm@1` with token (+ optional note payload)
- Preserve fingerprint staleness, explicit confirm, no success before commit
- Success: short completion state in the same workspace (closed confirmation + authoritative final reconciliation facts if useful). No invented analytics.
- `Listo` dismisses workspace; Hoy shows closed state without close CTA

**Dismiss / cancel:** leaves day open; no confirm mutation.

### 4. Structured cash count: reuse domain via new action path

**Decision:** Flutter MUST NOT rely on composing merchant phrases. Add the smallest structured path that calls existing `RecordCashCount` / `closing.submit_cash_count@1`:

- Register UiAction id `closing.submit_cash_count@1` (or equivalent versioned action id aligned with the tool) on `POST /api/v1/lumo/actions`.
- Request carries `context_token` (`typ=ui_action`, conversation-bound; **amount not in JWT**), `conversation_id`, idempotency key, and `payload: { "amount": "<decimal-string>" }` (mirror void_reason payload pattern).
- Server validates amount with existing `parse_counted_amount` and runs the same workflow as the message path.
- Workspace may obtain the action token by a minimal server-authored issuance (e.g. today GET does **not** mint tokens; workspace opens then issues token via existing silent prepare/request path, or a tiny additive issuance on an existing read—prefer reusing `closing.request@1` / preparation issuance patterns only where they already mint ui_action tokens; if count needs a dedicated mint before amount submit, use the smallest existing composer/action issuance without inventing a second close state machine).

**Alternative considered:** Silent `POST /lumo/messages` with constructed `tengo X en caja`. Rejected as primary: still conversational grammar, risk of persisted merchant turn, weaker structured contract.

**Generative UI card:** Operator workspace MUST NOT append `daily_close_preparation@1` into the Inicio transcript for this path. Response UI may be consumed silently inside the workspace.

### 5. Close note persistence (new; migration required)

**Current support:** none.

**Decision (smallest additive):**

| Layer | Change |
| --- | --- |
| `operations.closing_snapshots` | Nullable `close_note` `TEXT` (or `VARCHAR` with explicit max, e.g. 500) |
| Domain `ClosingSnapshot` | Optional `close_note` |
| `closing.confirm@1` | Optional payload field `close_note` (string; empty/null = omit) |
| Audit / outbox | Include note in confirm after_payload when present |
| `daily_close_completed` facts | Include `close_note` when non-null |
| Memoria timeline | Display note text when fact present |
| `CashCount` | **No** note column (foundation stays amount-only) |

Note is merchant-authored context for shortage/surplus (or optional balanced commentary); it MUST NOT change money math, eligibility, or fingerprint contents (fingerprint remains preparation money identity only unless an existing confirm rule requires otherwise—do not fold free text into fingerprint).

**Migration:** Yes — Alembic additive nullable column. Rollback: stop writing field; column may remain.

### 6. Conversational fallback

Typed `cerrar el día` / historical preparation card / confirm phrases on Inicio remain. Secondary to Hoy workspace.

### 7. Design system / Lovable

Lovable: single-task workspace, progressive disclosure, numeric input, difference feedback, optional note, final CTA, completion. Visuals: Lumo warm canvas, white cards, forest primary. No unsupported Lovable features.

### 8. Obsolete implementation to remove

- Hoy `Registrar conteo` / `Revisar cierre` buttons and A/B/C/D inline progression
- `_beginCashCountEntry` operator handoff from Hoy close CTA (composer focus may remain only if some other path needs it—not the prepare-close path)
- Inline `close-review-inline` confirm card as primary
- Helpers/tests keyed to that fragmented flow

Retain shared server-fact formatting utilities where useful.

### 9. ADR and migration

**ADR: Yes.** Changes closed UiAction catalog (cash-count action) and ClosingSnapshot persistence (note). File ADR under `docs/adr/` during implementation (title e.g. Structured Daily Close workspace mutations). ADR-027 Business Stream read model remains for today GET.

**Migration: Yes** for `close_note` on `closing_snapshots`. No migration for cash-count action alone.

## Risks / Trade-offs

- [New cash-count UiAction] → Catalog expansion; mitigate by reusing `RecordCashCount` only, amount in payload not JWT.
- [Close note on snapshot] → Amends “MUST NOT store a note”; mitigate with nullable optional field + ADR + foundation delta.
- [Supporting copy “revisa pendientes”] → Must not imply NBA pending_count; static copy only.
- [Two close UIs] → Workspace vs conversational fallback; test both; do not merge domains.
- [Token mint inside workspace] → Keep silent request_close safety (no fake bubble; actions fallback if messages persist visible turns).

## Migration Plan

1. Land ADR + Alembic `close_note` + confirm/action contract + business-stream `primary_action` update.
2. Ship Flutter workspace; remove obsolete Hoy/Inicio operator handoff/inline review.
3. Rollback: revert mobile + disable action/note writes; nullable column harmless.

## Open Questions

- Exact max length / empty-string normalization for `close_note` (recommend 500 chars, trim, blank → null).
- Whether balanced closes should show `Agregar nota` always or only when `cash_status` is `short`/`over` (product default: always optional; emphasize when difference ≠ 0).
