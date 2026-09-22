## Why

Confirmed sales exist, but Lumo cannot yet say what happened in the business today. PRD §7.7 and SRS RF-A-042 / RF-A-060 require every confirmed sale to belong to the operational date’s jornada, opened by the first sale. This slice adds that day and a server-side daily sales summary. It is the prerequisite for Daily Close and does not perform the close.

## What Changes

- Persist `OperationalDay` in new schema `operations`: one row per `(business_id, business_date)`, status `open` only.
- On a `sale.commit@1` **transition**, compute `business_date` from `confirmed_at` in `identity.businesses.timezone`, ensure that day’s row, and store `operational_day_id` plus `confirmed_at` on the confirmed `SaleSession`. Same transaction as Payment, status, audit, outbox, and idempotency.
- Register read-only `operational_day.summary@1` (Architecture §10.1 `operational_day.summary`). Aggregates come from persisted confirmed sales and recorded payments. No client or LLM math.
- Scripted interpreter accepts a closed phrase set: `cómo vamos hoy`, `ventas de hoy`, `cuánto vendimos hoy` (accent-folded). Other analytics phrases clarify and do not mutate.
- Register Generative UI `operational_day_summary@1` and render it on Inicio. Hoy stays a placeholder.
- Alembic revision `0005_operational_day` with `down_revision = "0004_confirmed_payment"` (the `0004` revision id, not the filename). Upgrade backfills confirmed sales that already exist at `0004`, then adds the membership CHECK. A backfilled day's `created_at` and `updated_at` are the earliest legacy confirmation for that date, not the migration clock. Backfill does not emit runtime audit or outbox. FORCE RLS. ADR-016.

**BREAKING** relative to the archived baseline: `operations` schema exists; confirmed sessions gain `operational_day_id` and `confirmed_at`; `ToolRegistry` and `GenerativeUIRegistry` gain the summary tool and card. Open and `ready_to_charge` sessions stay unattached.

## Capabilities

### New Capabilities

- `operational-day-foundation`: OperationalDay entity, business-date rule, commit-time membership, summary aggregation, read tool, and closed phrases.
- `operational-day-summary-ui`: Versioned `operational_day_summary@1` and Flutter rendering of server totals.

### Modified Capabilities

- `persistence`: Introduce `operations.operational_days`; add confirmed-sale linkage columns; extend cleanup. `workflow` and `memory` stay absent.
- `sales-session-foundation`: A confirmed session stores the day it belongs to. Active-session uniqueness is unchanged.
- `conversational-sale-runtime`: `sale.commit@1` ensures the day inside its write transaction; interpreter routes the closed day phrases to the read tool.
- `ai-native-contracts`: Register `operational_day.summary@1`, `operational_day_summary@1`, and policy `DAY-001`. Closing tools stay unregistered.
- `sale-payment`: Payment shape is unchanged. Drop the requirement that schema `operations` must not exist.
- `mobile-shell`: Renderer maps the day-summary card and must not sum daily totals.

## Non-goals

- Daily Close, `closing.prepare` / `closing.submit_cash_count` / `closing.confirm`, CashCount, expected vs actual cash, cash difference, reconciliation, exception review, close approval, reopening a day.
- OperationalDay states other than `open` (`in_progress`, `waiting_for_information`, `ready_to_close`, `closed`, `failed`). OutcomeRuns, WorkItems, NextBestAction, source coverage.
- Ticket promedio, product mix, weekly/monthly rollups, Hoy screen, history, charts, CSV/XLSX.
- Inventory, purchasing, receiving, suppliers, replenishment, forecasting, discounts, returns, void, accounting, CFDI/SAT, bank settlement, terminal/acquirer integration.
- Vendor LLM, voice/camera, Redis/Kafka/vector DB, multi-agent, multi-branch.

## Impact

- Backend: domain day + business-date helper, Alembic `0005`, `CommitSaleSession` ensure step, read workflow, scripted phrases, `operational_day_summary@1`.
- Mobile: Inicio renders the card from server fields. Hoy, Memoria, and Negocio stay placeholders.
- Integrity: one write transaction for day ensure + Payment + `confirmed`. Reads do not write audit, outbox, or idempotency. Cleanup deletes day rows with the sales they reference.
