## Context

Archived `build-a-daily-close-foundation` (ADR-017) left Daily Close unconfirmed. `operations.operational_days.status` is CHECK `open` only. `operations.cash_counts` is append-only, with `UNIQUE (id, business_id)` and one current row (`superseded_by_id IS NULL`). `expected_cash`, `cash_difference`, and `cash_status` are derived on read and are not stored. `closing.prepare@1` and `closing.submit_cash_count@1` are registered. `closing.confirm@1` and `closing.reopen@1` are not. Alembic head is `0006_cash_count`.

`sale.commit@1` creates or reuses the day inside its transaction via `INSERT … ON CONFLICT DO NOTHING` and does not lock the day row. Cash-count writes do lock that row `FOR UPDATE`. There is no signed confirmation-token verifier. `GenerativeUIAction.context_token` exists, and every current card sends `actions: []`. PyJWT HS256 and `DEV_TOKEN_SECRET` already issue dev auth tokens (`typ=dev`).

Authority used, and where this slice narrows it:

- PRD §7.9 and SRS RF-A-084/085: an authorized actor confirms; success is the committed close, with the difference visible and not silently corrected (RF-A-083, RB-A-010).
- PRD §9.2: a valid `CashCount` must exist and the difference must be visible. The gate does not require a zero difference.
- PRD §15 leaves the pilot policy for a non-zero difference open. This design decides it.
- PRD §8.3 and SRS §7.2 describe a longer day machine. ADR-016/017 persisted only `open`. This slice adds `closed` and still does not persist `in_progress`, `waiting_for_information`, `ready_to_close`, or `failed`, because those states belong to the workflow engine this change does not own.
- PRD §12 excludes reopening and a versioned `ClosingSnapshot`. This slice stores one immutable snapshot, not a version chain.
- SRS RF-A-085 also names outcome and memory. Those schemas stay absent. The atomic commit is snapshot + `status=closed` + audit + outbox.
- Architecture §10.1 names `closing.confirm`. SRS §11 names permission `closing.confirm`. No document names a `CLOSE-003` rule or a `closing.confirmed` event. Those identifiers continue the existing `CLOSE-001`/`CLOSE-002` and `sale.confirmed` patterns. They are not a second vocabulary.
- Design System §4.18 puts "Preparar el cierre del día" on Hoy as an unwired toast. ADR-017 kept the review on Inicio. This slice stays on Inicio.

Money columns in `sales` and `operations` are `numeric(12,2)`. Domain code does not import FastAPI, SQLAlchemy, or Flutter. One orchestrator. No new broker, cache, or agent.

## Goals / Non-Goals

**Goals:**

- Freeze the accepted close in one immutable `ClosingSnapshot`.
- Transition today's open day to `closed` only after explicit, still-current confirmation.
- Keep later sales and recounts off that closed day.
- Return the frozen close from the close read, and keep the sales summary as a live aggregation.

**Non-Goals:**

- The proposal's Non-goals, including reopen, WorkItems, OutcomeRuns, tolerance, Hoy, export, and memory rows.

## Decisions

### 1. `ClosingSnapshot` schema

New table `operations.closing_snapshots`. Domain type in `backend/app/domain/operations/closing_snapshot.py`. Persistence methods stay on `OperationsRepository`. No new schema and no new top-level package.

| Column | Type | Source at insert, under the day lock |
|---|---|---|
| `id` | UUID v7 | application |
| `business_id` | UUID | `TenantContext` |
| `operational_day_id` | UUID | locked day |
| `cash_count_id` | UUID | current `CashCount` (`superseded_by_id IS NULL`) |
| `actor_id` | UUID | `TenantContext.actor_id`. This is the closer. There is no second `closed_by` column |
| `business_date` | `DATE` | copied from the locked day. It must equal today's business date from the same clock reading |
| `currency` | `VARCHAR(3)` | business currency. Payment currencies must match or the close aborts |
| `sale_count` | `INTEGER` | `summarize_day` |
| `gross_sales_total` | `numeric(12,2)` | `summarize_day` |
| `cash_total` | `numeric(12,2)` | `summarize_day` |
| `card_total` | `numeric(12,2)` | `summarize_day` |
| `transfer_total` | `numeric(12,2)` | `summarize_day` |
| `expected_cash` | `numeric(12,2)` | that same `cash_total` |
| `counted_cash` | `numeric(12,2)` | current `CashCount.amount` |
| `cash_difference` | `numeric(12,2)` | `counted_cash - expected_cash`, existing domain function |
| `cash_status` | `VARCHAR(16)` | `balanced`, `over`, or `short` from the sign of that difference. `not_counted` is not a snapshot status |
| `closed_at` | `timestamptz` | the one UTC clock reading for this confirm |
| `created_at`, `updated_at` | `timestamptz` | the same `closed_at`, set explicitly |

