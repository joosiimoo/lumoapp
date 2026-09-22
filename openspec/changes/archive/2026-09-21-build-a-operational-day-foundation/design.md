## Context

`build-a-sale-payment-and-completion` is archived. A confirmed `SaleSession` plus its `SaleItem`s and exactly one `sales.payments` row is the durable completed sale. Lifecycle is `open` → `ready_to_charge` → `confirmed`. `sale.commit@1` locks the session, inserts the payment, sets `confirmed`, and writes audit, `sale.confirmed`, `payment.recorded`, and `lumo.message.commit_sale` in the request transaction that `get_db` commits. There is no `confirmed_at`. `updated_at` moves on every write. Schema `operations` does not exist.

`identity.businesses.timezone` already exists (`VARCHAR(64) NOT NULL`). The Carrota seed is `America/Mexico_City`. Currency is `businesses.currency` (`MXN` for Carrota). The domain does not read that timezone today.

Authority for this slice: PRD §7.7 and §8.3, SRS RF-A-042 and RF-A-060, Architecture §10.1–10.2 and §11.4. PRD v0.11’s richer `OperationalDay` (stored totals, completion, coverage) is vision and is not copied. ADR-015 left OperationalDay out of payment completion. ADRs 001–015 stay accepted.

Inspection constraints:

- Alembic head revision id is `0004_confirmed_payment`. The file is `0004_sale_session_confirmed_payment.py`. Those strings are not interchangeable. Next revision id is `0005_operational_day` with `down_revision = "0004_confirmed_payment"`.
- Databases at that head can already contain `confirmed` `SaleSession` rows. `0004` added the status and `sales.payments`. There is no `confirmed_at` yet, so those rows have neither membership field.
- Money columns in `sales` are `numeric(12,2)`. Summaries stay on that scale. Do not introduce `numeric(19,4)` only here.
- RLS is `ENABLE` + `FORCE` and `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`. `business_id` is copied from `TenantContext`, never from the client.
- The scripted interpreter matches trimmed, case-insensitive exact phrases. It has no repository access.
- Flutter Inicio holds one stable `conversation_id`. Hoy, Memoria, and Negocio are placeholders. Design System §10 Hoy (chart, cash state, “Preparar el cierre del día”) is not this slice.
- `sale.commit` in Architecture §10.2 step 7 is “actualiza jornada”. That step was deferred by ADR-015 and is this change. Steps that re-read catalog price, create WorkItems, or evaluate close gates stay deferred.
- SRS §7.2 continues `open` → `in_progress` after a confirmed sale. This slice does not own the workflow engine, so that transition is not implemented. See Decisions.

## Goals / Non-Goals

**Goals:**

- Lumo can answer, from confirmed sales, how many sales were completed on the current business date, the gross total, and the cash / card / transfer split.
- Day membership is deterministic, frozen at confirmation, tenant-scoped, and safe for a later Daily Close to trust.
- Flutter and the interpreter only display or request that summary. They do not calculate it.

**Non-Goals:**

- Daily Close and every closing, cash-count, reconciliation, exception, outcome, work-item, and export behavior listed in the proposal.
- Any OperationalDay status other than `open`.
- A Hoy screen, charts, history, or weekly/monthly aggregates.
- Changing payment shape, sale status machine, or the active-session unique index.

## Decisions

### 1. OperationalDay entity

Table `operations.operational_days`:

| Column | Type | Rule |
|---|---|---|
| `id` | UUIDv7 | PK |
| `business_id` | UUID | tenant; copied from `TenantContext` |
| `business_date` | `DATE` | local calendar date, not a timestamp |
| `status` | text | CHECK `open` only |
| `timezone` | `VARCHAR(64)` | IANA name copied from `identity.businesses.timezone` at insert |
| `created_at` / `updated_at` | `timestamptz` | `created_at` is the open instant. Runtime: the insert instant. Backfill: `MIN(legacy_confirmed_at)` for that day, not the migration clock |

Also `UNIQUE (business_id, business_date)` and `UNIQUE (id, business_id)` so the sale FK can include `business_id`.

No `opened_at` (it would duplicate `created_at`), no `opened_by` (the actor is on the `operational_day.opened` audit row), no stored `sales_total` / `payments_total`, no version column. Sale sessions already serialize with row locks; the day uses the unique key, not optimistic version.

`not_started` is the absence of a row. Closing and intermediate workflow states from PRD §8.3 / SRS §7.2 are not stored. A day that has confirmed sales remains `open` until a future change owns the workflow engine.

