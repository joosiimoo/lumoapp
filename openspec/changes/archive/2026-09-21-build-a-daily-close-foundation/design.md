## Context

`build-a-operational-day-foundation` is archived. Alembic head is `0005_operational_day`. `operations.operational_days` holds one `open` row per `(business_id, business_date)`, created lazily inside the confirming `sale.commit@1` transaction (ADR-016). A confirmed `SaleSession` stores `operational_day_id` and `confirmed_at`, and carries exactly one `sales.payments` row with `method` in (`cash`, `card`, `transfer`), `status=recorded`, `amount numeric(12,2)` (ADR-015). `operational_day.summary@1` is a registered read that aggregates `sale_count`, `gross_sales_total`, `cash_total`, `card_total`, and `transfer_total` from those rows. Registered UI is `sale_item_added@1`, `sale_summary@1`, `sale_confirmed@1`, `operational_day_summary@1`. Hoy, Memoria, and Negocio are Flutter placeholders.

Authority for this slice:

- PRD §7.9: Lumo calculates expected cash from cash-paid sales, requests and records the real count, and presents the difference explicitly. Build A does not correct or hide a difference.
- SRS RF-A-081 (`CashCount` keeps amount, currency, actor, timestamp), RF-A-082 (`cash_difference = counted_cash - expected_cash` computed in the backend), RF-A-083 (a non-zero difference is shown and never silently adjusted), RB-A-009 (card and transfer do not increase expected cash), RB-A-010 (a difference is not auto-corrected).
- SRS §11 permission catalog includes `closing.submit_cash_count`. Architecture §10.1 names `closing.prepare`, `closing.submit_cash_count`, `closing.confirm`. Architecture §11.2 lists table `cash_counts`. Architecture §12 lists "CashCount registrado" as an Event Memory fact.
- Design System §4.18 places "Preparar el cierre del día" on Hoy and §10 records that no closing screen exists; §5 records `cash difference` as **not implemented**.
- PRD v0.11 `CashCount` (with `closing_snapshot_id`, `evidence_ids`, `note`, `supersedes_cash_count_id`) and `ClosingSnapshot` are vision, not Build A scope. SRS RF-A-084/085 (confirm and commit the close) are explicitly excluded from this slice.

Inspection constraints that shape the design:

- Money columns in `sales` and `operations` are `numeric(12,2)`. Stay on that scale; do not introduce `numeric(19,4)` for one table.
- RLS is `ENABLE` + `FORCE` with policy `tenant_isolation` using `business_id::text = current_setting('app.current_business_id', true)`. `business_id` is copied from `TenantContext`.
- `ToolRegistration.permission` is declarative metadata today; nothing enforces it at runtime. Declaring the SRS permission name costs nothing and keeps the registry honest.
- The scripted interpreter matches closed phrases after `normalize_closed_phrase` (NFKD fold, drop combining marks, lowercase, collapse whitespace, strip one surrounding layer of `¿?¡!`). It has no repository access.
- `OperationsRepository.summarize_day` already produces `cash_total` for a day. Expected cash must reuse that aggregation so the summary card and the preparation card cannot disagree.
- `get_db` owns the request transaction; workflows write inside it and success is composed post-commit. `X-Debug-Fail-After-Write` forces rollback in local/test.
- `clear_tenant_sale_mutations` deletes payments, items, sessions, then operational days, plus the sale audit/outbox/idempotency rows. Cash counts must slot in before operational days.

## Goals / Non-Goals

**Goals:**

- Lumo can state expected cash for today's `OperationalDay` from persisted confirmed cash payments.
- The merchant can say how much cash is physically there in one closed phrase, and that count is persisted with actor and timestamp.
- Lumo reports a signed difference and a derived status, computed only in the backend.
- A recount before the close is possible, and the earlier count remains reconstructible.
- Nothing in this slice closes a day.

**Non-Goals:**

- Everything in the proposal's Non-goals, in particular `closing.confirm`, `OperationalDay.status=closed`, `ClosingSnapshot`, gates, WorkItems, tolerance, denominations, and the Hoy screen.
- Changing sale lifecycle, payment shape, day membership, or `operational_day.summary@1`.

## Decisions

### 1. `expected_cash` is cash payments of the day, nothing else

```text
expected_cash = SUM(sales.payments.amount)
WHERE payments.status = 'recorded'
  AND payments.method = 'cash'
  AND payments.sale_session_id IN (
        SELECT id FROM sales.sale_sessions
        WHERE business_id = :tenant
          AND operational_day_id = :day
          AND status = 'confirmed')
```

Decimal only, quantized to two places, empty sum is `0.00`, currency is `businesses.currency`. It MUST be produced by the same repository aggregation that feeds `operational_day.summary@1`, so `expected_cash` always equals that read's `cash_total`.