Not stored: denominations, note, evidence ids, source coverage, outcome id, product rows, tolerance, opening float, a version number.

Constraints:

- `PRIMARY KEY (id)`
- `UNIQUE (operational_day_id)` — one snapshot per day
- `UNIQUE (id, business_id)`
- `UNIQUE (cash_count_id)` — the accepted count is referenced once
- FK `(operational_day_id, business_id)` → `operational_days (id, business_id)`
- New `UNIQUE (id, business_id, operational_day_id)` on `cash_counts` (`uq_cash_counts_id_business_day`). Existing `uq_cash_counts_id_business` stays. FK `(cash_count_id, business_id, operational_day_id)` → `cash_counts (id, business_id, operational_day_id)`
- CHECKs: `sale_count >= 0`; every money column except `cash_difference` is `>= 0`; `expected_cash = cash_total`; `gross_sales_total = cash_total + card_total + transfer_total`; `cash_difference = counted_cash - expected_cash`; `cash_status` is `over` / `short` / `balanced` according to the sign of `cash_difference`
- `ENABLE` and `FORCE` ROW LEVEL SECURITY, policy `tenant_isolation`, same expression as `operational_days`
- `lumo_app` receives `SELECT`, `INSERT`, and `DELETE` only. No `UPDATE` privilege
- `BEFORE UPDATE` trigger `closing_snapshots_immutable` raises for every role, so snapshot `UPDATE` is not an enforcement path
- Two deferred constraint triggers, both `DEFERRABLE INITIALLY DEFERRED`, call one function `operations.assert_closing_snapshot_cardinality()`. A trigger only on `closing_snapshots` is not enough: `UPDATE operational_days SET status = 'closed'` never touches a snapshot row, so that trigger would not fire

`ClosingSnapshot` is immutable in product operation. No application path updates a snapshot, no product workflow deletes or rewrites one, and there is no replacement or version chain. `DELETE` stays granted because `clear_tenant_sale_mutations` removes tenant rows. That helper is the only intended deleter.

Cardinality uses one function, `operations.assert_closing_snapshot_cardinality()`, `SECURITY DEFINER`, `SET search_path = operations, pg_temp`, owned by the owner of `operations.operational_days`. `SECURITY DEFINER` only stabilizes the execution owner and `search_path`. It does not bypass row-level security. Those tables use `FORCE ROW LEVEL SECURITY`, and the owner is a non-superuser without `BYPASSRLS`. Do not grant `BYPASSRLS` and do not add a bypass role. `lumo_app` stays without `BYPASSRLS`.

The affected business comes only from the trigger row, not from function arguments. Before the cardinality queries the function saves `current_setting('app.current_business_id', true)`, then `set_config('app.current_business_id', target_business_id::text, true)`. Queries filter to that `business_id` and that day id only. On every return, and in the exception handler before every `RAISE`, it restores the caller context. It must not leave the target business UUID active. `set_config` uses `is_local = true` only. It must not use dynamic SQL, must not try to force a custom GUC back to SQL NULL, and must not `RESET` the session value.

A custom GUC has two no-tenant representations. `current_setting(..., true) IS NULL` means it was never initialized in the session. After a transaction-local assignment, PostgreSQL 16.14 cannot put that custom setting back to SQL NULL inside the same transaction. `SET LOCAL app.current_business_id TO DEFAULT` and `set_config(..., NULL, true)` both leave `''`. `NULL` and `''` both mean no active tenant: `business_id::text = current_setting(...)` matches no business UUID. A non-empty saved value is an active tenant and must be restored exactly. Restoration is:

- Saved value NULL: `SET LOCAL app.current_business_id TO DEFAULT`. On PostgreSQL 16.14 the setting is then `''`, not the target UUID.
- Saved value not NULL, including the empty string: `set_config('app.current_business_id', saved_value, true)`.

`lumo_admin` is also a non-superuser without `BYPASSRLS`, so a statement whose GUC does not match the row updates nothing and does not queue the trigger. The unset-GUC and wrong-GUC tests set `app.current_business_id` to the affected business for the `UPDATE`, then clear it or point it at another business before `COMMIT`. The deferred check then runs with the caller's bad context. Commit must still fail. That is what shows the function used `NEW`/`OLD` rather than the caller GUC. Do not disable RLS and do not use a bypass role to make the update visible.

| Trigger | Table | Events |
|---|---|---|
| `closing_snapshots_match_day` | `operations.closing_snapshots` | `AFTER INSERT`, `AFTER DELETE` |
| `operational_days_match_snapshot` | `operations.operational_days` | `AFTER INSERT`, `AFTER UPDATE OF status`, `AFTER DELETE` |

Both are `FOR EACH ROW` constraint triggers. Snapshot `UPDATE` is not one of these events. `closing_snapshots_immutable` already rejects it.

At `COMMIT` the function sees the final rows for that pair:

- No day row and no snapshot row: success. Cleanup may delete the snapshot and then the day in one transaction. The check must not demand a snapshot for a day that no longer exists.
- No day row and a snapshot row still present: failure. The immediate snapshot-to-day foreign key also rejects deleting the day first. The function is the same rule at commit.
- Day `open` and `snapshot_count = 0`: success.
- Day `open` and `snapshot_count <> 0`: failure.
- Day `closed` and `snapshot_count = 1`: success.
- Day `closed` and `snapshot_count <> 1`: failure.
- Any other status: failure. The status `CHECK` already rejects those values.

Inside the confirm transaction the day may be `open` while the new snapshot row exists. That intermediate state is legal because both checks wait until `COMMIT`. The legal close is insert snapshot, set `status=closed`, then commit. A direct `status=closed` with no snapshot fails at commit and rolls back to `open`. An insert that leaves the day `open` fails at commit and leaves no snapshot. Deleting the only snapshot of a still-closed day fails at commit and the snapshot remains.

`cash_status` is stored so a later formula change cannot reclassify an accepted close. The CHECK keeps it equal to the frozen difference. Audit is not the source of truth for a later read.

Close does not insert an `OperationalDay`. No sales means no day, which means nothing to close.

### 2. Day state

`ck_operational_days_status` becomes `status IN ('open', 'closed')`. Existing rows stay `open`. No backfill and no snapshot insert in the migration.

`closed_at` lives only on the snapshot. The day row does not gain totals or a close timestamp. `updated_at` on the day changes when status changes, using the same `closed_at`.

`in_progress`, `waiting_for_information`, `ready_to_close`, `failed`, `closed_with_exceptions`, and `reopened` stay rejected. `not_started` remains the absence of a row.

### 3. Shortage and overage

`balanced`, `short`, and `over` may all close. This is the pilot policy PRD §15 left open: the merchant confirms the visible difference, the signed difference is frozen, and nothing is adjusted. There is no tolerance, approval, or exception queue.

`not_counted` cannot close. `balanced` does not auto-close. Declining to say the confirm phrase leaves the day `open`.

An `open` or `ready_to_charge` session does not block confirmation. It is not a member of the day. Committing it after close is refused (decision 8). Full outcome gates stay out of scope.

### 4. Confirmation flow and token

Closed phrases, after the existing `normalize_closed_phrase`:

| Phrase | Intent | Effect |
|---|---|---|
| `cerrar el dia`, `cerrar la jornada`, `cerrar caja` | `request_close` | preparation read plus a question. Does not call `closing.confirm@1` |
| `confirmar cierre`, `si, cerrar`, `confirmar` | `confirm_close` | `closing.confirm@1` only with a valid token |