Domain type lives in `backend/app/domain/operations/` and MUST NOT import SQLAlchemy, FastAPI, or Flutter. The SQLAlchemy row stays in `backend/app/infrastructure/persistence/models.py`, matching existing tables. Repository methods live in `backend/app/infrastructure/persistence/operations.py` behind an application port. The summary query may join `sales.sale_sessions` and `sales.payments` from infrastructure. Domain code does not.

### 2. Business date and timezone

Runtime membership clock is a new `sales.sale_sessions.confirmed_at timestamptz`, set once on the `ready_to_charge` → `confirmed` transition from one injectable UTC clock reading. Runtime MUST NOT use `created_at` or `updated_at`. `updated_at` is allowed only as the migration-time approximation for rows that were already `confirmed` before `0005` (decision 12).

Timezone source is `identity.businesses.timezone` for the authenticated business. The domain MUST NOT hardcode `America/Mexico_City` or Carrota. Carrota gets Mexico local dates only because its seeded zone is `America/Mexico_City`.

Rule, evaluated in application code with stdlib `zoneinfo` (no new dependency):

```text
business_date = confirmed_at.astimezone(ZoneInfo(business.timezone)).date()
```

`confirmed_at` MUST be timezone-aware UTC. Conversion from UTC to a zone is unambiguous, including across DST transitions. Do not convert a naive timestamp, and do not use the PostgreSQL session `TimeZone` or the device timezone.

Midnight: the local calendar day is `[00:00:00.000000, next 00:00:00.000000)`. For `America/Mexico_City` (UTC−6, no DST):

- `2026-09-22T05:59:59Z` → business date `2026-09-21`
- `2026-09-22T06:00:00Z` → business date `2026-09-22`

A session started before local midnight and confirmed after it belongs to the confirmation date. Same-key replay does not recompute or move it.

If `business.timezone` is not a valid IANA name, the commit transition MUST fail and the request transaction MUST roll back. No payment, no day, no `confirmed`.

The day’s `timezone` column is a snapshot of the zone used to create that date. This change does not support changing a business timezone mid-day. Later confirms recompute the date from the current business timezone and attach to the row for that date if it exists.

The summary’s “today” uses the same function on the application clock (`now`), not on a client date.

### 3. Sale membership is a foreign key, not a derivation

On the confirming transition only, set:

- `confirmed_at`
- `operational_day_id`

`open` and `ready_to_charge` MUST keep both NULL. PostgreSQL CHECK:

```text
(status = 'confirmed' AND operational_day_id IS NOT NULL AND confirmed_at IS NOT NULL)
OR
(status IN ('open', 'ready_to_charge') AND operational_day_id IS NULL AND confirmed_at IS NULL)
```

Foreign key `(operational_day_id, business_id)` → `operational_days (id, business_id)`. `MATCH SIMPLE` allows NULL `operational_day_id` on active sessions.

Rejected: derive the day at read time from `updated_at`. That column is not the runtime confirmation clock. The only use of `updated_at` is the one-time `0005` backfill below. Rejected: a join table. One sale belongs to one day. Rejected: store only `business_date` on the sale. The FK is the association RF-A-042 and Architecture §10.2 step 7 ask for, and Daily Close can lock the day without re-deriving membership.

`uq_sale_sessions_active_context` stays `WHERE status IN ('open', 'ready_to_charge')`. Do not add `confirmed` to it.

### 4. sale.commit ensures the day

Only the `ready_to_charge` → `confirmed` transition ensures the day. Replay, different-key read-back, clarify, and deny paths MUST NOT insert a day.

Inside the existing commit write transaction, after `SELECT … FOR UPDATE` on the session and after the payment amount is calculated, before `get_db` commits:

1. Read `business.timezone` and `business.currency` for `TenantContext`.
2. Set `confirmed_at` from one application clock reading (injectable in tests).
3. Compute `business_date`.
4. Ensure the day (decision 5).
5. Insert the one `Payment` (unchanged rules).
6. Set `status=confirmed`, `operational_day_id`, `confirmed_at`.
7. Audit `sale.commit@1` with `operational_day_id`, `business_date`, and `confirmed_at` in `after_payload`.
8. If this transaction inserted the day: audit `operational_day.opened` and enqueue outbox `operational_day.opened`.
9. Enqueue `sale.confirmed` (payload gains `operational_day_id`) and `payment.recorded` (unchanged).
10. Complete `lumo.message.commit_sale`.

Success and `sale_confirmed@1` stay post-commit. The orchestrator still does not open the transaction. `sale.start@1` and `sale.totalize@1` do not create a day. An abandoned draft is not “what happened today.”

