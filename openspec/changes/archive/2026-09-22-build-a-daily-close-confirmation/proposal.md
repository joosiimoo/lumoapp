## Why

Lumo can prepare a daily close and record a cash count, but it cannot confirm the day. Expected cash and the difference stay live, so a later sale or recount would change what the merchant thought they accepted. PRD §7.9 and SRS RF-A-084/085 require an authorized confirmation whose `closed` state, audit, and evidence commit together. ADR-017 left that freeze for a future `ClosingSnapshot`.

## What Changes

- Add one immutable `ClosingSnapshot` per `OperationalDay`. It freezes the confirmed-sales totals, the current `CashCount`, expected cash, the signed difference, and `cash_status` at the moment of confirmation.
- Allow exactly one new day transition: `open` → `closed`. Intermediate PRD §8.3 / SRS §7.2 states stay unpersisted; this slice does not own the workflow engine.
- Register `closing.confirm@1` (`write`, idempotent, permission `closing.confirm`, policy `CLOSE-003`). The client and the model cannot supply totals, day id, snapshot id, or `closed_at`.
- Require a server-issued confirmation token. `cerrar el día` shows the current preparation and asks. `confirmar cierre` closes only when that token still matches the locked state. A sale or recount in between refreshes the preparation and does not freeze the stale figures.
- A non-zero difference may close after that explicit confirmation. It is stored as shown and never adjusted (PRD §7.9, SRS RF-A-083, RB-A-010). `not_counted` blocks. A balanced day does not auto-close. PRD §15's pilot policy is decided here as explicit confirmation of the visible difference, with no tolerance and no approval chain.
- After close, `sale.commit@1` and `closing.submit_cash_count@1` refuse the closed day. Nothing reopens it. `closing.prepare@1` returns the snapshot. `operational_day.summary@1` stays a live confirmed-sales aggregation and may report `status=closed`.
- Show `daily_close_confirmed@1` on the existing Inicio stream. Hoy stays a placeholder.
- Migration `0007_daily_close_confirmation` (`down_revision = 0006_cash_count`). Propose ADR-018. Do not rewrite ADR-015, ADR-016, or ADR-017.

## Capabilities

### New Capabilities

- `closing-snapshot-foundation`: immutable `operations.closing_snapshots`, one per day, tenant-safe, internally consistent.
- `daily-close-confirmation`: guards, confirmation token, `closing.confirm@1`, locking, idempotency, audit, outbox, and post-close sale and cash-count refusal.
- `daily-close-confirmed-ui`: versioned closed card with no actions.

### Modified Capabilities

- `persistence`: revision `0007`, status check `open|closed`, snapshot table, cleanup order, integrity checks, downgrade refusal.
- `operational-day-foundation`: `closed` is legal; close does not create a day; a confirming sale cannot attach to a closed day.
- `operational-day-summary-ui`: `status` may be `closed`.
- `cash-count-foundation`: a recount of a closed day is refused.
- `daily-close-preparation`: a closed day reads the snapshot; a close request may attach a confirmation token; preparation still does not close.
- `daily-close-preparation-ui`: optional server-issued `confirmation_token`, never rendered as a mutating button.
- `conversational-sale-runtime`: closed phrases for request and confirm; register `closing.confirm@1`.
- `conversational-sale-session`: `sale.commit@1` locks the day and refuses a closed date.
- `ai-native-contracts`: register the confirm tool and `daily_close_confirmed@1`; `closing.reopen@1` stays unregistered.
- `mobile-shell`: render the confirmed card on Inicio and echo the confirmation token.

## Impact

- PostgreSQL `operations.closing_snapshots` and `ck_operational_days_status`. No workflow or memory schema.
- `sale.commit@1` and `closing.submit_cash_count@1` gain a closed-day guard. Existing open-day behavior is unchanged.
- Message path gains `lumo.message.confirm_close`. Audit action `closing.confirm@1`. Outbox `closing.confirmed`, once per successful close.
- Flutter Inicio only. No new dependency, broker, or agent.

## Non-goals

- `closing.reopen@1`, day reopening, and versioned snapshots (PRD §12).
- WorkItems, NextBestAction, OutcomeRuns, exception queues, approvals, manager override, and tolerance.
- Denominations, opening float, expenses, withdrawals, deposits, refunds, voids, reconciliation, settlement, accounting, CFDI/SAT.
- Close history, export, charts, weekly or monthly reporting, and a Hoy redesign.
- Inventory, purchasing, suppliers, forecasting, CRM, loyalty, multi-branch.
- Redis, Kafka, vector DB, a new agent, or broad NLU.
- Event Memory rows and outcome evaluation. The outbox event is the handoff; no worker is added.
- Blocking close because an `open` or `ready_to_charge` session still exists. Those sessions are not day members. Committing one after close is refused.
