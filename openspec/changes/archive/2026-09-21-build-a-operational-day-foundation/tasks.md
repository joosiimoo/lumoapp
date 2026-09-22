## 1. Domain

- [x] 1.1 Add `OperationalDay` and `OperationalDayStatus` (`open` only) under `backend/app/domain/operations/`. Fields: `id`, `business_id`, `business_date`, `status`, `timezone`, `created_at`, `updated_at`. Domain MUST NOT import SQLAlchemy, FastAPI, or Flutter.
- [x] 1.2 Add `business_date_for(confirmed_at, timezone_name)` using stdlib `zoneinfo`. Require a timezone-aware UTC instant. Unit-test `America/Mexico_City`: `2026-09-22T05:59:59Z` → `2026-09-21`, `2026-09-22T06:00:00Z` → `2026-09-22`. Unit-test that an unknown IANA name fails. Do not hardcode Carrota.

## 2. Persistence and migration

- [x] 2.1 Alembic file `0005_operational_day.py`, revision id `0005_operational_day`, `down_revision = "0004_confirmed_payment"` (not the `0004` filename). `CREATE SCHEMA operations`; table `operational_days` (`id`, `business_id`, `business_date DATE`, `status` CHECK `open`, `timezone VARCHAR(64)`, timestamps); `UNIQUE (business_id, business_date)`; `UNIQUE (id, business_id)`; index on `business_id`; ENABLE + FORCE RLS; `tenant_isolation`; `lumo_app` DML grants matching `sales.payments`. Do not create `workflow`, `memory`, or `cash_counts`.
- [x] 2.2 In that same migration, after the table exists: add nullable `operational_day_id`, add nullable `confirmed_at`, run the legacy backfill, verify every `confirmed` row is attached, then add the membership CHECK, the composite FK `(operational_day_id, business_id)` → `operational_days (id, business_id)`, and the `operational_day_id` index. Do not add the CHECK before the backfill. Do not change `uq_sale_sessions_active_context` or add a total column. Downgrade drops the CHECK, FK, and index, then the two columns, then the table and schema, without deleting payments or items.
- [x] 2.3 Add `OperationalDayRow` and the session columns on the SQLAlchemy models. Add an operations port/repository: `ensure_open_day` (`INSERT … ON CONFLICT (business_id, business_date) DO NOTHING RETURNING id`, else select) and `summarize_day`. Copy `business_id` from `TenantContext`.
- [x] 2.4 Backfill rows already `confirmed` at `0004_confirmed_payment`. `legacy_confirmed_at` is `sale_sessions.updated_at`. Compute `business_date` with `business_date_for` and that business's `identity.businesses.timezone`. Do not hardcode a zone. Fail the upgrade on an invalid timezone. Insert one `open` OperationalDay per distinct `(business_id, business_date)` with a normal `new_uuid7()` (do not add a historical timestamp argument; `created_at` is the open instant, not the UUID) and the timezone snapshot. Set that day's `created_at` and `updated_at` to the minimum pre-upgrade `updated_at` of the legacy confirmed sessions on that date, explicitly in the `INSERT`, not `CURRENT_TIMESTAMP`. Then set each session's `confirmed_at` and `operational_day_id` only. Do not change `updated_at`, status, items, or payments. Leave `open` and `ready_to_charge` NULL. Because `lumo_admin` is `NOBYPASSRLS`, disable RLS on `identity.businesses`, `sales.sale_sessions`, and `operations.operational_days` for the backfill and the all-tenant verification, then ENABLE and FORCE it again before the migration returns. Do not write `operational_day.opened` audit or outbox, `sale.commit` audit, `sale.confirmed`, or idempotency rows.

## 3. Business-date clock

- [x] 3.1 Pass one injectable UTC clock reading into the confirming commit. Read `identity.businesses.timezone` and `currency` for that tenant. Set runtime `confirmed_at` from that clock and compute `business_date` with `business_date_for` before any day or payment insert. Do not use `updated_at`. An invalid timezone MUST raise inside the request transaction so `get_db` rolls it back.