### 5. Concurrency and uniqueness

Ensure is:

```text
INSERT … ON CONFLICT (business_id, business_date) DO NOTHING RETURNING id
```

If `RETURNING` is empty, `SELECT` the existing row for that pair. Write `operational_day.opened` audit and outbox only when `RETURNING` produced the new id.

Two concurrent first commits of different sessions block on the unique index. One inserts. The other attaches to that id after the winner commits, or becomes the inserter if the winner rolls back. PostgreSQL rechecks `ON CONFLICT` after the competing transaction ends, so a rollback does not leave the loser with `DO NOTHING` and no row. Do not catch a unique violation in a way that aborts the whole transaction.

Same-session double commit stays serialized by `FOR UPDATE` on `sale_sessions`, as today. Same-key replay returns the stored body and does not insert a second day or a second association.

### 6. Summary aggregation

`operational_day.summary@1` is a read. Repository SQL, `Decimal` / `numeric`, no binary float:

- Count confirmed sessions with that `operational_day_id`.
- `gross_sales_total` = `SUM(payments.amount)` for the recorded payment of those sessions.
- `cash_total` / `card_total` / `transfer_total` = the same sum filtered by `method`.
- Empty sums are `0.00`, not NULL.
- Quantize to two decimal places with the existing money helper.
- Currency is `business.currency`.
- Exclude `open` and `ready_to_charge`.
- Do not sum `line_total`s. Payment amount is already the sale total.

`gross_sales_total` MUST equal the three method totals. If a payment currency differs from the business currency, the read MUST fail with no partial totals.

No day row: return `operational_day_id=null`, `status=null`, `sale_count=0`, all totals `0.00`, and `business_date` = today. Do not insert. A second read still inserts nothing. If a sale commits between two reads, the second read includes it. The message `Idempotency-Key` is still required by the endpoint, but this read MUST NOT write `idempotency_records`, audit, or outbox. It is not a frozen snapshot.

### 7. Tool, policy, and phrases

Register `operational_day.summary@1` (Architecture name `operational_day.summary`, versioned like the other tools). Permission `sale.create` (the merchant permission that already exists; SRS has no separate operations-read permission). `side_effect=read`. `requires_idempotency=false`. Input is an empty object. Output is the summary payload. Do not register `operational_day.get`, `closing.*`, or `export.*`.

Policy `DAY-001`: the tool is allow only as a registered read. Client or model totals, counts, and dates are not inputs and MUST NOT be persisted. `SEC-002` still denies `closing.confirm@1`.

Interpreter, before product parsing and after payment/totalize matching: NFKD, strip combining marks, lowercase, collapse whitespace, strip one surrounding layer of `¿?¡!`. Exact set:

- `como vamos hoy`
- `ventas de hoy`
- `cuanto vendimos hoy`

Those map to `intent=day_summary`, `candidate_tool=operational_day.summary@1`. `¿Cómo vamos hoy?` matches. `ventas de hoy por favor` does not. `ventas de la semana`, `ventas de ayer`, and `cómo vamos` follow the existing unsupported clarification, create no day, and emit no summary card.

The orchestrator routes `day_summary` to a read workflow. The interpreter still has no repository access.

### 8. Generative UI

Component `operational_day_summary` version `1`. `actions` is empty. No close button, difference, expected cash, chart, or product list. `text` MUST equal `fallback_text`.

```json
{
  "component": "operational_day_summary",
  "version": 1,
  "data": {
    "operational_day_id": null,
    "business_date": "2026-09-21",
    "status": null,
    "currency": "MXN",
    "sale_count": 0,
    "gross_sales_total": {"amount": "0.00", "currency": "MXN"},
    "cash_total": {"amount": "0.00", "currency": "MXN"},
    "card_total": {"amount": "0.00", "currency": "MXN"},
    "transfer_total": {"amount": "0.00", "currency": "MXN"}
  },
  "actions": [],
  "fallback_text": "Hoy 2026-09-21 · 0 ventas · $0.00 · Efectivo $0.00 · Tarjeta $0.00 · Transferencia $0.00"
}
```

When a day exists, `operational_day_id` is that UUID and `status` is `open`. One sale uses `1 venta`; any other count uses `N ventas`. Method labels in the sentence are `Efectivo`, `Tarjeta`, `Transferencia`. Amounts are the server decimal strings.

