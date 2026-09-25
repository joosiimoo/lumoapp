## Context

Daily Close already works. `sale.commit@1` confirms a sale only with one recorded `Payment` and opens today's `OperationalDay`. `closing.submit_cash_count@1` appends a current `CashCount`. `cash_status` is derived on read as `not_counted`, `balanced`, `short`, or `over`. `closing.confirm@1` closes the day for `balanced`, `short`, and `over` after an explicit token. `not_counted` cannot close. There is no reopen, no tolerance, and no exception acceptance (ADR-018). `closing.prepare@1` is a pure read.

The merchant still has to know which command to type. PRD Build A §2 and §7.8, and PRD v0.11 §10.2 and §17.2, describe WorkItems and a Next Best Action. Build A v1.0 and the implemented close contract win wherever v0.11 assumes pending payment, OutcomeRun, or a general exception engine. `workflow` and `memory` schemas stay absent. The table lives in `operations`.

Hoy already downloads today's sales export. Inicio already renders `daily_close_preparation@1` with `closing.request@1` labeled "Cerrar el día". Cash capture has no button; the merchant says an amount.

## Goals / Non-Goals

**Goals:**

- Persist what Daily Close work remains, why, who acts, which day it affects, and what resolved it.
- Tell the merchant one deterministic next action without a new execution path.
- Keep short/over closable exactly as ADR-018 specifies.
- Initialize WorkItems for an already-open current day without an Alembic data backfill.

**Non-Goals:**

- OutcomeRun, Source Coverage, Event Memory, WorkAbsorptionRecord, Build B exceptions, dismiss, assignment, push, or a task manager.
- Any WorkItem the current rows cannot both create and resolve.
- A stored Next Best Action, model-authored copy, or a second mutation API.

## Decisions

### 1. WorkItem types

Exactly three:

| type | meaning |
|---|---|
| `cash_count_required` | Today's open day has at least one confirmed sale and no current `CashCount`. Close is impossible until a count exists. |
| `cash_difference_review` | A current count exists and derived `cash_status` is `short` or `over`. This is the review the merchant should see before confirming. It does not prohibit close. |
| `close_confirmation_required` | A current count exists and derived `cash_status` is `balanced` only. |

`payment_required` is excluded. `Payment.status` is only `recorded`. Commit writes that payment in the same transaction as `confirmed`. `ready_to_charge` keeps `operational_day_id` NULL and the close spec says an open or `ready_to_charge` session must not block confirmation. A payment WorkItem would not change Daily Close readiness.

Short or over MUST NOT also create `close_confirmation_required`.

No inventory, replenishment, purchasing, supplier, forecast, reminder, CRM, review-queue, or sync-repair type.

### 2. Fields

`operations.work_items`:

- `id` UUID primary key, UUIDv7
- `business_id` UUID NOT NULL
- `operational_day_id` UUID NOT NULL
- `type` as above
- `status` `open` or `resolved`
- `priority` `critical`, `high`, or `normal`, constrained to the type
- `responsible_party` `business` for every v1 row
- `reason_code` constrained to the type
- `source` constant `daily_close_rule`
- `evidence` JSON object of structured facts, never title or reason prose
- `created_at`, `updated_at` `timestamptz` UTC
- `resolved_at` `timestamptz` NULL while open
- `resolution_actor_type` NULL while open; `business` or `system` when resolved
- `resolved_by_actor_id` UUID NULL while open, and NULL when `resolution_actor_type` is `system`
- `resolution_code` NULL while open

No `surfaced_at`. A later instrumentation slice may record an impression if evidence shows it is needed. This slice does not persist that a GET rendered a row. No `expires_at`. No `outcome_run_id`. No assignee. No dismiss reason.

`priority` and `responsible_party` are stored so the row answers them without a join, and CHECK constraints stop them drifting from `type`:

- `cash_count_required` → `critical`, `reason_code=cash_count_missing`
- `cash_difference_review` → `high`, `reason_code` `cash_short` or `cash_over`
- `close_confirmation_required` → `normal`, `reason_code=close_confirmation_required`

