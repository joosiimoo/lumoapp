## Context

Carrota can start, add items, totalize, pay, and confirm sales; OperationalDay, cash count, Daily Close, Business Stream, daily export, and factual Event Memory are live. Corrections are not.

Current sale machine is only `open` → `ready_to_charge` → `confirmed`. There is no remove-item path (`SalesPort` has `add_item` / `list_items` only). Specs and ADR-014/015 explicitly reserve void and item edit/remove as out of scope. Confirmed sales are the durable sale (`SaleSession` + `SaleItem`s + one `Payment`); there is no separate `sales.sales` table.

Live aggregates (`summarize_day`, expected cash, Business Stream open-day `factual_summary`, Daily Close preparation) filter `SaleSession.status = 'confirmed'` and `Payment.status = 'recorded'`. Export is one row per confirmed `SaleItem` with a fixed column list and no `sale_status`. Event Memory has `sale_confirmed`, `cash_count_recorded`, and `daily_close_completed` only; uniqueness is `(business_id, event_type, source_entity_type, source_entity_id)`. Cash counts are append-only; counted amount is never rewritten; expected cash and difference are live on open days. ClosingSnapshot is immutable; `closing.reopen@1` is not registered. Onboarding change `build-a-conversational-onboarding-and-minimum-configuration` stays untouched.

Authority for this carve-out: PRD v0.11 §21.7 Cancelación, §21.8 Corrección, RF-086. Build A MVP text reserved user-facing cancel; this change deliberately exposes merchant corrections for the Carrota pilot while keeping closed-day and reopen out of scope.

## Goals / Non-Goals

**Goals:**

- Safe active-sale item removal with backend-authoritative totals.
- Safe confirmed-sale void that preserves history and stops contributing to live operational money.
- Cash-count and Daily Close preparation stay coherent after a void on an open day.
- Corrections feed factual Event Memory as "Venta anulada".
- Export remains auditable: voided sales visible with explicit status, excluded from operational totals.
- Conversation-primary UX with the smallest secondary controls.

**Non-Goals:**

- Refunds, partial refunds, payment-method change, confirmed-sale line edits.
- Post-close void, day reopen, snapshot rewrite.
- Inventory, RF-009, Build B.
- Event-only void or physical delete of confirmed rows.
- Changing the paused onboarding OpenSpec change.

## Decisions

### 1. Persistence: soft status `voided` on `SaleSession` (not a void table, not delete)

Extend `SaleSessionStatus` with `voided`. Keep the session, all `SaleItem`s, and the single `Payment` (`status` remains `recorded`). Add nullable void metadata used only when voided:

- `voided_at` timestamptz
- `voided_by_actor_id` uuid (same actor model as other sale mutations)
- `void_reason` non-empty text (bounded length)

Check constraints:

- Status enum includes `voided`.
- Day membership: `voided` MUST keep non-null `operational_day_id` and `confirmed_at` (same association as when confirmed). Void does not detach the sale from its day.
- Active unique index stays `WHERE status IN ('open', 'ready_to_charge')` — voided is inactive like confirmed.

**Alternatives rejected:**

- Separate void table as source of truth → dual “is this live?” predicates and join tax.
- Event-only void → aggregates/export still count the sale.
- Physical delete → breaks audit, memory uniqueness references, and PRD §21.7.
- Flipping `Payment.status` without session status → every aggregate must special-case payments; session status is the existing membership signal.

### 2. Active item removal: hard-delete the line; no confirmed history

`sale.remove_item@1` targets one `sale_item_id` on the active session (`open` or `ready_to_charge`). Under `SELECT … FOR UPDATE` on the session:

1. Refuse if session is `confirmed` or `voided`.
2. Delete that `SaleItem` row (hard delete). Active lines are uncommitted; product requires no confirmed-sale history from this path.
3. Remaining items stay; session total is Σ remaining `line_total` (ADR-007). Empty session total is `0.00`.
4. Status rules after remove:
   - `open` with remaining or zero items → stay `open`.
   - `ready_to_charge` with ≥1 item → stay `ready_to_charge`; backend recomputes remaining items and total; composer emits a fresh `sale_summary@1` with **new** payment and remove actions.
   - `ready_to_charge` with 0 items → transition to `open` (cannot charge an empty sale; this is an explicit empty-cart demotion, not a silent reopen-for-add after payment); **no** payment actions.
