# ADR-017: Cash count and close preparation

- Status: Accepted
- Date: 2026-09-21

## Decision

`expected_cash` is the Decimal sum of `sales.payments.amount` where `status = recorded` and `method = cash` for the confirmed `SaleSession`s of one `OperationalDay`, quantized to two places in the business currency and `0.00` when empty. It is produced by the same repository aggregation that feeds `operational_day.summary@1`, so it always equals that day's `cash_total`. Build A has no opening float, and cash expenses, withdrawals, deposits, refunds, voids, and tips are excluded because no authoritative Build A requirement defines them. Expected cash is computed at read time, never frozen; the frozen figure belongs to a future `ClosingSnapshot`.

`operations.cash_counts` is append-only. The **current** count for a day is the single row whose `superseded_by_id` is NULL, enforced by the immediate partial unique index `uq_cash_counts_current` on `(operational_day_id) WHERE superseded_by_id IS NULL`. A superseded row is never deleted and its `amount`, `actor_id`, and `counted_at` are never modified.

    10|Both supersede links are tenant-safe composite foreign keys to `operations.cash_counts (id, business_id)`, never to `id` alone, so a chain cannot cross tenants even if application code supplies a foreign id. `fk_cash_counts_supersedes` is immediate. `fk_cash_counts_superseded_by` is `DEFERRABLE INITIALLY DEFERRED` — the only non-immediate constraint in the schema — because a recount retires the previous row **before** the replacement row exists. The write order inside the day lock is normative:

1. Read the current count.
2. Generate the new count id in the application.
3. `UPDATE` the previous row to set `superseded_by_id` to that id.
4. `INSERT` the new row with `supersedes_cash_count_id` set to the previous row and `superseded_by_id` NULL.

Step 3 removes the previous row from the partial index predicate before step 4 adds the new one, so two rows never satisfy "current" for one day at any statement boundary. The forward reference is validated at `COMMIT`. Rollback alone restores the previous row to `superseded_by_id` NULL; no compensating write exists.

`cash_difference = counted_cash − expected_cash` and `cash_status` (`not_counted`, `balanced`, `over`, `short`) are derived in the backend on every read and are never persisted. There is no tolerance, threshold, rounding band, or automatic adjustment. The client, the interpreter, and the model never supply or recompute expected cash, counted cash, the difference, or the status.

    20|`closing.submit_cash_count@1` is the only write: input is `amount` alone, `permission = closing.submit_cash_count`, `policy_id = CLOSE-001`, `requires_idempotency = true`. `closing.prepare@1` is a pure read despite the Architecture §10.1 name: empty input, `policy_id = CLOSE-002`, and it inserts or updates no operational day, cash count, sale, payment, audit, outbox, or idempotency row. Both compose `daily_close_preparation@1` with no actions.

The write runs in one application-owned transaction that peeks its idempotency key **before** locking the day, locks today's `operations.operational_days` row `FOR UPDATE`, computes expected cash under that lock, and reserves the key only when persisted state must change. A same-key replay returns the stored original body, which may carry figures older than current state. A different key whose amount equals the current count is a stable read-back that returns live figures and writes nothing at all — no cash count, audit, outbox, or idempotency row.

A `CashCount` requires an existing `OperationalDay`. Recording cash never creates one: ADR-016 keeps the confirming `sale.commit@1` as the only day creator, so a count with no day for today is refused as a non-mutating clarification (`CLOSE-001`, `operational_day_not_started`). A pure preparation read with no day returns the deterministic not-started payload.

`OperationalDay.status` stays `open`. Daily Close confirmation is out of scope: `closing.confirm@1` and `closing.reopen@1` stay unregistered and denied under `SEC-002`, and close-sounding phrases clarify without selecting a tool.

## Consequences

    30|`operations.cash_counts` exists with FORCE RLS, the `tenant_isolation` policy, and `lumo_app` DML grants matching `operational_days`. Alembic `0006_cash_count` (`down_revision = 0005_operational_day`) creates it with no backfill and touches no other table; downgrade drops only that table and discards recorded counts.

Capture and review happen in the existing Inicio conversation stream. Hoy, Memoria, and Negocio stay placeholders, "Preparar el cierre del día" stays unwired, and no closing screen, chart, or history is introduced. `closing_ready_card@1` and `cash_difference_card@1` stay unregistered.

Workflow and memory schemas stay absent. No `ClosingSnapshot`, WorkItem, NextBestAction, OutcomeRun, tolerance rule, denomination, opening float, reconciliation, export, or new infrastructure is part of this decision. ADR-015 and ADR-016 are unchanged.