`confirmar` is that exact phrase only. Payment phrases are unchanged. `preparar el cierre` stays a pure prepare and does not issue a token.

No persisted challenge row and no new action id. The codebase has JWT signing and an empty action list, and no token verifier. This slice uses that JWT stack for the Architecture/SRS signed context, without a button:

- HS256 with the existing `DEV_TOKEN_SECRET`
- `iss=lumo`, `typ=closing_confirm` (never `dev`, so it is not an auth token and `allows_dev_tokens` does not apply)
- Claims: `business_id`, `actor_id`, `operational_day_id`, `cash_count_id`, `fingerprint`, `iat`, `exp`
- `exp = iat + 15 minutes` from the issuing clock
- No amounts in the token

The fingerprint is domain-owned SHA-256 hex of this UTF-8 string, money quantized to `0.01`:

```text
v1|{business_id}|{operational_day_id}|{cash_count_id}|{business_date}|{currency}|{sale_count}|{gross}|{cash}|{card}|{transfer}|{expected}|{counted}|{difference}|{cash_status}
```

Issuance happens only in the orchestrator on `request_close`, and only when the preparation read shows an open day, a current count, and a valid currency. The token is placed on `daily_close_preparation@1.data.confirmation_token`. `actions` stays `[]`. Flutter stores it in memory and sends it back as `client_context.confirmation_token`. Flutter does not display it and does not invent it. The orchestrator copies that field into the tool input and discards any token on the model decision.

Confirmable request text:

`El cierre está preparado: {n} venta|ventas · ${gross}. Efectivo esperado ${expected}. Contado ${counted}. Diferencia ${difference}. ¿Confirmas el cierre?`

`1` uses `venta`; every other count uses `ventas`. Amounts are the server decimal strings, difference sign included.

Other request outcomes, all non-writing:

- No day: not-started preparation payload, token null, text `No hay una jornada abierta para cerrar hoy.`
- Open day, no count: preparation card, token null, text `Falta contar el efectivo antes de cerrar.`
- Already closed: `daily_close_confirmed@1`, token null

`closing.confirm@1` input is exactly `{ "confirmation_token": "<jwt>" }`.

Token results under the day lock:

| Condition | Reason | Write |
|---|---|---|
| Missing token | `confirmation_required` | none |
| Bad signature, expired, wrong `typ`, wrong business, or wrong actor | `confirmation_invalid` | none |
| Valid token whose day, current count, or fingerprint ≠ locked state | `confirmation_stale` | none. Return refreshed preparation, a new token, and `El cierre cambió. Revisa los datos y confírmalo otra vez.` |

A stale result asks again. It does not close.

### 5. Guards

Under the day lock, confirmation proceeds only when all of these hold:

1. An `OperationalDay` exists for today's business date.
2. `status=open`.
3. A current `CashCount` exists for that day and its `business_id` matches.
4. `summarize_day` succeeds, so currency is consistent.
5. No snapshot exists yet for that day.
6. The token checks in decision 4 pass against that locked state.
7. Derived `cash_status` is `balanced`, `over`, or `short`.

Anything else clarifies or read-backs as specified below. No guard trusts a client total.

### 6. Tool, permission, and policy

`closing.confirm@1`: `side_effect=write`, `requires_idempotency=true`, permission `closing.confirm` (SRS §11), policy `CLOSE-003`. Permission stays declarative metadata, as with `closing.submit_cash_count`. No new RBAC engine.