5. **Stale payment actions after cart change:** each `ready_to_charge` payment action token (`sale.pay.cash@1` / `card` / `transfer`) MUST bind the session's persisted server `sale_revision` (see Decision 2a). Successful remove on a `ready_to_charge` session MUST advance that column. Any previously emitted payment token whose revision no longer matches MUST return `ui_action_stale` and MUST NOT commit. Fresh actions from the post-remove summary bind the new revision and the new derived total (total stays server-side in the card data, not as a client-supplied commit amount). Flutter MUST NOT recompute totals or invent a client-only revision.
6. Write `sale.remove_item@1` audit + outbox `sale.item.removed` in the same transaction. Do not write Event Memory (no confirmed fact).

**Alternatives rejected:** Soft-delete item flags (unnecessary for uncommitted lines); requiring reopen-to-open on every ready_to_charge remove (worse UX when merchant only drops one line before paying); leaving pre-remove payment tokens valid (would charge a stale cart/total); in-memory or client-only revision (cannot survive process restart or multi-worker and is not server-authoritative).

### 2a. Persistence: `sale_revision` on `SaleSession` (server-authored integer)

Payment-token staleness after remove requires a durable server value, not an ephemeral counter.

- Column: `sales.sale_sessions.sale_revision` — `INTEGER NOT NULL`, constrained `>= 1`.
- Initialization: every new `SaleSession` INSERT sets `sale_revision = 1`.
- Migration backfill: existing rows receive `sale_revision = 1` (no historical ready_to_charge cart mutations need higher values).
- Domain/entity/SQLAlchemy/repository: expose `sale_revision: int` on `SaleSession` and map it end-to-end.
- Increment semantics (same write transaction as the remove, after the session row is locked `FOR UPDATE`):
  - When `sale.remove_item@1` succeeds and the session status **before** the remove was `ready_to_charge`, set `sale_revision = sale_revision + 1` (whether remaining items keep `ready_to_charge` or emptying demotes to `open`).
  - When the session was `open` before remove, leave `sale_revision` unchanged (no payment actions exist for open carts).
- Do **not** advance on add-item, totalize, commit, or void.
- Payment JWT mint/verify: `sale.pay.*@1` tokens MUST include claim `sale_revision` equal to the persisted column at mint time; commit path compares claim to the locked session's current column and returns `ui_action_stale` on mismatch.
- Scope: this column exists solely for payment-action cart staleness. It is **not** a general optimistic lock for add/totalize/void; those continue to serialize via `FOR UPDATE` and status rules.

**Alternatives rejected:** Deriving staleness only from item-count/total in the token (amounts must stay out of pay tokens); hashing the cart into the JWT without a persisted counter (harder to reason about and still needs a server check source of truth); client-supplied revision.

### 3. Confirmed sale void: mutate once; voided is stable read-back

`sale.void@1` (UI confirm path binds `sale_session_id` + reason) after locking session and OperationalDay:

| Session state | Behavior |
|---------------|----------|
| `confirmed` + day `open` | Mutate: require non-empty reason → `voided` + void metadata; keep items/payment/day membership; audit `sale.void@1`, outbox `sale.voided`, one `sale_voided` event; `maintain_open_daily_close`. |
| already `voided` | **Non-mutating read-back** of the voided sale UI. No second `sale_voided` event, no new audit/outbox, no metadata rewrite, no daily-close re-sync side effects from this call. |
| `confirmed` + day `closed` | Refuse; no mutation. |
| any other status (`open`, `ready_to_charge`, …) | Refuse; no mutation. |

Same-key idempotent replay of a successful void returns the original body. A different key against an already-voided session follows the voided read-back row above (not a second mutation).

**Policy alignment:** PolicyEngine MUST NOT deny solely because the session is already `voided`—that would block the intended read-back before the workflow can return it. Policy MAY allow the void tool/action when status is `confirmed` (candidate mutate) or `voided` (candidate read-back), and MUST deny other statuses. Closed-day deny applies to the mutate path (`confirmed` on a closed day). Blank reason denies only the mutate path; voided read-back does not require re-supplying a reason to return current state.

### 4. Aggregate and close predicates stay `status=confirmed`

`summarize_day`, expected cash, Business Stream open-day facts, Daily Close preparation, and valid operation counts continue to count only `confirmed` sessions. Voided are excluded automatically once status flips — no parallel “exclude voided” flag needed beyond the status check. Closed-day reads still use ClosingSnapshot; because void is refused after close, snapshot integrity holds without reopen.

### 5. Cash-count consequence after void

If a current CashCount exists when a cash (or any) sale is voided:

- Recompute live `expected_cash` from remaining confirmed cash payments.
- Preserve the recorded counted amount (append-only CashCount rows are not rewritten).
- Recompute `cash_difference` and `cash_status` (`balanced` / `short` / `over` / `not_counted`).
- If previously balanced / ready_to_close, WorkItem sync MUST leave `close_confirmation_required` when no longer balanced and MUST surface `cash_difference_review` when short/over — i.e. invalidate Caja cuadrada / ready_to_close when appropriate.
- Outstanding `closing.confirm@1` tokens whose fingerprint includes old prep figures become `confirmation_stale` (existing fingerprint mechanism).

### 6. Event Memory: append `sale_voided`; keep `sale_confirmed`

New `event_type=sale_voided`, `source_entity_type=sale_session`, `source_entity_id=sale_session_id`, `source_type=manual_capture`, `occurred_at=voided_at`, `operational_day_id` = the sale’s day.

`facts` exactly: `sale_session_id`, `payment_id`, `payment_method`, `amount`, `currency`, `void_reason`, `voided_by_actor_id`. Money strings match existing event conventions. Do not UPDATE or delete `sale_confirmed`. Memoria maps the type to merchant copy **Venta anulada**. Day chronology shows both confirmation and later void.

Unique constraint already allows both events for one session because `event_type` differs.

### 7. Export: keep voided rows + add `sale_status` (**BREAKING**)

Current contract exports only `status=confirmed` and has no status column. Filtering voided out after status flip would hide audit history. Keeping voided without a status column would make every row look like a live confirmed sale and break consumer assumptions and gross reconciliation (`SUM(line_total)` == day gross).

Decision:

- Include sessions with `status IN ('confirmed', 'voided')` for the day.
- Insert column `sale_status` immediately after `sale_session_id` with values `confirmed` or `voided`.
- Operational reconciliation: `SUM(line_total)` and distinct-`payment_id` payment sums over **confirmed** rows only MUST equal live/open confirmed gross; voided rows are present for audit and MUST NOT be included in that equality.
- Active `open` / `ready_to_charge` still excluded.
- UI caption updates to state that the file includes confirmed and voided sales with explicit status; operational day totals elsewhere exclude voided.

This is the safest audit behavior given the existing fixed-column contract.

### 8. UX: conversation primary; Memoria-only void entry

| Surface | Control |
|---------|---------|
| `sale_item_added@1` | Secondary remove for that line (`sale.remove_item@1` JWT-bound to session + item). Unchanged. |
| `sale_summary@1` | Secondary remove per line; after success recompose summary or empty-open clarification. Unchanged. |
| `sale_confirmed@1` (Inicio) | **No Anular / no `sale.void.request@1`.** Confirmed card is informational after commit. A voided read-back of this contract MAY still render when returned by a void flow, but Inicio is not a persistent void entry point. |
| Hoy / Business Stream | **No** sale-level void actions; no individual sales list in this slice. |
| Memoria `sale_confirmed` timeline entry ("Venta registrada") | Secondary **Anular** only when the backend attaches a server-authored `sale.void.request@1` action. Eligibility is server-only: session `status=confirmed`, sale’s `operational_day_id` is the current open OperationalDay, day `status=open`. Flutter MUST NOT infer eligibility from facts or status. |

Void still uses the existing path only: `sale.void.request@1` → confirmation with server before/after impact + non-empty reason → `sale.void.confirm@1`. No second void mechanism, no new UiAction id.

**History rules:** `sale_confirmed` Event Memory remains immutable. After void, the original "Venta registrada" card remains and MUST NOT expose Anular; a separate "Venta anulada" (`sale_voided`) event remains visible. Closed-day and already-voided sales never expose Anular.

**Memoria DTO (smallest extension):** `GET /api/v1/memory/events` keeps the existing event read shape (`BusinessEventRead` fields + `local_time`). Add optional `actions` on each event. When present, each action is the generative UI action envelope (`action_id`, `option_id`, `context_token`, `idempotency_key`) plus server-authored `conversation_id` that MUST equal the JWT `conversation_id` claim so Flutter can `POST /api/v1/lumo/actions` after app restart/reload without inventing a conversation. Only eligible `sale_confirmed` events MAY include exactly one `sale.void.request@1` action; all other event types and ineligible `sale_confirmed` / `sale_voided` events MUST omit `actions` or return an empty list. Reloading Memoria remints fresh tokens/keys for still-eligible sales.

No new primary chat mode. Destructive void still requires the explicit confirm action. Flutter formats server strings only; before/after impact stays server-authored.

### 9. Idempotency and concurrency