Build A has **no opening float**. `grep` over the PRD, SRS, Architecture, and Design System finds no opening float, `fondo de caja`, starting cash, or denomination concept, so none is invented. Card and transfer are excluded by RB-A-009. Expenses, withdrawals, deposits, refunds, voids, and tips are excluded because no Build A requirement defines them; they are deferred to the future close workflow, where the formula becomes `opening_float + cash_sales − cash_out ± adjustments` only when a change owns those entities.

Expected cash is always live, computed at read time. A count taken before a later cash sale therefore compares against the newer expected value. That is honest for a preparation surface and avoids a stored snapshot that can drift. The frozen expected-cash snapshot belongs to `ClosingSnapshot` in Build B.

Rejected: derive expected cash from `sale_items.line_total`. The payment amount is already the authoritative sale total and carries the method.

### 2. `CashCount` entity

Table `operations.cash_counts`:

| Column | Type | Rule |
|---|---|---|
| `id` | UUID (v7) | PK |
| `business_id` | UUID | tenant, copied from `TenantContext` |
| `operational_day_id` | UUID | composite FK `(operational_day_id, business_id)` → `operational_days (id, business_id)` |
| `actor_id` | UUID | who counted (SRS RF-A-081) |
| `amount` | `numeric(12,2)` | counted cash, `>= 0` CHECK |
| `currency` | `VARCHAR(3)` | business currency snapshot |
| `source` | `VARCHAR(32)` | CHECK `manual_capture` only |
| `counted_at` | `timestamptz` | the injectable UTC clock reading for the write |
| `supersedes_cash_count_id` | UUID NULL | tenant-safe self-reference to the count this one replaces, `UNIQUE` |
| `superseded_by_id` | UUID NULL | tenant-safe self-reference to the count that replaced this one, `UNIQUE` |
| `created_at` / `updated_at` | `timestamptz` | standard mixin |

Indexes and constraints:

- `UNIQUE (operational_day_id) WHERE superseded_by_id IS NULL` — exactly one **current** count per day. This partial unique index is **immediate**; a partial unique index cannot be a deferrable constraint, and it is not made one.
- `UNIQUE (id, business_id)` — the target of both self-references; `INDEX (business_id)`; `INDEX (operational_day_id)`.
- Both self-references are **composite and tenant-safe**, never by id alone:

  ```text
  FOREIGN KEY (supersedes_cash_count_id, business_id)
    REFERENCES operations.cash_counts (id, business_id)

  FOREIGN KEY (superseded_by_id, business_id)
    REFERENCES operations.cash_counts (id, business_id)
    DEFERRABLE INITIALLY DEFERRED
  ```

  A chain therefore cannot cross tenants even if application code supplies a foreign id: a `(id, business_id)` pair from another business has no matching row under this tenant's `business_id`, so the database rejects it. FORCE RLS stays as defense in depth, not as the only barrier. `MATCH SIMPLE` means a NULL link column leaves the FK unenforced, which is correct for the head and tail of a chain.
- `superseded_by_id`'s composite FK MUST be `DEFERRABLE INITIALLY DEFERRED` because a recount updates the previous row to point at the new row *before* that row exists (decision 3). `supersedes_cash_count_id`'s composite FK stays **immediate**: the row it points at already exists when the new row is inserted. Both `UNIQUE (supersedes_cash_count_id)` and `UNIQUE (superseded_by_id)` stay immediate.
- CHECK `superseded_by_id IS DISTINCT FROM id` and CHECK `supersedes_cash_count_id IS DISTINCT FROM id`.

No `note`, `evidence_ids`, `closing_snapshot_id`, `denominations`, `expected_cash`, or `cash_difference` column. The difference is derived (decision 4). Storing expected cash on the row would freeze a value that this slice deliberately keeps live, and the write's audit row already carries the expected cash and difference observed at count time as evidence.

Domain `CashCount` is a frozen dataclass in `backend/app/domain/operations/cash_count.py` and MUST NOT import SQLAlchemy. `CashCountRow` goes in `backend/app/infrastructure/persistence/models.py` with the other rows; queries extend `backend/app/infrastructure/persistence/operations.py`. This matches the existing directory split; no new package layout is introduced.

Rejected: one mutable row per day with `UNIQUE (operational_day_id)` and an in-place `UPDATE`. It is one column smaller but the previous amount survives only in audit, while SRS RF-A-081 and PRD v0.11 RF-069 ask the count itself to preserve corrections, and PRD v0.11 already names `supersedes_cash_count_id`. Append-only also gives the future `ClosingSnapshot` a stable count id per attempt.

Rejected: an `attempt_sequence` integer plus `is_current` boolean. The supersede links express order without a counter that concurrent writers must agree on.