`CLOSE-003` denies the call when arguments include any of: `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, `operational_day_id`, `closing_snapshot_id`, `business_date`, `closed_at`, `sale_count`, `gross_sales_total`, `cash_total`, `card_total`, `transfer_total`, `currency`, `actor_id`, `cash_count_id`. The workflow under the lock is what authorizes the close. `closing.reopen@1` stays unregistered and denied by `SEC-002`.

### 7. Transaction, locks, and races

Normative `closing.confirm@1` order, one application transaction:

1. Peek `lumo.message.confirm_close`. Same key and hash: return the stored body. Different hash: `IDEMPOTENCY_CONFLICT`. No lock yet.
2. Read timezone and currency. Take one UTC clock reading. Derive today's business date.
3. `SELECT … FOR UPDATE` today's day. No row: clarify `operational_day_not_started`. No reserve.
4. Peek again, in case a same-key winner committed while this transaction waited.
5. `status=closed`: read-back the snapshot (decision 9). Do not reserve a new idempotency row.
6. No current count: clarify `cash_count_required`. No reserve.
7. `summarize_day` under the lock. Currency failure aborts with no snapshot.
8. Verify the token (decision 4). Failures do not reserve.
9. Reserve the idempotency key.
10. `INSERT` the snapshot while status is still `open`.
11. `UPDATE` the day to `closed` where `status=open`. Row count must be 1.
12. Audit, one outbox event, complete idempotency.
13. Commit. Both deferred cardinality triggers then see `status=closed` and exactly one snapshot. Success is composed only after commit.

`X-Debug-Fail-After-Write` still rolls the whole transaction back: day stays `open`, no snapshot, no close audit, no `closing.confirmed`.

Lock order elsewhere:

- Cash count and confirm lock only the day row, so they serialize. The loser re-reads. A recount that commits first changes the current count; the waiting confirm then fails the fingerprint and does not close. A confirm that commits first leaves the day `closed`; the waiting recount clarifies `operational_day_closed` and appends nothing.
- `sale.commit@1` keeps its session `FOR UPDATE`, then, on the mutating path only, locks the day `FOR UPDATE` before `idempotency.begin` and before `ensure_open_day` / payment insert. Confirm never locks a sale session, so the order session → day cannot deadlock with confirm or with a cash count.
- If the day row does not exist, commit keeps today's `ensure_open_day` insert. Close cannot be racing, because close cannot create a day.
- If commit holds the day lock, confirm waits, then recomputes and rejects a stale token.
- If confirm commits first, commit sees `closed` and clarifies. The session is not confirmed, no payment is inserted, and no idempotency row is reserved.

No advisory lock, Redis lock, or serializable isolation.

### 8. After close

`sale.commit@1` for today's closed date clarifies `operational_day_closed` with text `La jornada de hoy ya está cerrada. No puedo registrar otra venta en ese día.` The session stays `open` or `ready_to_charge`. No reopen and no second day for that date. A confirmation after local midnight belongs to the new business date; yesterday's closed day is left as it is. This slice does not close older open days.

`closing.submit_cash_count@1` on a closed day clarifies `operational_day_closed` with text `La jornada de hoy ya está cerrada. No puedo cambiar el conteo.` No new count, audit, outbox, or idempotency row. The current count stays current.

### 9. Idempotency

Operation type `lumo.message.confirm_close`. The hash covers the raw message, `conversation_id`, and the token string.

- Same key, same hash: stored body, no second snapshot, audit, or event.
- Same key, different hash: `IDEMPOTENCY_CONFLICT`, no write.
- Different key when the day is already closed: frozen snapshot read-back, no new snapshot, audit, outbox, or idempotency row.
- A clarify (no day, no count, bad or stale token) does not reserve a key.
- A key that is absent, processing, or failed follows the existing begin/retry rules, and is reserved only at step 9.

### 10. Audit and outbox

One audit action `closing.confirm@1` per successful close, in the same transaction.

`before_payload`: `status=open`, `operational_day_id`, `cash_count_id`.

`after_payload`: `closing_snapshot_id`, `operational_day_id`, `cash_count_id`, `business_date`, `currency`, `sale_count`, `gross_sales_total`, `cash_total`, `card_total`, `transfer_total`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`, `closed_at`, `previous_status=open`, `new_status=closed`.

One outbox event `closing.confirmed` with those frozen identifiers and amounts. Replay, read-back, and clarify write neither. No worker. The snapshot row, not the audit row, is what a later close read returns.

### 11. Reads and UI