`status=open` requires `resolved_at`, `resolution_actor_type`, `resolved_by_actor_id`, and `resolution_code` all NULL. `status=resolved` with `resolution_actor_type=business` requires `resolved_at`, `resolved_by_actor_id`, and `resolution_code` all set. `status=resolved` with `resolution_actor_type=system` requires `resolved_at` and `resolution_code` set and `resolved_by_actor_id` NULL.

Evidence shapes, decimal strings, business currency:

- `cash_count_required`: `currency`, `expected_cash`, `sale_count`, `cash_status=not_counted`
- `cash_difference_review` and `close_confirmation_required`: those fields plus `counted_cash`, signed `cash_difference`, `cash_status`, `cash_count_id`

Money in evidence uses the same decimal-string-plus-currency JSON as the rest of the API when projected. The stored JSON keeps amount strings and one currency field. The projector, not Flutter, formats `$94.00` and `-$14.00`.

### 3. Lifecycle states used now

Only `open` and `resolved`.

PRD v0.11 also lists `assigned`, `in_progress`, `waiting`, `dismissed`, `expired`, and `failed`. None of those have a Build A actor or timer. They are not columns and not API values.

### 4. Identity and deduplication

One open row per `(business_id, operational_day_id, type)`, enforced by partial unique index `uq_work_items_one_open` WHERE `status='open'`.

A repeated sale or cash count that keeps the same desired type updates that open row's `evidence`, `reason_code` (short versus over), and `updated_at`. It does not insert another open row. A Next Best Action read never writes.

### 5. Reopen versus new generation

Do not reopen. A resolved row is immutable.

If the condition becomes true again, insert a new row with a new id. The partial unique index allows many resolved rows and only one open row. `created_at` orders the generations. No generation counter.

The only product path that returns is `cash_difference_review`: a balanced recount resolves it, and a later short or over recount inserts a new open row. A current cash count is never deleted, so `cash_count_required` does not return. A closed day is never reopened, so `close_confirmation_required` does not return.

While a difference row stays open, short flipping to over (or the reverse) updates `reason_code` and `evidence` on that same id.

### 6. Generation predicates

Sync considers only the OperationalDay whose `business_date` is today in the business timezone. Older open days are left untouched. This matches close, which only confirms today.

Let `sale_count` be confirmed sessions on that day, and let `cash_status` be the existing `cash_status_for(counted − expected)` using the current count (`superseded_by_id IS NULL`). `expected` is `summarize_day.cash_total`.

Desired open set:

The desired open set has at most one type:

- No day, `sale_count < 1`, or `status=closed`: empty. A product day is created only by a confirming commit, so `sale_count < 1` on an open day is not a merchant path; sync still treats it as nothing to close.
- Open day, `sale_count` at least 1, no current count: `{cash_count_required}`.
- Current `cash_status` `short` or `over`: `{cash_difference_review}` only. Do not also open `close_confirmation_required`.
- Current `cash_status` `balanced`: `{close_confirmation_required}`.

The LLM does not choose membership.

### 7. Resolution predicates

- `cash_count_required` resolves when a current count is inserted. `resolution_code=cash_count_recorded`. `resolution_actor_type=business`. `resolved_by_actor_id` is the authenticated counter. That same transaction then inserts either `close_confirmation_required` (balanced) or `cash_difference_review` (short or over).
- Short or over, then a recount or a later cash sale makes status `balanced`: resolve `cash_difference_review` with `resolution_code=cash_balanced`, `resolution_actor_type=system`, `resolved_by_actor_id` NULL, and insert `close_confirmation_required`. The merchant did not execute a distinct "resolve difference" command. The desired set recomputed.
- Short flips to over, or over to short, while the day stays open: update `reason_code` and `evidence` on the same open `cash_difference_review` row. Do not resolve it.
- Short or over, then `closing.confirm@1` succeeds: resolve that `cash_difference_review` with `resolution_code=day_closed`, `resolution_actor_type=business`, and the confirmer's actor id. No `close_confirmation_required` row is required to have existed.
- Balanced, then close succeeds: resolve `close_confirmation_required` with `day_closed` and `resolution_actor_type=business`.
- Balanced, then a later sale or recount makes status `short` or `over`: resolve `close_confirmation_required` with `resolution_code=cash_unbalanced`, `resolution_actor_type=system`, `resolved_by_actor_id` NULL, and insert `cash_difference_review`.