## 4. Sale commit integration

- [x] 4.1 On the `ready_to_charge` → `confirmed` path only, ensure the day, insert the existing `Payment`, then set `confirmed`, `operational_day_id`, and `confirmed_at` while the session row is locked. `sale.start@1` and `sale.totalize@1` MUST NOT create a day.
- [x] 4.2 Include `operational_day_id`, `business_date`, and `confirmed_at` on the `sale.commit@1` audit `after_payload`. Add `operational_day_id` to the `sale.confirmed` outbox payload. When runtime `ensure_open_day` inserted the row, also write audit `operational_day.opened` and outbox `operational_day.opened` (`operational_day_id`, `business_date`, `timezone`, `status`). Reuse, including reuse of a day created by the `0005` backfill, MUST NOT emit `operational_day.opened`.
- [x] 4.3 Same-key replay and different-key confirmed read-back MUST NOT insert a day or change `operational_day_id`. Clarify/deny paths MUST NOT insert a day.

## 5. Summary read path

- [x] 5.1 Implement SQL aggregation for one `operational_day_id`: `COUNT` of `confirmed` sessions, `SUM(payments.amount)` as gross, and filtered sums for `cash`, `card`, and `transfer`. Use `Decimal`, quantize to two places with the existing money helper, and coerce empty sums to `0.00`. Exclude `open` and `ready_to_charge`. Do not sum `line_total`s. Fail the read if a payment currency differs from the business currency.
- [x] 5.2 Add `GetOperationalDaySummary`. Today's date uses the same clock and timezone rule. If no day exists, return `operational_day_id=null`, `status=null`, `sale_count=0`, and `0.00` totals without inserting. The read MUST NOT write audit, outbox, or idempotency rows.

## 6. Tool, policy, and interpreter

- [x] 6.1 Register `operational_day.summary@1`: empty input object, summary output, permission `sale.create`, policy `DAY-001`, `side_effect=read`, `requires_idempotency=false`. Do not register `operational_day.get`, `closing.*`, or `export.*`.
- [x] 6.2 Add `DAY-001` on `FoundationPolicyEngine`: the summary is a registered read; model-supplied counts, totals, or dates MUST NOT be stored. Keep `SEC-002` denying `closing.confirm@1`.
- [x] 6.3 Teach the scripted interpreter the closed set after accent fold, case fold, whitespace collapse, and one surrounding `¿?¡!` layer: `como vamos hoy`, `ventas de hoy`, `cuanto vendimos hoy` → `intent=day_summary`, `candidate_tool=operational_day.summary@1`. Match after payment and totalize and before product parsing. No repository access. `ventas de la semana`, `ventas de ayer`, and `ventas de hoy por favor` stay unsupported and MUST NOT select this tool.
- [x] 6.4 Wire the orchestrator and message route to the read workflow. `day_summary` MUST NOT run the commit or add-item write path.

## 7. Generative UI backend

- [x] 7.1 Register `operational_day_summary@1` and compose it from the summary payload, including the zero summary. `actions=[]`. `text` MUST equal `fallback_text` (`1 venta` vs `N ventas`, ISO date, method labels Efectivo/Tarjeta/Transferencia, server amounts). Refuse `daily_summary_card@1` and `closing_ready_card@1`. Do not add close, difference, or chart fields.

## 8. Flutter

- [x] 8.1 Map `operational_day_summary@1` in `GenerativeUIRenderer` to a compact Inicio `LumoCard` (date, sale count, gross, cash, card, transfer). Format server strings only. Unknown version shows `fallback_text`. No close button, chart, or client addition of method totals.
- [x] 8.2 Keep the same Inicio `conversation_id` when sending `ventas de hoy`. Do not build the Hoy screen and do not wire “Preparar el cierre del día”.