Rejected: self-references by `id` alone. `id` is unique, so the FK would accept a row from another business and leave tenant separation entirely to RLS and to application code. The composite reference costs nothing extra — `UNIQUE (id, business_id)` already exists for the day reference pattern — and turns a cross-tenant chain into a database error.

### 3. Recount, current value, and the no-day rule

The **current** count for a day is the single row with `superseded_by_id IS NULL`. A recount appends a new row and links it bidirectionally with the previous one in the same transaction. Superseded rows are never deleted or edited again after that one link write.

**Write order matters, and it is update-then-insert.** With the day row already locked `FOR UPDATE`:

```sql
-- 1. day already locked: SELECT … FROM operations.operational_days
--    WHERE business_id = :tenant AND business_date = :today FOR UPDATE
-- 2. read the current count
SELECT id, amount FROM operations.cash_counts
WHERE business_id = :tenant
  AND operational_day_id = :day
  AND superseded_by_id IS NULL;

-- 3. generate new_count_id in the application (new_uuid7())

-- 4. retire the previous current row FIRST
UPDATE operations.cash_counts
SET superseded_by_id = :new_count_id, updated_at = :now
WHERE id = :previous_id AND business_id = :tenant;

-- 5. then insert the new current row
INSERT INTO operations.cash_counts
  (id, business_id, operational_day_id, actor_id, amount, currency, source,
   counted_at, supersedes_cash_count_id, superseded_by_id, created_at, updated_at)
VALUES
  (:new_count_id, :tenant, :day, :actor, :amount, :currency, 'manual_capture',
   :counted_at, :previous_id, NULL, :now, :now);

-- 6. audit, outbox, complete idempotency
-- 7. COMMIT  → deferred self-FK is validated here
```

Why this ordering never allows two current rows: the partial unique index only contains rows whose `superseded_by_id IS NULL`. Step 4 sets that column on the previous row, so the previous row **leaves** the index before step 5 runs; step 5's insert then enters an index that has no row for that `operational_day_id`. At no instant between statements do two rows satisfy the predicate, so the immediate index never has to tolerate a transient duplicate. The rejected insert-then-update order would put the new row into the index while the previous row is still in it, and the immediate partial unique index would abort the transaction.

Step 4 writes an id that does not exist yet, which is exactly why `superseded_by_id`'s composite FK is `DEFERRABLE INITIALLY DEFERRED`: PostgreSQL defers that referential check to `COMMIT`, by which point step 5 has created the row. Deferring only that one FK keeps every other constraint immediate, so a genuinely wrong link still fails at commit rather than passing silently. `supersedes_cash_count_id` needs no deferral because its target is the already-committed previous row.

Rollback needs no compensating write. Steps 4 and 5 are in one transaction, so a failure between them — or anywhere before commit — restores the previous row to `superseded_by_id IS NULL` automatically and leaves no new row. The previous count is current again, with its original `amount`, `actor_id`, and `counted_at` untouched.

The first count for a day skips step 2's result and step 4: it inserts one row with both link columns NULL.

Rejected: insert the new row first and update the previous row afterwards. Both rows would satisfy `superseded_by_id IS NULL` at the moment of the insert and the immediate partial unique index would reject it.

Rejected: drop the partial unique index and rely on the day lock alone. The index is the only structural guarantee that "one current count" survives a future code path that forgets the lock.

Rejected: make the whole supersede write a single `UPDATE … RETURNING` plus `INSERT … SELECT`. It does not remove the forward reference, so it still needs the deferred FK, and it hides the ordering that the invariant depends on.

Rejected: keep `superseded_by_id` NULL and infer current-ness from `MAX(counted_at)` or a `created_at` ordering. Ties are possible, the invariant becomes a query convention instead of a constraint, and PRD v0.11 already names the bidirectional link.

A `CashCount` requires an existing `OperationalDay`. Recording cash MUST NOT insert a day, because ADR-016 makes the confirming `sale.commit@1` the only creator of a day and `not_started` is the absence of a row. When no day exists for today's business date, the write is refused as a non-mutating clarification (`CLOSE-001`, reason `operational_day_not_started`): Lumo answers that there are no sales registered today, and no row, audit, outbox, or idempotency record is written. Requesting preparation with no day returns the deterministic not-started payload and also writes nothing.

A day with sales but zero cash sales has `expected_cash = 0.00`; counting is allowed there and `120.00` is an overage of `120.00`. That is the correct, visible outcome under RB-A-010.

### 4. Difference and status are derived, never stored, never client-side

```text
cash_difference = counted_cash − expected_cash      (Decimal, two places, signed)

counted_cash IS NULL          → cash_status = not_counted, cash_difference = null
cash_difference  > 0          → cash_status = over        (sobrante)
cash_difference == 0          → cash_status = balanced
cash_difference  < 0          → cash_status = short       (faltante)
```