There is no "accept difference" resolution. The merchant reviews the difference, recounts until balanced, or closes with the difference still visible on the `ClosingSnapshot`. A read must not be stored as the resolver.

Resolved rows are not deleted.

### 8. Synchronization strategy

Transition-driven only. The same desired-set function runs inside the write that changed the facts:

- successful `sale.commit@1`
- successful insert of a new current `CashCount`
- successful `closing.confirm@1`

`GET /api/v1/operational-days/current/next-best-action` and `operational_day.next_best_action@1` are pure reads. They must not insert, update, or resolve a WorkItem, and must not write audit, outbox, idempotency, or `surfaced_at`. `closing.prepare@1`, `operational_day.summary@1`, and sales export stay pure reads as well.

A no-op sync inside a write does not bump `updated_at` and does not write audit.

### 9. Transaction boundaries

Sync runs inside the caller's transaction and commits or rolls back with it:

- Successful `sale.commit@1`, after the day is attached and the payment exists, before idempotency completes. Replay and confirmed read-back return before this hook.
- Successful insert of a new current `CashCount`. The equal-amount read-back that writes no count does not sync.
- Successful `closing.confirm@1`, after `status=closed`. This pass only resolves the open row for that day. It must not insert a WorkItem.

The Next Best Action query only selects. It has no write transaction of its own.

### 10. Migration

Alembic `0010_work_items`, `down_revision` `0009_catalog_price_override`.

Composite foreign key `(operational_day_id, business_id)` → `operations.operational_days (id, business_id)`, same pattern as `cash_counts`. `ENABLE` and `FORCE` ROW LEVEL SECURITY. Policy `tenant_isolation` on `business_id`. `lumo_app` receives `SELECT`, `INSERT`, `UPDATE`, and `DELETE`. Product code does not delete rows; `DELETE` exists so test reset can remove them before the day.

No `workflow` schema. No backfill. Downgrade aborts if any `work_items` row exists; otherwise it drops only that table.

### 11. Existing-day initialization

The migration inserts nothing. FastAPI startup does not scan tenants: `lumo_app` has no `BYPASSRLS`, and `FORCE` RLS hides every business until `app.current_business_id` is set. This slice does not grant `BYPASSRLS` and does not hide initialization inside a GET.

Deploy runs an application command after `alembic upgrade` and before serving traffic. It uses `DATABASE_ADMIN_URL` (`lumo_admin`), not a public route and not the request path. In one transaction it disables RLS only on `identity.businesses`, reads business ids and timezones, then enables and forces RLS again before commit. PostgreSQL rolls that DDL back if the transaction fails. For each business it then opens a transaction, sets `app.current_business_id` to that id, and runs the same desired-set function for the open OperationalDay whose date is today in that timezone. It skips closed days and older open days.

The command inserts only missing open WorkItems. The partial unique index makes a second run insert nothing. It does not modify sales, cash counts, closing snapshots, outbox, or idempotency. Each actual insert writes `work_item.created` with `audit.actor_id` NULL and `after_payload.origin` `rollout_bootstrap`. `route_or_tool` is `work_item.bootstrap`. A repeated run that inserts nothing writes no audit.

A pre-0010 day that is already closed, or an older day that is still open, gets no WorkItems. If the command is skipped, an open today stays without WorkItems until the next successful commit, new cash count, or close. Those writes still sync. A close that happens before any sync resolves zero rows and inserts none.

### 12. Next Best Action is derived

