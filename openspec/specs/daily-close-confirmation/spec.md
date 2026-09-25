## Purpose

Explicit confirmation of today's open operational day: signed token, fingerprint, short and over allowed, stale confirmation refused, one snapshot, one audit, and one outbox event. No reopen.

## Requirements

### Requirement: closing.confirm@1 confirms today's open day
`ToolRegistry` MUST register `closing.confirm@1` as a write tool. Input MUST be exactly `{ "confirmation_token": string }` and MUST NOT accept totals, expected cash, counted cash, a difference, `cash_status`, an operational day id, a snapshot id, a business date, a currency, an actor id, a cash count id, or `closed_at`. Permission MUST be `closing.confirm`. Policy MUST be `CLOSE-003`. Side effect MUST be `write`. Idempotency MUST be required. `closing.reopen@1` MUST remain unregistered. The tool MUST NOT create an `OperationalDay`, a `WorkItem`, a `NextBestAction`, or an `OutcomeRun`, and MUST NOT register `daily_close_ready@1`. A business date with no `OperationalDay` MUST clarify with reason `operational_day_not_started` and MUST NOT insert a day, a snapshot, an audit row, an outbox row, or an idempotency row.

#### Scenario: No day does not close
- **WHEN** the actor confirms a close and no OperationalDay exists for today's business date
- **THEN** the response MUST clarify with `operational_day_not_started`, and `operations.operational_days` and `operations.closing_snapshots` MUST gain no row

#### Scenario: Reopen stays unregistered
- **WHEN** a decision names `closing.reopen@1`
- **THEN** the registry MUST report the tool as unregistered, policy MUST `deny` under `SEC-002`, and no day MUST change status

### Requirement: Explicit confirmation token is required
A close MUST NOT proceed from conversational text alone. `request_close` phrases `cerrar el dia`, `cerrar la jornada`, and `cerrar caja`, after `normalize_closed_phrase`, MUST run the preparation read and MUST NOT call `closing.confirm@1`. When that read shows an open day, a current `CashCount`, and a consistent currency, the orchestrator MUST issue a confirmation token and ask `El cierre está preparado: {n} venta|ventas · ${gross}. Efectivo esperado ${expected}. Contado ${counted}. Diferencia ${difference}. ¿Confirmas el cierre?` with `1 venta` only when `sale_count` is 1. The token MUST be HS256, signed with `DEV_TOKEN_SECRET`, with `iss=lumo` and `typ=closing_confirm`, claims `business_id`, `actor_id`, `operational_day_id`, `cash_count_id`, `fingerprint`, `iat`, and `exp`, and `exp` MUST be `iat` plus 15 minutes. It MUST NOT be `typ=dev` and MUST NOT contain amounts. The fingerprint MUST be the SHA-256 hex of `v1|{business_id}|{operational_day_id}|{cash_count_id}|{business_date}|{currency}|{sale_count}|{gross}|{cash}|{card}|{transfer}|{expected}|{counted}|{difference}|{cash_status}` using quantized decimal strings. The orchestrator MUST read the token only from `client_context.confirmation_token` and MUST discard a token supplied by the model. `confirm_close` phrases `confirmar cierre`, `si, cerrar`, and `confirmar` MUST select `closing.confirm@1`.

#### Scenario: Request close asks and does not close
- **WHEN** today's open day has expected cash `22.50`, a current count of `22.50`, and the actor posts `cerrar el día`
- **THEN** the day MUST remain `open`, no snapshot MUST exist, the response MUST ask `¿Confirmas el cierre?`, and `daily_close_preparation@1.data.confirmation_token` MUST be a `closing_confirm` token

#### Scenario: Phrase alone does not close
- **WHEN** the actor posts `confirmar cierre` with no `client_context.confirmation_token`
- **THEN** the response MUST clarify with `confirmation_required` and no snapshot MUST be written

