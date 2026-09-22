## 1. Domain

- [x] 1.1 Add `OperationalDayStatus.CLOSED` and keep intermediate statuses unrepresentable in `backend/app/domain/operations/day.py`
- [x] 1.2 Add domain `ClosingSnapshot` and `preparation_fingerprint` in `backend/app/domain/operations/closing_snapshot.py`, using quantized `Decimal` strings and SHA-256, with no SQLAlchemy or JWT import
- [x] 1.3 Export the new types from `backend/app/domain/operations/__init__.py` and unit-test fingerprint stability, shortage/overage sign, and rejection of float inputs

## 2. Migration and persistence model

- [x] 2.1 Add Alembic `0007_daily_close_confirmation` with `down_revision = 0006_cash_count`, widening `ck_operational_days_status` to `open|closed` and adding `uq_cash_counts_id_business_day`
- [x] 2.2 Create `operations.closing_snapshots` with the design §1 columns, CHECKs, unique keys, composite foreign keys, FORCE RLS, `tenant_isolation`, and `lumo_app` `SELECT`/`INSERT`/`DELETE` only
- [x] 2.3 Add `closing_snapshots_immutable`, `SECURITY DEFINER` function `operations.assert_closing_snapshot_cardinality()` with `search_path` limited to `operations, pg_temp`, and deferred constraint triggers `closing_snapshots_match_day` (`AFTER INSERT OR DELETE`) and `operational_days_match_snapshot` (`AFTER INSERT OR DELETE OR UPDATE OF status`). The function saves `current_setting('app.current_business_id', true)`, sets it transaction-locally to the `business_id` from `NEW`/`OLD` with `set_config`, queries only that business and day, and restores the saved value before return and before every `RAISE`. A previously unset setting is restored with `SET LOCAL app.current_business_id TO DEFAULT`, which on PostgreSQL 16.14 leaves `''` (no active tenant, not the target UUID). A non-empty caller UUID is restored exactly. Do not grant `BYPASSRLS` and do not treat `SECURITY DEFINER` as a bypass of `FORCE RLS`
- [x] 2.4 Implement downgrade that aborts when any day is `closed` or any snapshot exists, and otherwise restores the open-only check and drops the new objects
- [x] 2.5 Add `ClosingSnapshotRow` to `backend/app/infrastructure/persistence/models.py` without an application update path

## 3. Snapshot repository

- [x] 3.1 Add `OperationsRepository` methods to insert a snapshot, mark a locked day `closed`, and load the snapshot for a day, copying `business_id` from `TenantContext`
- [x] 3.2 Set `created_at`, `updated_at`, and the day's `updated_at` from the confirm clock reading, not `DEFAULT now()`

## 4. Close confirmation workflow

- [x] 4.1 Add `backend/app/application/closing_confirmation_token.py` to issue and verify HS256 `typ=closing_confirm` tokens with `DEV_TOKEN_SECRET`, 15-minute expiry, and no amount claims
- [x] 4.2 Add `ConfirmDailyClose` in `backend/app/application/workflows/confirm_daily_close.py` following design §7 steps 1–13, including peek-before-lock and reserve-only-when-inserting
- [x] 4.3 On success, write audit `closing.confirm@1` and exactly one `closing.confirmed` outbox event with the frozen payload from design §10
- [x] 4.4 Return clarify for `operational_day_not_started`, `cash_count_required`, `confirmation_required`, `confirmation_invalid`, and `confirmation_stale` without reserving idempotency; stale returns refreshed preparation and a new token
- [x] 4.5 Wire the workflow into `POST /api/v1/lumo/messages` and honor `X-Debug-Fail-After-Write` so a forced failure rolls back the snapshot and status

## 5. Preparation and summary after close

- [x] 5.1 Change `closing.prepare@1` so a closed day returns the snapshot and composes `daily_close_confirmed@1`, with no recompute and no write; a closed day missing a snapshot fails
- [x] 5.2 Keep open-day and not-started preparation live, with `confirmation_token` null, and keep `preparar el cierre` from issuing a token
- [x] 5.3 Keep `operational_day.summary@1` as a live aggregate and return `status=closed` without snapshot fields

## 6. Post-close sale and cash-count guards

- [x] 6.1 In `CommitSaleSession`, lock an existing day `FOR UPDATE` on the mutating path before `idempotency.begin` and before `ensure_open_day`; clarify `operational_day_closed` without a payment or a new day
- [x] 6.2 In `RecordCashCount`, after the existing day lock, clarify `operational_day_closed` and append nothing when status is `closed`
- [x] 6.3 Leave the no-day `ensure_open_day` insert unchanged, and do not lock a sale session from the confirm workflow