Flutter maps the card on the existing Inicio stream (Lumo mark, soft card, max-width 420). It may format the ISO `business_date` for display and MUST NOT recompute the calendar day from the device zone. It MUST NOT add method totals to check or replace `gross_sales_total`. Hoy stays a placeholder. Do not wire “Preparar el cierre del día”.

`sale_confirmed@1` stays the per-sale card. This summary is a different component.

### 9. RLS, audit, outbox, idempotency

`operations.operational_days`: ENABLE and FORCE RLS, policy `tenant_isolation`, grants `SELECT, INSERT, UPDATE, DELETE` to `lumo_app`, matching `sales.payments`.

Business B’s summary and selects MUST NOT see Carrota’s day or totals. A zero summary for B is B’s own today, not Carrota’s numbers.

Audit / outbox when **runtime** `sale.commit@1` inserts a day:

- action `operational_day.opened`
- event `operational_day.opened` with `operational_day_id`, `business_date`, `timezone`, `status`

Reusing a day writes neither. Days inserted by the `0005` backfill write neither, and they do not write `sale.commit` audit, `sale.confirmed`, or idempotency rows. The sale’s own runtime `sale.commit@1` audit and `sale.confirmed` payload still carry `operational_day_id`. Reads write nothing.

Same-key commit replay is the existing idempotency peek. It does not create a second day. A failed commit rolls the new day back with the payment. A day inserted by an earlier committed sale is untouched when a later sale rolls back.

### 10. Cleanup

`clear_tenant_sale_mutations` MUST, in one transaction, delete payments, items, and sessions before `operations.operational_days` for that `business_id` (FK), and delete `operational_day.opened` audit and outbox with the existing sale integrity rows. Orphan checks MUST treat a dangling `operational_day_id` as an orphan. Confirmed sessions MUST NOT survive without their day, and a day MUST NOT be deleted while a session still references it.

### 11. ADR-016

Prepare `docs/adr/ADR-016-operational-day-foundation.md` during implementation. Decision: lazy `open` OperationalDay on the first confirmed sale of a business date; membership is `sale_sessions.operational_day_id` from `confirmed_at` in `businesses.timezone`; summary is the read tool `operational_day.summary@1`. Daily Close remains out of scope. Do not rewrite ADR-015.

## Risks / Trade-offs

- [Status stays `open` after sales exist, which is shorter than SRS §7.2] → Recorded as an explicit deferral of the workflow engine. A later change adds transitions without rewriting membership.
- [Summary permission reuses `sale.create`] → No new permission catalog in this slice. The tool is read-only and tenant-scoped. A narrower permission can be added with Daily Close.
- [PRD §7.10 also wants ticket promedio and product mix] → Those are a later consolidated-report change. This card is the minimum “what happened today.”
- [Two first-sale transactions contend on one unique key] → `ON CONFLICT DO NOTHING` plus `SELECT`. One opened event.
- [Business timezone edited later] → Historical `business_date` and FK do not move. New confirms use the new zone. Mid-day edits are unsupported.
- [Read is live, not idempotent-snapshotted] → Correct for “cómo vamos hoy”. Do not store a summary row that can drift.
- [Request transaction commits even for a pure read] → Allowed only when the summary path inserted nothing.
- [Legacy `updated_at` is not a true confirmation clock] → Used once, in `0005` only. Runtime commits write `confirmed_at` from the injectable clock. A backfilled day's `created_at` is the earliest of those approximations for that date, not the migration clock. Backfill does not emit opened events, so a reused historical day stays quiet.
- [UUIDv7 embeds generation time] → `new_uuid7()` has no historical-instant argument. Backfilled ids use it as-is. Readers MUST use `created_at`, not the UUID, for the reconstructed open instant.
- [`lumo_admin` cannot bypass FORCE RLS] → Disable RLS only for the backfill and verification inside the upgrade transaction, then turn FORCE back on before return. The verification query must see every tenant or it can pass while confirmed rows are still NULL.

### 12. Legacy backfill is migration repair, not a runtime event

`0004` already allows `confirmed` sessions. `0005` MUST upgrade a non-empty database. Rows that are already `confirmed` when `0005` runs have no canonical `confirmed_at`.

For each such row only:

```text
legacy_confirmed_at = sale_sessions.updated_at
business_date = business_date_for(legacy_confirmed_at, identity.businesses.timezone)
```

Use that business’s stored IANA timezone. Do not hardcode Carrota or `America/Mexico_City`. If the business row is missing or the timezone is not a valid IANA name, the migration MUST raise and the Alembic transaction MUST roll back to `0004_confirmed_payment`. Do not skip the row and do not invent a zone.

Then, still inside that upgrade:

