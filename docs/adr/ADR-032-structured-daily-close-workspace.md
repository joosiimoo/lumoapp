# ADR-032: Structured Daily Close workspace mutations

- Status: Accepted
- Date: 2026-09-30

## Context

Carrota acceptance showed Daily Close as a fragmented operator loop (Hoy → Inicio composer count → Hoy review → confirm). Product requires one Hoy-owned task: **Preparar el cierre del día** opens a dedicated close workspace with numeric cash count, server reconciliation, optional note, and **Cerrar el día**.

Today:
- Cash count exists only as `closing.submit_cash_count@1` via conversational phrases on `/lumo/messages`.
- `UiActionRegistry` forbids an inline cash-count action.
- `ClosingSnapshot` must not store a note.
- Flutter must not calculate money; confirm already uses fingerprint + `closing.confirm@1`.

OpenSpec change: `build-a-carrota-operational-surfaces-v2`.

## Decision

### Structured cash count UiAction

Register `closing.submit_cash_count@1` on `UiActionRegistry` and `POST /api/v1/lumo/actions`.

- `context_token` is `typ=ui_action`, conversation-bound; **amount is not in the JWT**.
- Request `payload` is `{ "amount": "<decimal-string>" }`.
- Handler verifies the token, validates amount with existing `parse_counted_amount`, and invokes **`RecordCashCount`** (same domain workflow as the message path).
- No second reconciliation engine; expected cash, difference, and `cash_status` remain server-authored.
- Conversational phrase cash count on `/lumo/messages` remains supported.

### Optional close note on ClosingSnapshot

Add nullable `close_note` on `operations.closing_snapshots` (max 500 characters at the domain/API boundary; trim; blank → null).

- Note is accepted on `closing.confirm@1` (action payload / tool input optional field).
- Persisted only on successful confirm with the immutable snapshot.
- Included in audit/event facts and Memoria when present.
- **Not** stored on `CashCount`.
- **Not** part of the preparation fingerprint.
- Always optional; never required to close in Build A.

### Operator UX boundary

Hoy exposes one prepare-close CTA and owns the workspace. Typed `cerrar el día` remains a conversational fallback. Inicio stays conversation-first without operator close chrome.

## Consequences

- Amends ADR-017 (cash count exposure), ADR-018 (confirm payload), ADR-019 (action catalog), ADR-025 (close event facts) additively.
- Requires Alembic migration for `close_note`.
- ADR stays **Proposed** until Carrota manual acceptance; then Accept.
- Flutter still does no money math; LLM still cannot mutate.
- Charts, comparisons, reopen, RF-009, and Build B stay out of scope.