`cash_difference` is serialized as a signed decimal string (`"-2.50"`, `"0.00"`, `"2.50"`) with the business currency. No tolerance, threshold, rounding band, or auto-adjustment exists: no authoritative Build A document defines one, and RB-A-010 forbids silent correction. The client, the interpreter, and the model never supply or recompute `expected_cash`, `counted_cash`, `cash_difference`, or `cash_status`.

### 5. Tool names, contracts, and permissions

Architecture §10.1 already names these tools, so no new vocabulary is invented.

`closing.submit_cash_count@1` — write.

- input: `{ "amount": decimal-string }`. Nothing else. No `expected_cash`, `cash_difference`, `counted_cash`, `operational_day_id`, `business_date`, `currency`, `actor_id`, or `source`. Those come from `TenantContext`, the business row, the application clock, and persisted state.
- output: the preparation payload of decision 6 plus `cash_count_id` and `supersedes_cash_count_id`.
- `permission = "closing.submit_cash_count"` (SRS §11), `policy_id = "CLOSE-001"`, `side_effect = "write"`, `requires_idempotency = true`.
- `amount` MUST be a non-negative decimal string with at most two fraction digits. `-1`, `1.005`, `abc`, and an empty string are validation failures with no write.

`closing.prepare@1` — **read**, despite the mutating-sounding Architecture name.

- input: `{}` (empty object).
- output: the preparation payload of decision 6.
- `permission = "closing.submit_cash_count"`, `policy_id = "CLOSE-002"`, `side_effect = "read"`, `requires_idempotency = false`.
- Semantics are pinned in the spec: it computes and returns state. It MUST NOT insert or update `operational_days`, `cash_counts`, sales, payments, audit, outbox, or `idempotency_records`. It MUST NOT change `OperationalDay.status`, evaluate outcome gates, create a `ClosingSnapshot`, create WorkItems, or mark anything ready to close. In PRD v0.11 §closing, "prepare" is the workflow that *assembles* the close for review; here only the cash part of that assembly exists.

`closing.confirm@1` and `closing.reopen@1` stay unregistered and keep failing `SEC-002`.

Rejected: inventing `operational_day.close_preparation@1` or `cash_count.record@1`. The Architecture registry already has canonical names, and diverging would leave the closed catalog inconsistent with §10.1. The mutating-sounding name is handled by an explicit read contract, not by renaming.

### 6. Preparation payload

```json
{
  "operational_day_id": "<uuid>|null",
  "business_date": "2026-09-21",
  "day_status": "open|null",
  "currency": "MXN",
  "sale_count": 3,
  "expected_cash": {"amount": "22.50", "currency": "MXN"},
  "counted_cash": {"amount": "20.00", "currency": "MXN"},
  "cash_difference": {"amount": "-2.50", "currency": "MXN"},
  "cash_status": "short",
  "counted_at": "2026-09-21T23:10:00+00:00",
  "cash_count_id": "<uuid>|null"
}
```

`sale_count` is the confirmed-sale count of the day; it gives the merchant the context "3 ventas" without a second request, and it is already computed by the same aggregation. `gross_sales_total`, `card_total`, and `transfer_total` are deliberately **excluded**: they do not affect expected cash, and `operational_day_summary@1` already owns the full daily split. Keeping them out stops the preparation card from becoming a second summary card.

No day: `operational_day_id`, `day_status`, `counted_cash`, `cash_difference`, `counted_at`, and `cash_count_id` are null, `sale_count` is `0`, `expected_cash` is `0.00`, `cash_status` is `not_counted`, and `business_date` is today in the business timezone.

### 7. Write transaction boundary

The step order is normative, because two of the contracts in this design depend on it: an equal-amount read-back must not leave an idempotency record, and the recount must update before it inserts. Inside the single `get_db` request transaction:

**A. Peek idempotency before anything else.** `IdempotencyService.peek` for `lumo.message.record_cash_count` (the port and the SQLAlchemy implementation already expose `peek`; it reserves nothing).

- Completed record with the same payload hash → return the stored body verbatim and stop. No lock, no expected-cash computation, no write.
- Any record with a different payload hash → `IDEMPOTENCY_CONFLICT`. No write.
- No record, or a record still `processing` or `failed` → fall through. The existing concurrent-duplicate and retry-after-failure semantics are applied later by `begin` in step G.

**B.** Read `identity.businesses` for `TenantContext` → `timezone`, `currency`.

**C.** Take one injectable UTC clock reading → `counted_at`, then `business_date = business_date_for(counted_at, business.timezone)` (existing helper, `zoneinfo`). An invalid IANA name raises and rolls the request back.

**D.** `SELECT … FROM operations.operational_days WHERE (business_id, business_date) FOR UPDATE`. No row → clarify per decision 3 and stop: no cash count, no day, no audit, no outbox, no idempotency record.

