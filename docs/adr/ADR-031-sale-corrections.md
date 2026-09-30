# ADR-031: Sale corrections (active remove + confirmed void)

- Status: Accepted
- Date: 2026-09-29

## Context

Carrota needs merchant-facing corrections before Daily Close: drop a mistaken line from an active sale, and void a wrong confirmed sale without erasing history. ADR-014/015 reserved item remove and void. Live aggregates, export, cash count, Daily Close preparation, Business Stream, and Event Memory all treat `confirmed` as the live sale signal. PRD v0.11 §21.7–21.8 and RF-086 authorize this Carrota pilot carve-out.

## Decision

### Voided status

Extend `SaleSession.status` with `voided`. Void keeps the session, all `SaleItem`s, and the single `Payment` (`status` remains `recorded`). Persist `voided_at`, `voided_by_actor_id`, and non-empty `void_reason`. Day membership (`operational_day_id`, `confirmed_at`) stays. Active unique index remains `WHERE status IN ('open', 'ready_to_charge')`.

Mutate only when status is `confirmed` and the OperationalDay is `open`. Already `voided` is a non-mutating read-back (no second event/audit/outbox). Closed-day void is refused. No reopen and no ClosingSnapshot rewrite.

### Active item removal

`sale.remove_item@1` hard-deletes one `SaleItem` on `open` or `ready_to_charge` under `SELECT … FOR UPDATE`. Session total is Σ remaining `line_total`. Empty `ready_to_charge` demotes to `open` with no payment actions. No Event Memory for uncommitted remove.

### Persisted `sale_revision`

`sales.sale_sessions.sale_revision` is an `INTEGER NOT NULL` column (`CHECK >= 1`), initialized to `1` on insert and backfilled to `1` for existing rows. Successful remove when the pre-remove status was `ready_to_charge` increments it by one in the same locked transaction. Open removes, add-item, totalize, commit, and void do not advance it.

Payment action tokens (`sale.pay.cash@1` / `card` / `transfer`) bind JWT claim `sale_revision` equal to the persisted column at mint time. Commit compares the claim to the locked session column; mismatch returns `ui_action_stale` without Payment / transition writes. Fresh post-remove summary tokens bind the new revision. Clients MUST NOT invent or supply revision as authority. This column is payment-cart staleness only, not a general optimistic lock.

### Aggregates and close

Live gross, sale count, tenders, expected cash, Daily Close preparation, and Business Stream / Hoy open-day facts continue to count only `status=confirmed`. Voided are excluded by that filter. After void, preserve CashCount counted amount; recompute difference/status; re-sync Daily Close WorkItems / OutcomeRun via `maintain_open_daily_close`; prior close-confirm tokens whose prep fingerprint changed become stale.

### Event Memory

Keep `sale_confirmed`. Append exactly one `sale_voided` (`source_entity_type=sale_session`) with facts: `sale_session_id`, `payment_id`, `payment_method`, `amount`, `currency`, `void_reason`, `voided_by_actor_id`. Memoria title: **Venta anulada**.

### Export

Daily sales export includes `confirmed` and `voided` rows. Insert column `sale_status` immediately after `sale_session_id`. Operational reconciliation (`SUM(line_total)`, payment sums) uses confirmed rows only.

## Consequences

- ADR-014/015/017/018/022/025 remain; this ADR amends them for corrections.
- Flutter still does no money math; LLM still cannot mutate.
- Refunds, reopen, inventory, RF-009, and Build B stay out of scope.