`operational_day.summary@1` stays a live aggregation of confirmed sales and recorded payments. It may return `status=open`, `status=closed`, or null. It does not read the snapshot and does not grow cash-difference fields. The summary card may show the server label `Cerrado` when `status=closed`.

`closing.prepare@1` on an open day is unchanged and returns `confirmation_token=null`. On a closed day it returns the snapshot, does not recompute, writes nothing, and the composer emits `daily_close_confirmed@1`. A closed day with no snapshot is an error, not a live fallback.

`daily_close_confirmed@1` fields: `operational_day_id`, `closing_snapshot_id`, `business_date`, `day_status=closed`, `closed_at`, `currency`, `sale_count`, `gross_sales_total`, `expected_cash`, `counted_cash`, `cash_difference`, `cash_status`. `actions` is empty. No reopen control. Fallback starts with `Cierre confirmado`. Status words stay `Caja cuadrada`, `Sobrante`, and `Faltante`.

Inicio renders both cards in the current stream and keeps `conversation_id`. Hoy, Memoria, and Negocio stay placeholders. The Hoy action card stays unwired. Flutter displays server amounts only.

### 12. Migration, cleanup, integrity, ADR

Revision `0007_daily_close_confirmation`, `down_revision=0006_cash_count`. It replaces the status CHECK, adds `uq_cash_counts_id_business_day`, and creates the snapshot table, RLS, grants, `closing_snapshots_immutable`, `operations.assert_closing_snapshot_cardinality()`, and the two deferred constraint triggers. The function saves and restores `app.current_business_id` as specified above. It does not grant `BYPASSRLS`. It does not update existing day or count rows.

Downgrade aborts if any day is `closed` or any snapshot row exists. If neither exists, it drops all three triggers and the function, drops the table, drops `uq_cash_counts_id_business_day`, and restores `status IN ('open')`. It does not rewrite `closed` to `open`.

Cleanup deletes `closing_snapshots` before `cash_counts` before `operational_days`, and includes `closing.confirm@1` audit, `closing.confirmed` outbox, and `lumo.message.confirm_close` idempotency.

Integrity flags: snapshot whose day or count is missing or in another business; count whose day disagrees with the snapshot; more than one snapshot per day; a closed day without exactly one snapshot; an open day with a snapshot; a snapshot whose CHECKs would fail; a referenced count that is not current; audit or outbox ids that do not exist.

ADR-018 records this decision. ADR-015, ADR-016, and ADR-017 are not edited.

### 13. Rejected alternatives

- Persist PRD §8.3 intermediate states now. They require the workflow engine this slice excludes.
- Block `short` and `over`. PRD §7.9 allows confirmation when the pilot policy says so, and a block needs the exception queue this slice excludes.
- Auto-close when `balanced`. RF-A-084 requires an authorized confirmation.
- Trust `confirmar cierre` with no token, or trust client totals. A sale between prompt and confirm would freeze figures the merchant did not see.
- Store a challenge row. JWT plus recompute under the day lock is enough, and it reuses the existing signer.
- Add a confirm button. No registered action contract exists, and the conversation is the control.
- Reuse `daily_close_preparation@1` for the closed card. The closed payload is a different contract: it has `closed_at`, the snapshot id, and gross sales, and it is immutable.
- Make `operational_day.summary@1` return the snapshot. That read is the live sales aggregate. The close read is the snapshot.
- Grant `UPDATE` on snapshots and rely on application discipline. The role privilege and `closing_snapshots_immutable` both refuse updates.
- Treat `SECURITY DEFINER` or table ownership as a bypass of `FORCE ROW LEVEL SECURITY`. The owner has no `BYPASSRLS`. The validator sets `app.current_business_id` from the affected row and restores the caller's value.
- Enforce cardinality with one deferred trigger on `closing_snapshots` only. Setting `operational_days.status` to `closed` would not fire it.
- Revoke `DELETE` from `lumo_app`. The existing tenant reset deletes snapshot rows in the same transaction as the day.
- Downgrade by dropping snapshots and reopening days. That destroys an accepted close.
- Create an empty closed day when there were no sales. ADR-016 keeps `sale.commit@1` as the only day creator.

## Risks / Trade-offs