**E.** Compute `expected_cash` from persisted confirmed payments **under that lock**.

**F.** Read the current `CashCount` for the day (`superseded_by_id IS NULL`). If a current count exists and its `amount` equals the submitted amount → **stable read-back**: return current preparation and stop. It MUST NOT begin or insert an idempotency record, MUST NOT insert a `CashCount`, MUST NOT write audit, and MUST NOT emit outbox.

Only when persisted state actually has to change:

**G.** `IdempotencyService.begin` for `lumo.message.record_cash_count`, which reserves the key and applies the existing concurrent-duplicate rules.

**H.** Perform the first count (single insert, both link columns NULL) or the recount (update-then-insert exactly as in decision 3).

**I.** Audit `closing.submit_cash_count@1` with `before_payload` = previous count id and amount (or null) and `after_payload` = `cash_count_id`, `operational_day_id`, `business_date`, `amount`, `currency`, `expected_cash`, `cash_difference`, `cash_status`, `counted_at`, `supersedes_cash_count_id`.

**J.** Enqueue outbox `cash_count.recorded` with the same identifying fields.

**K.** Complete the idempotency record.

**L.** Commit — the deferred `superseded_by_id` FK is validated here. Only then compose the response text and `daily_close_preparation@1` from the committed state.

`OperationalDay.status` is not touched. No sale, item, or payment row is written. The orchestrator does not open the transaction.

Peeking before the lock (step A) is safe because a completed record is immutable persisted state; it needs no day lock to be read back. It is also necessary: acquiring the key reservation first would create an idempotency row that step F's read-back path is contractually forbidden to leave behind.

### 8. Audit and outbox

Audit is mandatory (SRS RF-A-122): action `closing.submit_cash_count@1`, route/tool `closing.submit_cash_count@1`, with the policy decision, correlation id, and idempotency key. The read writes nothing.

Outbox `cash_count.recorded` is justified, not noise: Architecture §11.6 uses the outbox so confirmed facts are not lost between commit and derived processes, and Architecture §12 lists "CashCount registrado" as an Event Memory fact alongside `payment.recorded` and `operational_day.opened`, which already emit. Exactly one event per persisted count. A replay, a read-back, a refused write, and the read emit none. No worker or broker is added.

### 9. Idempotency and repeated counts

Operation type `lumo.message.record_cash_count`, distinct from the sale operation types. The evaluation order is step A then step F of decision 7, never the reverse.

| Case | Resolved at | Behavior |
|---|---|---|
| Same key, same payload hash | A (peek) | Exact replay of the **stored original body**. No second row, audit, event, or idempotency row. |
| Same key, different payload | A (peek) | `IDEMPOTENCY_CONFLICT`. No write. |
| New key, amount equals current count | F (read-back) | **Current live preparation.** No idempotency row, no `CashCount`, no audit, no outbox. |
| New key, amount differs from current count | G–L | Recount: update-then-insert, one audit row, one event, one idempotency record. |
| New key, no count exists yet | G–L | First count. |

**Same-key replay and different-key equal-amount read-back are deliberately not the same response.**

- A **same-key replay** returns the body persisted with that idempotency record, byte for byte. If cash sales were confirmed after the original count, the replay still shows the original `expected_cash`, `cash_difference`, and `cash_status`. That is the point of an idempotency record: the same request gets the same answer, so a retried network call can never look like a different business fact.
- A **different-key equal-amount read-back** is a new request that happens not to change persisted state, so it returns **current** preparation computed at that moment: live `expected_cash`, live `cash_difference`, live `cash_status`, and the existing `cash_count_id` and `counted_at`. If a cash sale was confirmed since the count, this response shows the new difference while the replay above does not.

Rejected: reserve the key first and delete or roll back the record when the request turns out to be a read-back. It would either leave a stray row or need a nested transaction, and the existing `peek` already answers the question without reserving anything.

Rejected: treat a new key with an equal amount as a full recount so the ordering question disappears. It would append an identical row on every retried tap and inflate the supersede chain with no new business fact.

The "equal amount is a read-back" rule follows the pattern already established for `sale.totalize@1` and `sale.commit@1` read-backs: when persisted state already matches the requested outcome, the system reports it instead of duplicating rows. It also keeps a retried UI tap from inflating the supersede chain.

### 10. Concurrency

All cash-count writes for a day serialize on `SELECT … FOR UPDATE` of that day's `operational_days` row. The winner performs its update-then-insert; the loser then re-reads the current count under the lock and either supersedes it (different amount) or returns it (equal amount). No lost update is possible, and the final current row is the last transaction to commit — a deterministic ordering.

