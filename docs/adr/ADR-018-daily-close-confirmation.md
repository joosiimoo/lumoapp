# ADR-018: Daily close confirmation

- Status: Accepted
- Date: 2026-09-22

## Decision

A confirmed close freezes one immutable `ClosingSnapshot` and moves that `OperationalDay` from `open` to `closed`. There is no reopen, no version chain, and no product path that updates a snapshot. `lumo_app` may `SELECT`, `INSERT`, and `DELETE`; `UPDATE` is not granted, and `closing_snapshots_immutable` rejects every update. `DELETE` exists so test/reset cleanup can remove a snapshot in the same transaction as its day.

`balanced`, `short`, and `over` may close after an explicit confirmation of the visible difference. Nothing is adjusted, and there is no tolerance, approval, or exception queue. `not_counted` cannot close. `balanced` does not auto-close. Close never creates a day.

Confirmation is an HS256 JWT, `iss=lumo`, `typ=closing_confirm`, signed with `DEV_TOKEN_SECRET`, expiring 15 minutes after `iat`. Claims are `business_id`, `actor_id`, `operational_day_id`, `cash_count_id`, and a domain SHA-256 fingerprint of the locked preparation. The token is not a `typ=dev` authentication token and carries no amounts. The orchestrator copies it only from `client_context.confirmation_token`. A valid token whose day, current count, or fingerprint no longer matches is stale: nothing is written, and the merchant must confirm the refreshed preparation.

`closing.confirm@1` locks today's operational day, inserts the snapshot while the day is still `open`, then sets `status=closed`. Audit action `closing.confirm@1` and outbox event `closing.confirmed` are written once in that transaction. Idempotency type `lumo.message.confirm_close` is reserved only when the close will mutate. A same-key replay returns the stored body. A different key on an already closed day returns the snapshot and writes nothing.

The day row is the shared lock with recounts and `sale.commit@1`. A closed day refuses another sale and another cash count. Commit locks an existing day before reserving idempotency and before creating a payment. If no day exists, commit still creates it.

Cardinality is checked from both tables by deferred constraint triggers `closing_snapshots_match_day` and `operational_days_match_snapshot`. An open day has zero snapshots. A closed day has exactly one. A missing day is valid only when no snapshot remains. `operations.assert_closing_snapshot_cardinality()` is `SECURITY DEFINER` with `search_path` limited to `operations, pg_temp` so execution privileges stay stable. That does not bypass `FORCE ROW LEVEL SECURITY`: the owner is a non-superuser without `BYPASSRLS`, and no bypass role is created. Before it reads, the function saves `app.current_business_id`, sets that GUC transaction-locally to the `business_id` on `NEW`/`OLD`, queries only that business and day, and restores the saved value before returning and before re-raising. A previously unset value is restored with `SET LOCAL app.current_business_id TO DEFAULT`. On PostgreSQL 16.14 that leaves `''`, which matches no business UUID. A caller UUID is restored exactly. `NULL` and `''` both mean no active tenant. The RLS predicate is not changed.

## Consequences

Alembic `0007_daily_close_confirmation` widens `ck_operational_days_status` to `open|closed`, adds `uq_cash_counts_id_business_day`, and creates `operations.closing_snapshots`. Existing days stay `open`. Downgrade aborts when any day is `closed` or any snapshot exists. ADR-015, ADR-016, and ADR-017 are unchanged.