Reuse ADR-011 patterns:

| Mutation | Idempotency operation | Concurrency |
|----------|----------------------|-------------|
| Remove item | `lumo.message.remove_sale_item` (and UI action key) | `FOR UPDATE` session; missing item after concurrent remove → stable clarify / no-op without inventing a new line; advances persisted `sale_revision` when session was `ready_to_charge` |
| Void | `lumo.message.void_sale` (and UI confirm key) | `FOR UPDATE` session + day; `confirmed`+open mutates; already `voided` read-back; other statuses refuse |

Persisted `sale_revision` (Decision 2a) is the sole payment-action cart version; it is not a general optimistic lock for every sale mutation. UI action tokens bind ids (+ `sale_revision` for pay actions); mismatched revision or otherwise stale tokens → `ui_action_stale`.

### 10. ADR required

This expands the closed sale status set, changes export schema, adds a memory event type, introduces persisted `sale_revision` for payment-action cart staleness, and defines closed-day void refusal interacting with immutable snapshots. That is architectural, not a local API tweak. Implementation MUST add **ADR-031** (sale corrections: voided status, aggregate exclusion, memory, export `sale_status`, open-day-only void, persisted `sale_revision`). Do not rewrite ADR-014/015/017/018/022/025; reference them as amended by 031 for corrections.

### 11. Migration

One Alembic revision after current head:

- Widen `ck_sale_sessions_status` to include `voided`.
- Adjust day-membership check so `voided` requires non-null day + `confirmed_at` (same as confirmed).
- Add `voided_at`, `voided_by_actor_id`, `void_reason` (NULL for non-voided; CHECK that voided rows have all three non-null / non-empty reason).
- Add `sale_revision INTEGER NOT NULL` with `DEFAULT 1` and `CHECK (sale_revision >= 1)`; backfill existing rows to `1`.
- No void metadata backfill (no historical voids).
- FORCE RLS unchanged; no `BYPASSRLS`.

Rollback: refuse deploy reverse if any `voided` row exists; otherwise drop void columns / `sale_revision` and restore checks.

## Risks / Trade-offs

- [Export column insert breaks naive CSV parsers] → Document **BREAKING**; put `sale_status` in a stable position; update Flutter caption and tests; keep formats otherwise identical.
- [Void after balanced count surprises merchant] → Confirm dialog shows before/after expected cash and that Caja cuadrada may clear; WorkItems re-sync immediately.
- [Hard-delete active items loses accidental remove evidence beyond audit/outbox] → Acceptable for uncommitted lines; audit + outbox retain the mutation; confirmed path never hard-deletes.
- [ready_to_charge stays chargeable after partial remove] → Intentional; empty demotes to `open` to block pay-on-empty; pre-remove payment tokens are revision-stale so a stale cart cannot be charged.
- [Policy deny on voided blocks read-back] → Void policy allows `confirmed` and `voided`; workflow distinguishes mutate vs read-back.
- [MVP docs said cancel not user-exposed] → Proposal states explicit Carrota pilot carve-out under v0.11 §21.7 / RF-086.

## Migration Plan

1. Land ADR-031 + Alembic + domain enums/constraints.
2. Ship remove-item end-to-end (tool, UI, tests) before void if sequencing helps, or both behind the same change tasks.
3. Ship void + memory + aggregate/export updates together so status never exists without exclusion rules.
4. Deploy API before relying on mobile remove and Memoria void actions; old clients simply lack controls.
5. Do not touch onboarding change files.
6. After Memoria-only void pivot: strip any Inicio `sale_confirmed@1` void actions; ship timeline `actions` minting before Memoria Anular UI.

## Open Questions

None blocking implementation. Resolved in this design:

- Remove allowed on `open` and `ready_to_charge` (product).
- Empty active sale allowed; empty demotes `ready_to_charge` → `open`.
- After remove on `ready_to_charge` with items remaining: stay `ready_to_charge`, advance persisted `sale_revision`, mint fresh payment actions; old pay tokens are `ui_action_stale`.
- `sale_revision` is a NOT NULL integer column on `sale_sessions`, starts at `1`, increments only on successful remove from `ready_to_charge`, never client/in-memory-only.
- Void: `confirmed`+open mutates; already `voided` is non-mutating read-back; other statuses refuse; policy does not block voided read-back.
- Void mutate only while OperationalDay open; no reopen.
- Export keeps voided + `sale_status`; operational totals exclude voided.
- ADR-031 required.
- Payment row retained with `recorded`; session status is the live/not-live signal.