The partial unique index `UNIQUE (operational_day_id) WHERE superseded_by_id IS NULL` is the database backstop and stays immediate. Because every writer holds the day lock and retires the previous row before inserting (decision 3), a correct writer never presents two current rows to the index. If a future code path ever did, PostgreSQL rejects the second row and the request rolls back rather than leaving two current counts. `UNIQUE (superseded_by_id)` and `UNIQUE (supersedes_cash_count_id)` keep the chain linear: a row can be superseded at most once and can supersede at most one row.

Rejected: advisory locks, Redis, and serializable isolation. The day row already exists as the natural, tenant-scoped serialization point.

### 11. Interpreter phrases

Both sets match after the existing `normalize_closed_phrase`, and both are evaluated **after** payment, totalize, and day-summary matching and **before** product parsing, so `900gr zanahoria` keeps its current path.

Cash-count capture, with one numeric slot:

```text
tengo <amount> en caja
hay <amount> en caja
conte <amount>            (from "conté 120")
caja <amount>
```

`<amount>` is `\$?\d+(?:[.,]\d{1,2})?` — optional `$`, digits, optional one- or two-digit fraction with `.` or `,`. The parsed value is normalized to a Decimal string with `.`. Thousands separators are not accepted (`1,200` is ambiguous with a decimal comma), so `tengo 1,200 en caja` clarifies without mutating. A bare `120` is **not** a cash count; it stays a possible sale quantity. No currency word is interpreted; the currency is always the business currency.

These map to `intent=record_cash_count`, `candidate_tool=closing.submit_cash_count@1`, and `counted_amount=<decimal string>` (new optional `AgentDecision` field).

Close-preparation requests:

```text
preparar el cierre
preparar cierre
cuanto deberia haber en caja
efectivo esperado
```

These map to `intent=close_preparation`, `candidate_tool=closing.prepare@1`.

Explicit guard: `cerrar el dia`, `cerrar caja`, `confirmar cierre`, `cerrar la jornada` MUST follow the existing unsupported clarification, MUST NOT select any tool, and MUST NOT mutate. Lumo answers that it can prepare the close and compare cash, and that confirming the close is not available yet. This is deliberate — it keeps the vocabulary that sounds like a final close from ever reaching a write path.

The interpreter stays a pure function with no repository access, and no broad NLU is added.

### 12. Policies

- `CLOSE-001` (write): allow `closing.submit_cash_count@1` only for a registered write with a server-parsed non-negative amount and an existing `OperationalDay` for today. Clarify with `operational_day_not_started` when no day exists. Never accept `expected_cash`, `cash_difference`, `counted_cash`, `operational_day_id`, or `business_date` from the model or client.
- `CLOSE-002` (read): allow `closing.prepare@1` only as a registered read; model-supplied amounts, differences, statuses, or dates are never operational truth.
- `SEC-002` continues to deny `closing.confirm@1` and `closing.reopen@1`.

Evaluation order is unchanged: security, integrity, tenant and permissions, workflow gates, business rules, catalog and pricing, confidence, user experience.

### 13. Generative UI contract

Component `daily_close_preparation`, version `1`, `actions: []`, `text` equal to `fallback_text`.

```json
{
  "component": "daily_close_preparation",
  "version": 1,
  "data": {
    "operational_day_id": "<uuid>|null",
    "business_date": "2026-09-21",
    "day_status": "open|null",
    "currency": "MXN",
    "sale_count": 3,
    "expected_cash": {"amount": "22.50", "currency": "MXN"},
    "counted_cash": {"amount": "20.00", "currency": "MXN"},
    "cash_difference": {"amount": "-2.50", "currency": "MXN"},
    "cash_status": "short",
    "counted_at": "2026-09-21T23:10:00+00:00",
    "cash_count_id": "<uuid>"
  },
  "actions": [],
  "fallback_text": "Cierre 2026-09-21 · Efectivo esperado $22.50 · Contado $20.00 · Diferencia -$2.50 · Faltante"
}
```

`fallback_text` status words are `Sin contar`, `Caja cuadrada`, `Sobrante`, `Faltante`. When `cash_status` is `not_counted` the sentence is `Cierre <date> · Efectivo esperado $X · Falta contar efectivo`, with no counted amount and no difference — never a fabricated `0.00` difference.

Flutter registers `daily_close_preparation` version `1` and renders a compact soft card in the Inicio stream with the Lumo-mark gutter: date, `EFECTIVO ESPERADO`, `CONTADO`, `DIFERENCIA`, and a status chip built from `cash_status`. It formats server strings only. It MUST NOT subtract, compare, or re-derive status, MUST NOT show a confirm-close button, reopen, exceptions, approvals, history, or a chart. An unknown version shows `fallback_text` and runs no action. Design System §5 lists `cash difference` as not implemented, so this card is a new mapping of the documented soft-card, metric-row, and status-chip primitives, not a redesign.