## 7. Tools, policy, and interpreter

- [x] 7.1 Register `closing.confirm@1` in `backend/app/agent/registrations.py` with permission `closing.confirm`, policy `CLOSE-003`, write, idempotency, and input `{ confirmation_token }` only
- [x] 7.2 Add `CLOSE-003` in `backend/app/policies/engine.py` to deny server-owned close arguments; keep `closing.reopen@1` on `SEC-002`
- [x] 7.3 Map request-close and confirm-close phrases in `backend/app/agent/providers/scripted.py`, and remove them from the unavailable-close clarification
- [x] 7.4 Route `request_close` and `confirm_close` in `FoundationOrchestrator`, copying the token only from `client_context.confirmation_token`
- [x] 7.5 Use operation type `lumo.message.confirm_close` and do not insert an idempotency row for `request_close`

## 8. Generative UI backend

- [x] 8.1 Register `daily_close_confirmed@1` and add nullable `confirmation_token` to `daily_close_preparation@1` with `actions` still empty
- [x] 8.2 Compose the confirmed card only after commit or from a committed snapshot, with the normative fallback text and status words
- [x] 8.3 Attach the confirmation token only on a confirmable `request_close` response, and keep it out of `fallback_text`

## 9. Flutter

- [x] 9.1 Render `daily_close_confirmed@1` on Inicio from server fields only, with no reopen control and no client arithmetic
- [x] 9.2 Echo `confirmation_token` in `client_context` on the next message, never display it, and clear it after a confirmed card or a null token
- [x] 9.3 Show server label `Cerrado` on `operational_day_summary@1` when `status=closed`, and keep Hoy, Memoria, and Negocio as placeholders

## 10. Integrity, cleanup, and ADR

- [x] 10.1 Extend `clear_tenant_sale_mutations` to delete snapshots before cash counts before days, including `closing.confirm@1` audit, `closing.confirmed` outbox, and `lumo.message.confirm_close`
- [x] 10.2 Extend `sale_integrity_orphans` with the snapshot, cardinality, current-count, and cross-tenant checks from the persistence delta
- [x] 10.3 Write `docs/adr/ADR-018-daily-close-confirmation.md` covering the guard, token, immutability, `open` to `closed`, locks, post-close refusal, idempotency, and no reopen, without editing ADR-015, ADR-016, or ADR-017

## 11. Acceptance tests

- [x] 11.1 Migration test: `0006` to `0007` leaves existing rows open and snapshot-free; downgrade aborts when a close exists and succeeds when it does not
- [x] 11.2 Domain and policy tests for fingerprint, `CLOSE-003`, phrase mapping, and unregistered `closing.reopen@1`
- [x] 11.3 Acceptance: no day, missing count, balanced close, shortage close, overage close, and no auto-close when balanced
- [x] 11.4 Acceptance: stale sale, stale recount, invalid token, and confirm with no token write nothing
- [x] 11.5 Acceptance: same-key replay, different-key read-back, and forced rollback leave one or zero snapshots as specified
- [x] 11.6 Concurrency: two confirms, confirm versus recount, and confirm versus `sale.commit@1` produce one snapshot and no sale on an already-closed day
- [x] 11.7 Post-close: sale clarify, recount clarify, prepare returns the snapshot, summary stays live with `status=closed`, and a later local date can open
- [x] 11.8 RLS: another business cannot read Carrota's snapshot; Flutter widget tests show server amounts and do not render a confirm button
- [x] 11.9 Migration integrity: commit fails for `status=closed` with no snapshot, for a snapshot left on an `open` day, and for deleting the snapshot of a `closed` day; rollback restores the prior rows; insert-snapshot-then-set-`closed` commits; deleting snapshot, cash counts, and the day in one transaction commits with neither row left
- [x] 11.10 After the normal confirm, replay, recount-refusal, and sale-refusal workflows, every `closed` day has exactly one snapshot and every `open` day has zero
- [x] 11.11 PostgreSQL integration: set the GUC to the day's business so the update matches, then clear it before commit — close without a snapshot fails; switch the GUC to another business before commit — that close still fails; after a successful `SET CONSTRAINTS ALL IMMEDIATE` and after a raising validation, the caller GUC is unchanged, including a previously unset setting becoming `''` on PostgreSQL 16.14, which matches no tenant row and is not the target UUID; `lumo_app` under Carrota still commits a valid close; snapshot-then-cash-counts-then-day cleanup commits and leaves the caller GUC unchanged. Do not disable RLS or grant `BYPASSRLS` for these tests