### Requirement: Close guards and difference policy
Under the operational-day lock, `closing.confirm@1` MUST write a snapshot only when the day exists, `status=open`, a current `CashCount` belongs to that day, `summarize_day` succeeds, no snapshot exists yet, and the token is valid for that locked state. `cash_status` `balanced`, `short`, and `over` MUST all be allowed. `not_counted` MUST clarify with `cash_count_required` and MUST NOT close. A balanced day MUST NOT close without the confirm phrase and a matching token. The signed difference MUST be stored unchanged. An `open` or `ready_to_charge` session MUST NOT block confirmation and MUST NOT be included in the snapshot. `closed_at` MUST be the single UTC clock reading used to derive today's business date for that request. `business_date` on the snapshot MUST be copied from the locked day.

#### Scenario: Balanced close
- **WHEN** expected cash is `22.50`, the current count is `22.50`, and the actor confirms with a matching unexpired token
- **THEN** one snapshot MUST exist with `cash_difference` `0.00` and `cash_status=balanced`, and the day's `status` MUST be `closed`

#### Scenario: Shortage close preserves the difference
- **WHEN** expected cash is `22.50`, the current count is `20.00`, and the actor confirms with a matching token
- **THEN** the snapshot MUST store `counted_cash` `20.00` and `cash_difference` `-2.50`, and no payment or count MUST be adjusted

#### Scenario: Overage close preserves the difference
- **WHEN** expected cash is `22.50`, the current count is `25.00`, and the actor confirms with a matching token
- **THEN** the snapshot MUST store `cash_difference` `2.50` and `cash_status=over`

#### Scenario: Missing count blocks close
- **WHEN** the day exists and has no current `CashCount` and the actor posts `confirmar cierre`
- **THEN** the response MUST clarify with `cash_count_required`, the day MUST remain `open`, and no snapshot MUST exist

### Requirement: Stale confirmation does not close
A token with a bad signature, a wrong `typ`, an expiry in the past, or a mismatched `business_id` or `actor_id` MUST clarify with `confirmation_invalid` and MUST NOT write. A token that verifies but whose `operational_day_id`, current `cash_count_id`, or fingerprint differs from the locked state MUST clarify with `confirmation_stale`, MUST return the refreshed preparation and a new token, and MUST use the text `El cierre cambió. Revisa los datos y confírmalo otra vez.` It MUST NOT insert a snapshot or change `status`.

#### Scenario: Sale between prompt and confirm
- **WHEN** the token was issued for expected cash `22.50` and a later cash sale changes expected cash before confirm
- **THEN** the confirm MUST NOT close, the day MUST remain `open`, and the response MUST show the new expected cash and a new token

#### Scenario: Recount between prompt and confirm
- **WHEN** the token names a `cash_count_id` that is no longer current
- **THEN** the confirm MUST NOT close and MUST NOT freeze the superseded count

### Requirement: Confirm transaction order
The write MUST run in one application-owned transaction in this order: peek `lumo.message.confirm_close`; read timezone and currency; take one clock reading; derive today's business date; lock today's day `FOR UPDATE`; peek again; if `closed`, read back the snapshot; if open and uncounted, clarify; recompute `summarize_day` under the lock; verify the token; reserve idempotency only when a snapshot will be inserted; insert the snapshot while status is still `open`; update status to `closed` only where `status=open`; write audit; enqueue one outbox event; complete idempotency; commit. Success and `daily_close_confirmed@1` MUST be produced only after commit. A failure before commit MUST leave the day `open` and MUST leave no snapshot, no `closing.confirm@1` audit, and no `closing.confirmed` event.

#### Scenario: Rollback leaves the day open
- **WHEN** a confirm writes the snapshot and the status change and then fails before commit
- **THEN** the day MUST remain `open`, no snapshot MUST remain, and no close audit or outbox row MUST remain

