## Purpose

Sale corrections for Carrota Build A: active-sale item removal and confirmed-sale void with preserved history, live aggregate exclusion, and factual Event Memory. (Synced from change build-a-carrota-sale-corrections; Purpose TBD refinement welcome.)

## Requirements

### Requirement: Active sale item removal is backend-authoritative
`sale.remove_item@1` MUST delete exactly one persisted `SaleItem` from an active `SaleSession` whose status is `open` or `ready_to_charge`. The workflow MUST lock the session row `FOR UPDATE` before inspecting status or deleting the line. After a successful remove, remaining items MUST remain visible in persistence order, and the derived session total MUST equal the Decimal sum of remaining `line_total` values. Removing the final item MUST leave the session active with zero items and total `0.00`. Removing an uncommitted item MUST NOT create a confirmed sale, a `Payment`, an OperationalDay attachment, or a factual Event Memory row. Flutter and the LLM MUST NOT recompute the session total.

#### Scenario: Remove one of two open items
- **WHEN** an `open` session has items totaling `22.50` and `10.00` and `sale.remove_item@1` targets the `10.00` line
- **THEN** that `SaleItem` MUST be gone, the remaining line MUST still exist, session status MUST stay `open`, and the derived total MUST be `22.50`

#### Scenario: Remove the final item leaves an empty active sale
- **WHEN** an `open` session has one item and that item is removed
- **THEN** the session MUST remain `open` with zero `SaleItem`s, derived total `0.00`, and no `Payment` or Event Memory row MUST be created

#### Scenario: Remove from ready_to_charge keeps chargeable when items remain
- **WHEN** a `ready_to_charge` session has two items and one is removed
- **THEN** status MUST remain `ready_to_charge`, the derived total MUST equal the remaining line total, and the response MUST compose a fresh `sale_summary@1` with new payment actions for that session

#### Scenario: Emptying ready_to_charge demotes to open
- **WHEN** a `ready_to_charge` session has one item and that item is removed
- **THEN** status MUST become `open`, zero items MUST remain, and payment actions MUST NOT be offered for an empty sale

#### Scenario: Remove refused on confirmed or voided
- **WHEN** `sale.remove_item@1` targets a `confirmed` or `voided` session
- **THEN** the operation MUST fail without deleting any `SaleItem`, and the session MUST remain unchanged

### Requirement: Payment actions issued before a ready_to_charge remove become stale
While a session is `ready_to_charge`, each composed `sale.pay.cash@1`, `sale.pay.card@1`, and `sale.pay.transfer@1` token MUST bind the session's persisted integer `sale_revision` claim in addition to `sale_session_id`. That claim MUST equal `sales.sale_sessions.sale_revision` at mint time. A successful `sale.remove_item@1` on that `ready_to_charge` session MUST persist `sale_revision = sale_revision + 1` under the session row lock. After that remove, any previously emitted payment action token whose `sale_revision` claim no longer matches the locked session column MUST return reason `ui_action_stale` and MUST NOT record a `Payment`, change status, or write transition audit/outbox/idempotency for commit. The post-remove `sale_summary@1` MUST mint fresh payment actions bound to the new persisted `sale_revision` and reflecting the new server total. When remove empties the session to `open`, no payment actions MUST be composed. Flutter MUST NOT supply, invent, or recompute totals or `sale_revision` to revive a stale payment action. In-memory or client-only revision MUST NOT be used.

#### Scenario: Old pay token is stale after remove
- **WHEN** a `ready_to_charge` summary minted pay tokens, then one item is removed leaving at least one item, and an old `sale.pay.cash@1` token is posted
- **THEN** the response MUST be `ui_action_stale`, the session MUST remain `ready_to_charge` without a new `Payment`, and only a freshly composed pay token for the new revision MAY commit later

#### Scenario: Fresh pay token after remove may commit
- **WHEN** after that remove the merchant taps a newly composed `sale.pay.cash@1` for the updated summary
- **THEN** commit MUST use the server-derived total of the remaining items and MUST NOT accept a client total

#### Scenario: Empty after remove offers no pay actions
- **WHEN** the last ready_to_charge item is removed
- **THEN** the response MUST NOT include `sale.pay.cash@1`, `sale.pay.card@1`, or `sale.pay.transfer@1`

### Requirement: Confirmed sale void preserves history
`sale.void@1` MUST transition a `confirmed` `SaleSession` whose OperationalDay is `open` to `voided` without deleting the session, its `SaleItem`s, or its `Payment`. The mutate path MUST persist non-null `voided_at`, `voided_by_actor_id`, and a non-empty `void_reason`, and MUST keep the existing `operational_day_id` and `confirmed_at`. `Payment.status` MUST remain `recorded`.

#### Scenario: Void keeps rows and metadata
- **WHEN** a confirmed cash sale of `22.50` is voided with reason `cobro duplicado`
- **THEN** that session MUST have `status=voided`, the same items and payment MUST still exist, `void_reason` MUST be `cobro duplicado`, and `voided_at` and `voided_by_actor_id` MUST be non-null

#### Scenario: Physical delete is forbidden
- **WHEN** a confirmed sale is voided
- **THEN** no `sale_sessions`, `sale_items`, or `payments` row for that sale MUST be deleted