No `next_best_actions` table. The action is the open WorkItem with the best priority, projected at read time. Durable NBA history would copy facts the WorkItem row already stores. `outcome_type` on the projection is the constant `daily_close_ready`. It is not a column.

### 13. Priority order

Sort open rows by this fixed rank and return one:

1. `cash_count_required` (`critical`) — `not_counted` cannot close.
2. `cash_difference_review` (`high`) — the merchant should see the shortage or overage before confirming. Close remains allowed.
3. `close_confirmation_required` (`normal`) — the current count is balanced.

A healthy day has one open row, so the rank is a tie-break if bad data ever leaves two. Short or over is only the difference row. Its action is still `closing.request@1`, and close stays allowed. A recommendation cannot outrank these rows because this slice has no recommendation type.

`pending_count` is the number of open WorkItems on today's day. After a successful sync that count is 0 or 1: one when sales exist and the day is open, zero when there is no day, no confirmed sales, or the day is closed.

### 14. Responsibility

`responsible_party` is `business` for every v1 type. The merchant counts, reviews, and confirms. Lumo surfaces the work and does not act. No operator, team, or user assignment.

### 15. Expiration

No timer. A row stops being actionable when it is resolved. `expires_at` is omitted from the table and returned as JSON `null` on the projection so a later contract can add it without pretending a deadline exists now.

### 16. Dismiss

Not a status, not an API, not a gesture. A WorkItem is the workflow fact, not a notification.

### 17. `payment_required`

Excluded. See decision 1.

### 18. Short and over

Unchanged close guards. `balanced`, `short`, and `over` may close after the existing token. `not_counted` may not. Balanced does not auto-close. No tolerance, approval, correction, or exception acceptance.

The difference row is the one pending job: review the visible amount, recount if desired, or continue through the existing explicit confirmation. It does not mean a second close WorkItem is also open. The confirm path still stores the signed difference on the snapshot.

### 19. API and tool

One application query, two transports:

- `GET /api/v1/operational-days/current/next-best-action` for Hoy. Authenticated tenant. No idempotency header. `404` is not used for "no day"; the body carries a null action.
- Tool `operational_day.next_best_action@1` for conversation. Empty input. `side_effect=read`. `requires_idempotency=false`. Permission `sale.create`, same as the day summary, so seeing the action is not confirming the close. Policy `NBA-001` allows only an empty argument object and denies a model-supplied id, type, priority, or amount. The tool must not write.

Hoy cannot call a tool without a message, and chat should not require Hoy. Both call the same query. There is no WorkItem collection API.

GET body:

```json
{
  "operational_day_id": null,
  "day_status": null,
  "pending_count": 0,
  "next_best_action": null
}
```

`pending_count` is the number of open WorkItems already stored for today's day. The read does not sync first. `day_status` is `open`, `closed`, or `null`. Normal counts are 1 for an open day with sales and 0 otherwise.

When an action exists, `next_best_action` carries `work_item_id`, `operational_day_id`, `outcome_type`, `type`, `title`, `reason`, `expected_result`, `priority`, `responsible_party`, `evidence`, `risk`, `reversible`, `expires_at`, `status` (`open`), and `actions`. GET `actions` are `{ "action_id": "closing.request@1" }` with no token. The GET must not mint a confirmation token.

### 20. WorkItem list API

No. v1 shows one action and a count. History stays in the table for tests and later memory. No merchant history endpoint.

### 21. Primary surface

Hoy, above the existing export panel, inside the current 420px column and existing card styles:

- Label `Próximo paso` when `next_best_action` is not null.
- Server `title` and `reason`.
- `1 pendiente` when `pending_count` is 1. A short or over day is one job, so the line is not `2 pendientes`.
- The export card unchanged underneath.

No task list, chart, hero metric, or closing-flow screen. Memoria and Negocio stay as they are. Hoy refetches when the tab becomes visible.

### 22. Generative UI