### Requirement: Close idempotency audit and outbox
The message path MUST use `operation_type` `lumo.message.confirm_close`. The request hash MUST cover the raw message, `conversation_id`, and the token string. The same key and hash MUST return the stored body and MUST NOT insert a second snapshot, audit row, or event. The same key and a different hash MUST return `IDEMPOTENCY_CONFLICT` and MUST NOT write. A different key after the day is already `closed` MUST return the existing snapshot as `daily_close_confirmed@1` and MUST NOT insert a snapshot, an audit row, an outbox row, or an idempotency row. A clarify MUST NOT reserve a key. The successful close MUST write one audit action `closing.confirm@1` whose `before_payload` has `status=open`, `operational_day_id`, and `cash_count_id`, and whose `after_payload` has the snapshot id, the cash count id, the frozen totals, `cash_status`, `closed_at`, `previous_status=open`, and `new_status=closed`. It MUST enqueue exactly one `closing.confirmed` outbox event with those frozen values. A later read MUST use the snapshot row, not the audit row.

#### Scenario: Same-key replay
- **WHEN** the actor resubmits the same confirm message, token, and idempotency key after a successful close
- **THEN** the original body MUST be returned and exactly one snapshot and one `closing.confirmed` event MUST exist

#### Scenario: Different key after close
- **WHEN** the day is already `closed` and the actor posts `confirmar cierre` with a new idempotency key
- **THEN** the response MUST describe the existing snapshot, and no second snapshot, audit, outbox, or `lumo.message.confirm_close` row MUST be created

#### Scenario: Close audit and outbox once
- **WHEN** a confirm commits
- **THEN** exactly one `closing.confirm@1` audit row and exactly one `closing.confirmed` outbox row MUST exist for that snapshot

### Requirement: Concurrent close and recount serialize on the day
Two `closing.confirm@1` calls for the same day MUST serialize on `SELECT … FOR UPDATE` of that row. Exactly one snapshot and one `closing.confirmed` event MUST result. The loser MUST take the already-closed read-back. A cash recount and a confirm MUST take the same lock. If the recount commits first, the confirm MUST see the new current count and MUST NOT close on the old token. If the confirm commits first, the recount MUST clarify with `operational_day_closed` and the text `La jornada de hoy ya está cerrada. No puedo cambiar el conteo.` Advisory locks, Redis, and serializable isolation MUST NOT be introduced.

#### Scenario: Two concurrent confirms
- **WHEN** two confirmations with different idempotency keys and the same matching token run concurrently
- **THEN** exactly one snapshot and one `closing.confirmed` event MUST exist

#### Scenario: Confirm races a recount
- **WHEN** a recount and a confirm lock the same open day
- **THEN** the loser MUST observe the winner's committed state, and the snapshot MUST reference only a count that was current at close

### Requirement: Successful close resolves open Daily Close WorkItems
In the same transaction that inserts the `ClosingSnapshot` and sets the day to `closed`, `closing.confirm@1` MUST resolve the one open WorkItem for that day with `resolution_code=day_closed`, `resolution_actor_type=business`, and the confirmer's actor id. It MUST NOT insert a WorkItem, a `NextBestAction` row, or an OutcomeRun. A short or over day MUST be closable while its only open row is `cash_difference_review`. `balanced`, `short`, and `over` MUST remain closable. `not_counted` MUST still clarify with `cash_count_required` and MUST NOT close. A clarify or stale confirmation MUST NOT resolve WorkItems by itself. A same-key replay and a different-key read-back of an already closed day MUST NOT resolve rows again and MUST NOT insert a second snapshot.

#### Scenario: Short close still commits and clears active work
- **WHEN** expected cash is `22.50`, the current count is `20.00`, the only open Daily Close WorkItem is `cash_difference_review`, and the actor confirms with a matching token
- **THEN** the snapshot MUST store `cash_difference` `-2.50` and `cash_status=short`, the day MUST be `closed`, that difference row MUST be `resolved` with `resolution_code=day_closed` and `resolution_actor_type=business`, and no `close_confirmation_required` row needs to have existed or be inserted

#### Scenario: Not counted still cannot close
- **WHEN** the actor confirms and no current `CashCount` exists
- **THEN** the response MUST clarify with `cash_count_required`, the day MUST stay `open`, and no snapshot MUST be written

#### Scenario: Already closed read-back does not rewrite WorkItems
- **WHEN** the day is already `closed` and a new confirm key returns the existing snapshot
- **THEN** no additional WorkItem resolve audit MUST be written for that read-back