### Requirement: Repeated void is a stable non-mutating read-back
When the target session is already `voided`, `sale.void@1` and `sale.void.confirm@1` MUST return a stable non-mutating read-back of the voided sale UI and MUST NOT change void metadata, MUST NOT insert a second `sale_voided` business event, MUST NOT write a new transition audit or `sale.voided` outbox event, and MUST NOT re-run daily-close maintenance as a side effect of that call. Same-key idempotent replay of the original successful void MUST return the original body. A different key against an already-voided session MUST follow this read-back. Sessions in any status other than `confirmed` (mutate candidate) or `voided` (read-back) MUST be refused without mutation.

#### Scenario: Second void returns voided read-back
- **WHEN** the session is already `voided` and `sale.void@1` is invoked with a new idempotency key
- **THEN** the response MUST present the voided sale, exactly one `sale_voided` event MUST exist for that session, and no additional void audit or outbox row MUST be written for that call

#### Scenario: Void refused on open or ready_to_charge
- **WHEN** `sale.void@1` targets an `open` or `ready_to_charge` session
- **THEN** the operation MUST fail without changing status and without writing void metadata or memory

### Requirement: Void mutate is allowed only on an open OperationalDay
The mutate path of `sale.void@1` MUST require the sale's `OperationalDay.status` to be `open`. When the day is `closed` and the session is still `confirmed`, the operation MUST refuse without mutating the sale, payment, snapshot, or memory. This change MUST NOT implement day reopen or ClosingSnapshot rewrite. Already-voided read-back is independent of attempting to reopen a closed day.

#### Scenario: Open day void succeeds
- **WHEN** the sale's OperationalDay is `open` and `sale.void@1` runs with a valid reason on a `confirmed` session
- **THEN** the session MUST become `voided` and the day MUST remain `open`

#### Scenario: Closed day void is refused
- **WHEN** the sale's OperationalDay is `closed` and `sale.void@1` is invoked against a still-`confirmed` session
- **THEN** the session MUST stay `confirmed`, no void metadata MUST be written, and no `sale_voided` event MUST be inserted

### Requirement: Voided sales stop contributing to live operational aggregates
After a successful void, live aggregations for that OperationalDay MUST exclude the voided session from gross sales total, valid sale/operation count, payment-method totals, expected cash, Daily Close preparation figures, and Business Stream / Hoy open-day factual totals. Those aggregates MUST continue to count only `status=confirmed` sessions. A voided sale MUST remain visible for audit export and Memoria.

#### Scenario: Gross and count drop after void
- **WHEN** an open day had two confirmed sales totaling `47.00` and one of them for `22.50` is voided
- **THEN** live `sale_count` MUST be 1 and live `gross_sales_total` MUST be `24.50`

#### Scenario: Expected cash drops for a voided cash sale
- **WHEN** the only confirmed cash sale of `22.50` is voided on an open day
- **THEN** live `expected_cash` MUST be `0.00`

### Requirement: Cash count consequence after void
When a current `CashCount` exists and a void changes live `expected_cash`, the system MUST preserve the recorded counted amount, recompute `cash_difference` and `cash_status` from live expected cash, and re-sync Daily Close WorkItems / OutcomeRun so that Caja cuadrada / `ready_to_close` is invalidated when the difference is no longer balanced. Outstanding close confirmation tokens whose preparation fingerprint no longer matches MUST become stale on confirm attempt. The void transaction MUST NOT rewrite historical `CashCount` amounts or an existing `ClosingSnapshot`.

#### Scenario: Balanced count becomes short after voiding cash
- **WHEN** expected cash and counted cash are both `22.50` (`balanced`) and that cash sale is voided
- **THEN** counted cash MUST remain `22.50`, expected cash MUST be `0.00`, difference MUST be `22.50` with status `over`, and `close_confirmation_required` MUST NOT remain the sole ready-to-close path as if still balanced

#### Scenario: Counted amount is not rewritten
- **WHEN** a void changes expected cash after a cash count
- **THEN** the current `CashCount.amount` MUST equal the previously recorded counted amount

### Requirement: Void confirmation shows before and after financial impact
Before a confirmed sale is voided, the merchant MUST see an explicit confirmation that includes server-computed before and after impact for at least gross sales total and sale count, and when a current cash count exists, expected cash and cash difference. Flutter MUST render those server strings and MUST NOT calculate the impact. Confirming without a non-empty reason MUST NOT void. The confirmation path is entered from Memoria via `sale.void.request@1` (see `memoria-timeline`); Inicio and Hoy MUST NOT offer void entry.

#### Scenario: Confirm shows impact
- **WHEN** the merchant opens void confirmation for a `22.50` sale on a day whose gross is `47.00` with two sales
- **THEN** the confirmation payload MUST show before gross `47.00` / count 2 and after gross `24.50` / count 1 from the server

#### Scenario: Cancel leaves the sale confirmed
- **WHEN** the merchant dismisses void confirmation without confirming
- **THEN** the session MUST remain `confirmed` and no void metadata MUST exist

### Requirement: Corrections write factual Event Memory
A successful void **mutate** (`confirmed` → `voided`) MUST insert exactly one `operations.business_events` row with `event_type=sale_voided` in the same write transaction after the session is `voided`. A voided read-back MUST NOT insert another row. Memoria MUST be able to present that event as "Venta anulada". Item removal MUST NOT write Event Memory.

#### Scenario: Void writes sale_voided
- **WHEN** a confirmed sale is voided
- **THEN** exactly one `sale_voided` business event MUST exist for that `sale_session_id` and the prior `sale_confirmed` event MUST still exist

#### Scenario: Remove item writes no memory
- **WHEN** an active sale item is removed
- **THEN** no `business_events` row MUST be inserted for that remove