Register `next_best_action` version `1` for the Inicio answer to the closed pending-work phrases. The backend sends the declarative contract only. `fallback_text` is `title` plus a space plus `reason`.

Hoy does not render that component. It binds the GET fields. The field meanings match.

### 23. Action ids

No new id.

- `cash_count_required`: `actions` empty. No amount field and no count button. Capture stays the existing cash-count phrases on Inicio.
- `cash_difference_review` and balanced `close_confirmation_required`: the Inicio card includes exactly `closing.request@1`, which already advances to the confirm token. It must not include `closing.confirm@1`. The difference card does not accept an exception; the button starts the same request-close handler.
- Hoy, when `actions` contains `closing.request@1`, shows the existing label `Cerrar el día`, switches to Inicio, and sends the existing phrase `cerrar el día` on the shell `conversation_id`. Hoy does not post `/api/v1/lumo/actions` and does not put a token on the GET. Export buttons still do not post actions.

`risk` and `reversible` are fixed:

- `cash_count_required`: `blocks_close`, `reversible=true`
- `cash_difference_review`: `visible_difference`, `reversible=true`
- `close_confirmation_required`: `requires_confirmation`, `reversible=false`

### 24. Conversation

After the existing phrase normalizer, only these exact strings select `intent=next_best_action` and `operational_day.next_best_action@1`: `que sigue`, `que falta`, `que tengo pendiente`, `que sigue con el cierre`, `que falta para cerrar`, `que falta para el cierre`, and `que tengo pendiente para cerrar`. Matching is exact. `que sigue con el cierre por favor` stays unsupported. Matching runs with the other closed operational phrases, before product parsing. There is no free-form NLU.

`preparar el cierre` and `ventas de hoy` stay on their current tools and do not attach this card. No proactive push. When there is no action, `text` is `No hay un paso pendiente para el cierre de hoy.` and `ui` is empty. That sentence must not claim that every sale is known.

Assistant `text` for an action equals `fallback_text`. The orchestrator must not replace amounts or priority with model prose.

### 25. Copy

Templates, server-side, using the existing `$` plus decimal-string formatter. Absolute value only inside the short/over titles. Evidence keeps the signed difference.

- Missing count title: `Cuenta el efectivo para continuar con el cierre.`
- Missing count reason: `Esperamos $94.00 en efectivo y todavía no hay un conteo.`
- Missing count expected result: `Un conteo de efectivo queda registrado para esta jornada.`
- Balanced title: `La caja está cuadrada. El siguiente paso es cerrar la jornada.`
- Balanced reason: `El efectivo contado coincide con los $94.00 esperados de las ventas registradas en Lumo.`
- Balanced expected result: `La jornada queda cerrada.`
- Short title: `Hay un faltante de $14.00. Revisa la diferencia antes de confirmar el cierre.`
- Over title: `Hay un sobrante de $10.00. Revisa la diferencia antes de confirmar el cierre.`
- Short or over reason: `El conteo es $80.00 y las ventas registradas en Lumo esperan $94.00 en efectivo.`
- Short or over expected result: `Puedes volver a contar o confirmar el cierre con esta diferencia visible.`

The words "ventas registradas en Lumo" are required wherever the sentence talks about expected cash. Do not say that all sales are complete.

### 26. Audit

On an actual insert: audit action `work_item.created`. On an actual resolve: `work_item.resolved`. Same transaction as the row change. The resolve payload includes ids, type, status, reason_code, evidence, `resolution_code`, and `resolution_actor_type`. It includes `resolved_by_actor_id` only when that type is `business`. Bootstrap inserts use `actor_id` NULL and `origin=rollout_bootstrap`. No model reasoning. No audit for an evidence-only refresh. Reads write no audit.

### 27. Outbox

No WorkItem event. Nothing consumes one in Build A. Sale, cash-count, and `closing.confirmed` events stay as they are. A later slice can add `work_item.opened` and `work_item.resolved` if a consumer exists.

### 28. Idempotency