PRD §10.5 `closing_ready_card` and `cash_difference_card` stay unregistered: the first asserts the close is ready, which this slice cannot assert, and the second would fragment the not-counted state into a second component.

### 14. Surface: Inicio, not Hoy

Capture and review both happen in the existing Inicio conversation stream. Hoy stays a placeholder and "Preparar el cierre del día" stays unwired.

Reasons: Design System §10 records that the closing flow is an entry point with a toast and that **no closing screen exists**, and §5 lists `cash difference` as not implemented, so there is no approved Hoy composition for this state. The Hoy screen in §10 is a hero metric card with an hourly bar chart plus 2-up metric cards, which needs charting and daily-aggregate components that this slice's non-goals exclude. PRD §7.7 and §7.9 allow the jornada and the close preparation to be driven through conversation. Building a partial Hoy now would either ship an off-design screen or pull the chart into a slice that is meant to stay small. A later change owns Hoy and can reuse this same contract.

### 15. Migration plan

File `backend/migrations/versions/0006_cash_count.py`, revision id `0006_cash_count`, `down_revision = "0005_operational_day"`.

Upgrade:

1. `CREATE TABLE operations.cash_counts` with the columns and CHECKs of decision 2 and the composite FK `(operational_day_id, business_id)` → `operations.operational_days (id, business_id)`.
2. Create `UNIQUE (id, business_id)`, `UNIQUE (supersedes_cash_count_id)`, `UNIQUE (superseded_by_id)`, the partial unique index `uq_cash_counts_current`, and indexes on `business_id` and `operational_day_id`. `UNIQUE (id, business_id)` must exist before step 3 because both self-references target it.
3. Add the two composite self-referencing foreign keys with `ALTER TABLE` after the table exists — `fk_cash_counts_supersedes` on `(supersedes_cash_count_id, business_id)` immediate, and `fk_cash_counts_superseded_by` on `(superseded_by_id, business_id)` with `DEFERRABLE INITIALLY DEFERRED`. Both reference `operations.cash_counts (id, business_id)`. Declaring them as separate `ALTER TABLE` statements keeps the deferral explicit and reviewable in the migration.
4. `ENABLE` + `FORCE ROW LEVEL SECURITY`, policy `tenant_isolation` on `business_id`, and the same `lumo_app` `SELECT, INSERT, UPDATE, DELETE` grants as `operations.operational_days`.

There is no backfill: the table is new and no prior cash data exists anywhere in the system. Consequently the migration needs none of the `0005` RLS-disable dance, and it must not touch `operational_days`, `sale_sessions`, `payments`, or the `operations` schema definition. It must not create `workflow`, `memory`, `closing_snapshots`, or `work_items`, and must not add a status value to `ck_operational_days_status`.

Downgrade drops the table (indexes, policy, and constraints go with it) and leaves schema `operations` and every sales row untouched. A successful upgrade leaves FORCE RLS on.

Application and migration ship together. A request that fails after the cash-count write rolls back through `get_db`; `X-Debug-Fail-After-Write` covers that test.

### 16. Cleanup and integrity

`clear_tenant_sale_mutations` gains, in the same transaction: delete `operations.cash_counts` for the tenant **before** `operations.operational_days` (FK) and **after** nothing else matters, plus delete `closing.submit_cash_count@1` audit rows and `cash_count.recorded` outbox rows, and `lumo.message.record_cash_count` idempotency rows. Because the supersede links are internal to the deleted set, one `DELETE` by `business_id` is enough.

`sale_integrity_orphans` gains: a cash count whose `operational_day_id` is missing, a cash count whose `supersedes_cash_count_id` or `superseded_by_id` points at a missing row **or at a row of another `business_id`**, more than one current count for a day, an audit or outbox row referencing a missing `cash_count_id`, and a `cash_count.recorded` event whose `operational_day_id` no longer exists. The cross-tenant link check is redundant with the composite foreign keys by design; it exists so the helper reports a breach if a future migration ever weakens them.

### 16b. Baseline spec repair: `conversational-sale-session`

`openspec/specs/conversational-sale-session/spec.md` still says commit "MUST NOT create an `OperationalDay`", which the archived `build-a-operational-day-foundation` change already contradicted by making `sale.commit@1` ensure and attach the day. This slice carries a delta that repairs the requirement text to the implemented baseline: commit **does** ensure and attach the `OperationalDay`, and must not create a `CashCount`, `WorkItem`, invoice, or a final Daily Close. This is a normative repair only; it adds no behavior and changes no sale code, and the existing commit scenarios stay as they are.

### 17. ADR-017