## 9. Integrity, config, and ADR

- [x] 9.1 Extend `sale_cleanup` so one transaction deletes payments, items, and sessions before that tenant’s `operational_days`, plus `operational_day.opened` audit and outbox. Orphan checks MUST flag a dangling `operational_day_id`.
- [x] 9.2 Update `openspec/config.yaml` context: schema `operations` exists; tools include `operational_day.summary@1`; UI includes `operational_day_summary@1`. `workflow` and `memory` stay absent. Do not describe Daily Close as implemented.
- [x] 9.3 Write ADR-016: lazy `open` day on the first confirmed sale, membership via `operational_day_id` from runtime `confirmed_at` in `businesses.timezone`, summary tool is read-only. Note that `0005` backfills pre-existing confirmed rows from `updated_at` once and does not emit opened events. Do not rewrite ADR-015. Do not implement closing.
- [x] 9.4 Install Alpine `tzdata` in the API image so stdlib `zoneinfo` can resolve a business IANA timezone inside the container. Keep the domain free of a hardcoded zone. The image smoke check must resolve `ZoneInfo("America/Mexico_City")` in that image, not from the host timezone database.

## 10. Acceptance tests

- [x] 10.1 Scenario 1: one cash confirm creates one OperationalDay, attaches the sale, and the summary reports count `1`, gross equal to the sale, and the cash bucket only.
- [x] 10.2 Scenario 2: cash `56.50`, card, and transfer on the same business date; count, gross, and each method total match the persisted payments.
- [x] 10.3 Scenario 3: `ventas de hoy` with no confirmed sales returns the zero summary and inserts no day.
- [x] 10.4 Scenario 4: a second `cómo vamos hoy` writes no audit, outbox, idempotency, or day row, and returns the same totals when no sale committed in between.
- [x] 10.5 Scenario 5: two concurrent first commits of different sessions leave one OperationalDay, one `operational_day.opened` event, and both sales attached.
- [x] 10.6 Scenario 6: same-key commit replay returns the original body and does not duplicate the day or the association.
- [x] 10.7 Scenario 7: after `confirmed`, the next product utterance on the same `conversation_id` can be confirmed on the same local date and both sales share `operational_day_id`.
- [x] 10.8 Scenario 8: frozen clock at `2026-09-22T05:59:59Z` and `2026-09-22T06:00:00Z` for `America/Mexico_City` assigns day A then day B.
- [x] 10.9 Scenario 9: business B cannot read Carrota’s OperationalDay or summary totals.
- [x] 10.10 Scenario 10: forced failure on the first commit of a date rolls back the day, payment, and `confirmed`; a later failure leaves the earlier day and sale intact and the new session `ready_to_charge`.
- [x] 10.11 Scenario 11: Flutter tests show daily count and totals from payload fields and do not add method amounts.
- [x] 10.12 Scenario 12: `ventas de la semana` clarifies, emits no summary card, and does not insert an OperationalDay.
- [x] 10.13 Migration: from revision `0004_confirmed_payment` with two confirmed sales for one business whose `updated_at` values share a local date, plus an `open` session and a `ready_to_charge` session, upgrade to `0005_operational_day` succeeds. Session A `updated_at` is `T1` and session B `updated_at` is `T2`, with `T1` earlier than `T2` and both on the same local date. Both confirmed sales get `confirmed_at` equal to their own pre-upgrade `updated_at`, keep those `updated_at` values unchanged, and share one `operational_day_id`. That OperationalDay's `created_at` and `updated_at` MUST both equal `T1` and MUST NOT equal the migration execution time. `business_date` follows that business timezone. The active rows stay NULL. Payments and items are unchanged. No `operational_day.opened` audit or outbox row exists. The membership CHECK is present. FORCE RLS is still enabled. An invalid business timezone fails the upgrade and leaves the revision at `0004_confirmed_payment`.