The Next Best Action read requires no key and writes no idempotency row. Sync inside commit, cash count, and confirm inherits those operations' keys: a replay returns the stored body and does not sync again. The bootstrap command has no idempotency table row; the partial unique index is its idempotency. No `lumo.message.sync_work_items` operation.

### 29. OutcomeRun later

Rows point at `operational_day_id` and `type` only. The next slice may add a nullable `outcome_run_id` and backfill by day without rewriting ids, status, or resolution history. This slice must not insert OutcomeRun rows. The projection's `outcome_type` constant is the temporary semantic.

`created_at`, `resolved_at`, `resolution_actor_type`, and `resolved_by_actor_id` remain for a later slice. This slice does not add `surfaced_at` or a WorkAbsorptionRecord. No metrics table.

### 30. Closed day and no-sales day

Closed today: the confirm transaction already resolved the open row. A later read inserts nothing, the projection is null, and `pending_count` is 0. Historical resolved rows remain.

No day today: insert nothing, projection null, `pending_count=0`.

Open day with zero confirmed sales: desired set empty, projection null.

### 31. ADR-023

Accepted by this change. Implementation writes `docs/adr/ADR-023-work-items-next-best-action.md` and does not edit ADR-015 through ADR-022.

Decision to record:

WorkItems are transition-maintained durable responsibility. Next Best Action reads are pure projections: they never reconcile and never persist, including no `surfaced_at`. Identity is one open row per business, day, and type; a returned condition inserts a new generation. Only `open` and `resolved` exist. Short or over has one active `cash_difference_review`, not a simultaneous close item. Priority if more than one row is ever present is `cash_count_required`, then `cash_difference_review`, then `close_confirmation_required`. Direct resolutions (cash count clears the count item; close clears the open difference or close item) record `resolution_actor_type=business` and the authenticated actor. Derived recomputation records `system` and a null actor id. Responsibility for the open job is `business`. Scope is today's Daily Close. The row belongs to `OperationalDay` through a composite foreign key. `outcome_run_id` waits for the next slice. Migration `0010` does not backfill. A deploy command initializes open today only, with bootstrap audit and no merchant endpoint. Audit is create and resolve only. There is no WorkItem outbox event. Hoy shows one action and a count. The model cannot set priority or amounts.

### Directory placement

- `backend/app/domain/operations/work_item.py` — entity, desired-set function, copy is not in the domain
- `backend/app/application/workflows/sync_daily_close_work_items.py` — desired-set sync used by commit, cash count, close, and the deploy initializer
- `backend/app/application/queries/get_next_best_action.py` — projection and Spanish templates
- repository methods beside the existing operations persistence
- domain must not import FastAPI, SQLAlchemy, or the LLM SDK

## Risks / Trade-offs

- [Deploy command is skipped] → Open today has no WorkItem until the next commit, new count, or close. The command is idempotent and can be run again. Reads stay empty rather than repairing themselves.
- [Admin bootstrap lists businesses] → RLS on `identity.businesses` is disabled only inside that listing transaction and forced back on before any WorkItem write. Each write sets that business's GUC. No `BYPASSRLS` grant.
- [Hoy close button sends a phrase] → It reuses `cerrar el día` so Hoy does not mint tokens. The confirm card still appears on Inicio.
- [Cash count has no button] → There is no safe action that captures an amount. The screen says what is missing; the existing utterance records it.
- [Evidence refresh is not audited] → The cash-count chain and payments remain the amount history. Audit records birth and resolution.
- [Past open days stay invisible] → Close itself only operates on today. Backfilling yesterday would invent a workflow the product cannot finish from Hoy.

## Migration Plan

1. Deploy `0010_work_items`. The upgrade inserts no rows.
2. Run the application initializer once before serving traffic. It fills open today only.
3. Downgrade aborts while any WorkItem exists. After a deliberate empty, it drops only `operations.work_items`.
4. Rollback of the app without downgrade leaves an unused table. Old code does not read it.

## Open Questions

None. Decisions 1–31 are closed for implementation.