Write `docs/adr/ADR-017-cash-count-and-close-preparation.md` during implementation. Decision: expected cash is the Decimal sum of recorded cash payments of the day's confirmed sales with no opening float; `operations.cash_counts` is append-only with one current row per `OperationalDay` linked by tenant-safe composite self-references `supersedes_cash_count_id` / `superseded_by_id`, where the `superseded_by` foreign key is `DEFERRABLE INITIALLY DEFERRED` so a recount can retire the previous row before inserting the new one; `cash_difference = counted_cash − expected_cash` and `cash_status` are derived, never stored; `closing.submit_cash_count@1` is the only write and `closing.prepare@1` is a pure read; a count requires an existing day and never creates one; `OperationalDay.status` stays `open`; `closing.confirm` stays out of scope. Do not rewrite ADR-015 or ADR-016.

## Risks / Trade-offs

- [Expected cash is live, so a count taken before a later cash sale becomes stale and the status can flip from `balanced` to `short`] → Correct for a preparation read and consistent with "no frozen close in Build A". `counted_at` is returned so a later change can surface staleness. The frozen figure belongs to `ClosingSnapshot`.
- [Append-only counts cost two self-referencing columns and a partial unique index] → Bought with SRS RF-A-081 evidence, PRD v0.11 `supersedes_cash_count_id`, and a stable per-attempt id for a future close. The mutable-row alternative is recorded as rejected.
- [One deferred foreign key is the only non-immediate constraint in the schema] → It is the minimum needed to make the update-then-insert recount executable against an immediate partial unique index, it is scoped to a single column of a single table, and it is still validated at commit. The alternative — a deferrable partial unique index — does not exist in PostgreSQL, and dropping the bidirectional link would lose the chain that a future `ClosingSnapshot` needs.
- [Registering `closing.*` tools in a slice that cannot close] → Mitigated by pinning `closing.prepare@1` as `side_effect=read` with explicit MUST NOT clauses, keeping `closing.confirm@1` unregistered and denied under `SEC-002`, and clarifying on close-sounding phrases.
- [A "new key with the same amount" read-back could hide a genuine deliberate recount to the identical value] → The persisted outcome is identical either way, and the audit trail of the original count stands. Preferring a read-back matches the existing totalize and commit semantics and avoids duplicate identical rows from retries.
- [No day means the merchant cannot record cash] → Deliberate: it preserves ADR-016's single day-creation path and the meaning of `not_started`. The clarification names the reason. Counting before any sale is deferred, not silently dropped.
- [The preparation payload omits gross, card, and transfer totals] → `operational_day_summary@1` already answers that question in the same conversation, and the omission keeps expected cash unambiguous.
- [Hoy remains a placeholder while the Design System puts close preparation there] → Recorded as an explicit deferral. No off-design screen is shipped and the contract is reusable.
- [`numeric(12,2)` bounds the counted amount below ten billion] → Matches every other money column in the schema; a larger scale for one table would fragment the money model.
- [Audit carries the expected cash and difference observed at write time, which can differ from a later read] → Intentional evidence of what the merchant was told at that moment, explicitly not a source of truth for the read.

## Migration Plan

Deploy order: Alembic `0005_operational_day` → `0006_cash_count` with the application that registers the two tools, the two policies, the UI contract, and the interpreter phrases. Rollback: revert the application and `alembic downgrade 0005_operational_day`, which drops `operations.cash_counts` and discards recorded counts; sales, payments, and operational days are untouched. A failed `0006` upgrade rolls back to `0005_operational_day`.

## Open Questions

These are decided above so implementation is unambiguous. Confirm before `/opsx:apply`; if a decision is rejected, update this design and the delta specs first.

1. A cash count requires an existing `OperationalDay`; counting with no sales today clarifies instead of creating a day.
2. Counts are append-only with one current row, rather than one mutable row plus audit history.
3. A different idempotency key with an amount equal to the current count is a read-back, not a new attempt.
4. The registered names are the Architecture §10.1 names `closing.submit_cash_count` and `closing.prepare`, with `closing.prepare@1` pinned as a read.
5. The declared permission is `closing.submit_cash_count` (SRS §11) for both tools, rather than reusing `sale.create`.
6. The surface is Inicio; Hoy stays a placeholder in this slice.
7. The preparation payload includes `sale_count` but omits gross, card, and transfer totals.
8. A recount retires the previous row before inserting the new one, and `(superseded_by_id, business_id)` is the single `DEFERRABLE INITIALLY DEFERRED` constraint in the schema.
9. Both supersede references are composite `(id, business_id)` foreign keys, so tenant separation of a chain is enforced by the database and not only by RLS.
10. The idempotency key is peeked before the day lock and reserved only when persisted state changes; a same-key replay is intentionally allowed to return figures that are older than current state, while a different-key equal-amount read-back returns live figures.
11. `conversational-sale-session` is repaired in this change to say `sale.commit@1` ensures and attaches the `OperationalDay`. No sale code changes.