1. Ensure one `operations.operational_days` row per distinct `(business_id, business_date)`, `status=open`, `timezone` copied from the business. For that group, `legacy_opened_at` is the minimum `legacy_confirmed_at`. Set both `created_at` and `updated_at` to `legacy_opened_at`. The `INSERT` MUST pass those timestamps. It MUST NOT omit them and pick `DEFAULT now()` / `CURRENT_TIMESTAMP` / the migration execution clock. New ids MUST come from the existing `new_uuid7()` helper, which stamps the current millisecond and accepts no historical instant. Do not add a historical-time parameter. The UUID is identity only. `created_at` is the canonical reconstructed open instant.
2. Set that session’s `confirmed_at` to `legacy_confirmed_at` and `operational_day_id` to the matching day.
3. Do not modify `updated_at`, `status`, items, or payments. `updated_at` has no database trigger; the `UPDATE` MUST list only the two new columns.
4. Leave `open` and `ready_to_charge` rows with both new columns NULL.
5. Verify that no `confirmed` session still has a NULL membership field. The verification query MUST see every tenant. If any row fails, raise.
6. Only after that verification, add the membership CHECK, then the composite FK and the `operational_day_id` index.

This backfill MUST NOT insert `operational_day.opened` audit, `operational_day.opened` outbox, `sale.commit` audit, `sale.confirmed` outbox, or idempotency rows, and MUST NOT rewrite existing `sale.confirmed` or `sale.commit@1` rows. Those events belong to runtime `sale.commit` after `0005`. A later commit that finds a backfilled day reuses it and does not emit `operational_day.opened`.

`updated_at` on a confirmed row is only an approximation: this baseline does not rewrite confirmed sessions, so it is the original confirm write in normal data. If something touched `updated_at` after confirm, the backfill follows that later timestamp. Runtime code MUST NOT copy this rule.

Alembic connects as `lumo_admin` (`DATABASE_ADMIN_URL`): `NOSUPERUSER` and `NOBYPASSRLS`. FORCE RLS applies to the table owner, and `identity.businesses` is also forced. A backfill or verification query without `app.current_business_id` sees no tenant rows and can report a false zero. Inside the upgrade transaction, `DISABLE ROW LEVEL SECURITY` on `identity.businesses`, `sales.sale_sessions`, and `operations.operational_days` for the read, insert, update, and verification only. Restore `ENABLE` and `FORCE` on those three tables before the migration function returns. A successful upgrade MUST leave FORCE RLS on. A failure rolls the `DISABLE` back with the transaction.

## Migration Plan

File `backend/migrations/versions/0005_operational_day.py`. Revision id `0005_operational_day`. `down_revision = "0004_confirmed_payment"`.

Upgrade order:

1. `CREATE SCHEMA operations`.
2. Create `operational_days` with the status CHECK, both unique constraints, `business_id` index, ENABLE + FORCE RLS, `tenant_isolation`, and `lumo_app` grants.
3. Add nullable `sales.sale_sessions.operational_day_id`.
4. Add nullable `sales.sale_sessions.confirmed_at`.
5. Backfill existing `confirmed` sessions (decision 12), including the temporary RLS disable and restore.
6. Verify no `confirmed` session has NULL `operational_day_id` or `confirmed_at`, seeing every tenant.
7. Add the membership CHECK.
8. Add the composite FK `(operational_day_id, business_id)` and the index on `operational_day_id`.

Do not create `workflow`, `memory`, `cash_counts`, or `sales.sales`. Do not add `confirmed` to `uq_sale_sessions_active_context`.

Downgrade, still coherent on a database that was backfilled: drop the membership CHECK, drop the composite FK and `operational_day_id` index, drop both columns, drop `operations.operational_days`, drop schema `operations`. Do not delete payments, items, or rewrite session status. Do not invent reversing audit rows. Downgrade discards the backfilled membership; `0004` had no place to store it.

Application and migration ship together. A request that fails after a runtime day insert rolls back through `get_db`. `X-Debug-Fail-After-Write` covers that test. A failed `0005` upgrade rolls back to revision `0004_confirmed_payment`.

## Open Questions

These are decided above so implementation is not ambiguous. Confirm before `/opsx:apply`. If a decision is rejected, change this design and the delta specs first.

1. Persisted status is only `open`. SRS §7.2’s `open` → `in_progress` waits for the workflow engine.
2. The merchant-facing surface is the Inicio card, not the Hoy screen, and the payload omits ticket promedio and product mix.
3. The read tool’s permission is `sale.create`.