- [Exact phrase `confirmar` is broad] → It matches only that normalized string. Sale phrases stay on `sale.commit@1`. A confirm with no token clarifies and writes nothing.
- [Confirmation signing uses `DEV_TOKEN_SECRET`] → `typ=closing_confirm` cannot authenticate. Renaming the setting is out of scope; the setting is already required in every environment.
- [A draft sale can still exist at close] → It is excluded from the snapshot. Committing it onto the closed date fails and does not reopen the day.
- [Summary totals could diverge from the snapshot if a sale attached after close] → Commit takes the same day lock before insert and refuses `closed`. Integrity plus that guard is the invariant. The summary is still not a close document.
- [Fifteen-minute token expiry] → Expiry clarifies `confirmation_invalid` and the merchant asks for the close again. No partial close.
- [Downgrade refusal] → A database that already confirmed a day cannot migrate down. That is the safe failure.
- [A cardinality check under `FORCE RLS` can miss the pair or leak the target tenant into the caller GUC] → The function sets `app.current_business_id` from `NEW`/`OLD` only, queries that business and day, and restores before return and before re-raise. A previously unset GUC becomes `''` on PostgreSQL 16.14, which matches no business. A caller UUID is restored exactly. No `BYPASSRLS`.
- [Force a custom GUC back to SQL NULL after temporary use] → PostgreSQL 16.14 leaves `''`. Treating `''` as no active tenant is the rule. The RLS predicate is not changed to match `''`.

## Migration Plan

1. Deploy `0007` before the API that writes snapshots. Until the new API is live, days stay `open` and no snapshot exists, so the old API keeps working on the widened CHECK.
2. Ship API and Flutter together so a request-close response can echo the token.
3. Rollback of the application binary is safe while no day is `closed`. Schema rollback uses the downgrade rule in decision 12 and stops if a close exists.

## Open Questions

None. Implementation-significant choices are fixed above:

1. Snapshot columns are decision 1. `actor_id` is the closer.
2. Exactly one snapshot per day (`UNIQUE (operational_day_id)`).
3. Immutable in product operation: no `UPDATE` grant, `closing_snapshots_immutable`, and no product delete or version chain. `DELETE` remains for test/reset cleanup. Cardinality is `operations.assert_closing_snapshot_cardinality()` on both tables. The function sets `app.current_business_id` from the trigger row and restores it. `SECURITY DEFINER` does not bypass `FORCE RLS`. Decision 1.
4. Frozen values and their sources are the column table in decision 1.
5. `cash_status` is stored and CHECK-tied to the difference.
6. Gross, cash, card, and transfer totals are stored.
7. The snapshot references the current `CashCount`.
8. A current count is required.
9. `short` and `over` may close after explicit confirmation.
10. `not_counted` blocks.
11. `balanced` does not auto-close.
12. Phrases and texts are decision 4.
13. A 15-minute server JWT bound to the fingerprint is required. The phrase alone is not enough.
14. Tool input is `{ "confirmation_token" }` only.
15. Permission `closing.confirm`, policy `CLOSE-003`.
16. Audit action `closing.confirm@1`.
17. Outbox `closing.confirmed`, once.
18. Same-key replay returns the stored body.
19. A different key on a closed day is a snapshot read-back with no new idempotency row.
20. Concurrent confirms serialize on the day lock; one snapshot and one event.
21. A recount that wins the lock invalidates the token; the confirm does not close.
22. Commit and confirm serialize on the day lock; a sale cannot attach after close commits.
23. A later sale on the closed date is clarified and does not reopen.
24. A later recount is clarified and does not append.
25. `closing.prepare@1` on a closed day returns the snapshot.
26. `operational_day.summary@1` on a closed day stays a live aggregate with `status=closed`.
27. UI contract is `daily_close_confirmed@1`.
28. Persisted statuses are only `open` and `closed`.
29. `closed_at` is the confirm transaction's single UTC clock reading.
30. Close never creates the day.
31. No day means the close request clarifies and writes nothing.
32. A business with no sales cannot close that date.
33. No WorkItem and no OutcomeRun.
34. No history or list endpoint.
