## 1. WorkItem domain and migration

- [x] 1.1 Add `backend/app/domain/operations/work_item.py` with the three types, `open`/`resolved`, the one-item desired set, and resolution codes including `cash_count_recorded`, `cash_balanced`, `day_closed`, and `cash_unbalanced`. No FastAPI, SQLAlchemy, or copy templates. Do not add `surfaced_at`
- [x] 1.2 Add Alembic `0010_work_items` down from `0009_catalog_price_override`: table, checks for `resolution_actor_type` and nullable `resolved_by_actor_id`, composite FK, partial unique index, FORCE RLS, `tenant_isolation`, grants, no backfill. Downgrade aborts when any row exists

## 2. Repository

- [x] 2.1 Add tenant-scoped load, insert, evidence update, and resolve methods. Resolve stores `business` plus actor id, or `system` plus a null actor id. Product code never deletes. Reset helper deletes `work_items` after cash counts and before operational days, including `work_item.created` and `work_item.resolved` audit

## 3. Transition-only sync

- [x] 3.1 Add `sync_daily_close_work_items` for today's day only: create, update evidence, resolve, or insert a new generation so the open set is empty or exactly one type. A no-op must not touch `updated_at` or audit
- [x] 3.2 Call it from successful `sale.commit@1` and from a new cash-count insert, inside those transactions. Do not call it from replay, confirmed read-back, equal-amount count read-back, `closing.prepare@1`, summary, export, the Next Best Action GET, or the Next Best Action tool
- [x] 3.3 On successful `closing.confirm@1`, resolve the one open row with `day_closed` and `resolution_actor_type=business`. Do not insert a WorkItem. Short and over remain closable without a `close_confirmation_required` row

## 4. Rollout initializer

- [x] 4.1 Add an application command that uses `DATABASE_ADMIN_URL`, lists businesses with RLS disabled only for that listing transaction, then for each business sets the tenant GUC and runs the same desired-set function for open today. Audit actual inserts as `work_item.bootstrap` with a null actor and `origin=rollout_bootstrap`. Do not grant `BYPASSRLS`, expose an HTTP route, or write sales, cash counts, snapshots, outbox, or idempotency

## 5. Next Best Action query

- [x] 5.1 Add the pure projector and Spanish templates, including absolute short/over titles and `las ventas registradas en Lumo`. `pending_count` is the stored open-row count
- [x] 5.2 Rank `cash_count_required`, then `cash_difference_review`, then `close_confirmation_required` only if more than one open row exists. Do not write `surfaced_at` or any other column
- [x] 5.3 Add `GET /api/v1/operational-days/current/next-best-action` without an idempotency key. Missing day returns `200` and a null action. A repeated GET must not change the database. Do not add a work-items list route

## 6. Tool, policy, and conversation

- [x] 6.1 Register `operational_day.next_best_action@1` (`sale.create`, `NBA-001`, `side_effect=read`, `requires_idempotency=false`) and `next_best_action` version `1`. The tool must not write. Do not add a UI action id or an OutcomeRun
- [x] 6.2 Map only the exact normalized phrases `que sigue`, `que falta`, `que tengo pendiente`, `que sigue con el cierre`, `que falta para cerrar`, `que falta para el cierre`, and `que tengo pendiente para cerrar`. Leave `qué sigue con el cierre por favor`, `preparar el cierre`, and `ventas de hoy` off this tool. Assistant text must be the server fallback, or `No hay un paso pendiente para el cierre de hoy.`

## 7. Flutter

- [x] 7.1 On Hoy, above the export panel, show `Próximo paso`, the server title and reason, and `1 pendiente` when `pending_count` is 1. Omit them when the action is null or the count is 0. Refetch when the tab becomes visible. Do not calculate money
- [x] 7.2 Show `Cerrar el día` only when the GET lists `closing.request@1`, switch to Inicio, and post `cerrar el día` on the shell conversation id. Do not post `/api/v1/lumo/actions` from Hoy. Count actions get no button and no amount field
- [x] 7.3 Render `next_best_action@1` in the Inicio stream, reuse `closing.request@1`, and suppress duplicate fallback prose. Export buttons stay CSV/XLSX only

## 8. Tests

- [x] 8.1 Two NBA GETs and two tool calls leave WorkItem, audit, and idempotency rows unchanged and return the same projection
- [x] 8.2 Short and over each leave only `cash_difference_review` open with `pending_count` 1. Balanced leaves only `close_confirmation_required` with `pending_count` 1. Closed returns `pending_count` 0
- [x] 8.3 Short to balanced recount resolves the difference as `system` with a null actor id and creates one `close_confirmation_required`. Short to close resolves the difference as `business` with `day_closed` and does not require a close-confirmation row
- [x] 8.4 A pre-0010 open today matches the deploy initializer and does not depend on a GET write. A second initializer run adds no row and no audit
- [x] 8.5 Model arguments are denied. Flutter does not recompute amounts. Prepare, summary, and export write no WorkItem. Existing confirm and export behavior stay unchanged. A failed commit rolls the WorkItem back

## 9. ADR-023

- [x] 9.1 Add `docs/adr/ADR-023-work-items-next-best-action.md` with the decision in design.md: transition-maintained WorkItems, pure NBA reads, no `surfaced_at`, one difference job for short/over, resolution actor semantics, and the deploy initializer. Do not edit ADR-015 through ADR-022
