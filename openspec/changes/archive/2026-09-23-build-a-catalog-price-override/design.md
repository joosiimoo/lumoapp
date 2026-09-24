## Context

`Product.current_price` is catalog truth. `sale.add_item@1` stores that amount on a catalog `SaleItem`. A grounded merchant amount that differs clarifies under `CAT-001` / `catalog_price_mismatch` and writes no session, item, audit, outbox, or idempotency row (ADR-020). Free-concept prices are already explicit and are out of this slice.

PRD §7.5 and SRS RF-A-039 require a final price that differs from the current catalog price to keep a non-empty reason and to remain visible. The sale row itself must answer, later, what the catalog price was, what was charged, whether it differed, and why. Audit alone is not enough.

`sale_item_added@1`, `sale_summary@1`, and `sale_confirmed@1` stay version `1`. Their registry `data_schema` lists required keys only. `GenerativeUIComposer` accepts `data` as an open object. Flutter ignores unknown keys. Unknown component versions render `fallback_text` and hide the card. `unit_price` on a card is the persisted charged unit price.

Pending clarifications live in `InMemoryPendingClarificationStore`, keyed by `(business_id, actor_id, conversation_id)`. That store is not schema `memory` and not a draft `SaleItem`.

## Goals / Non-Goals

**Goals:**

- Let a merchant sell one catalog product at a grounded unit price other than `Product.current_price`, with a merchant-written reason, without changing the catalog.
- Persist the catalog price at commit time, the charged unit price, and the reason on the `SaleItem`.
- Ask for the reason before any write. On the reason turn, lock the product inside the short write transaction and use that locked price.
- Keep `sale.add_item@1` as the only add-item tool. Keep totalize, payment, OperationalDay, and Daily Close on persisted `line_total`.

**Non-Goals:**

- Catalog price updates, price history, promotions, discounts, coupons, thresholds, manager approval, customer prices, tax, inventory, learning, edit, delete, refund, receipt, invoice, mixed payment, analytics, and export.
- A free-concept price reason. `price_override_reason` stays null on `free_concept`.
- A new tool, audit action, audit table, or `sale.price.overridden` event.
- Changing `sale.commit@1` closed-day refusal.

## Decisions

### 1. SaleItem fields

Add two nullable fields. Do not add `price_source` or `pricing_mode`.

| Field | Catalog, prices equal | Catalog override | `free_concept` |
|---|---|---|---|
| `product_id` | not null | not null | null |
| `catalog_unit_price_snapshot` | `Product.current_price` at commit | `Product.current_price` at commit | null |
| `unit_price` | same as snapshot | merchant override | explicit concept price |
| `price_override_reason` | null | non-empty merchant text | null |

Override is `source_type=catalog` and `unit_price <> catalog_unit_price_snapshot`. The checks below make that equivalent to a non-blank reason, so a discriminator would only repeat the same fact.

`catalog_unit_price_snapshot` uses the existing money shape: `NUMERIC(12, 2)` and the line `currency`. No second currency column.

### 2. Database checks

Alembic `0009_catalog_price_override`, `down_revision` `0008_noncatalog_sale_item`.

Columns:

- `catalog_unit_price_snapshot NUMERIC(12, 2) NULL`
- `price_override_reason VARCHAR(200) NULL`

Keep `ck_sale_items_source` and `ck_sale_items_money_positive`. Add `ck_sale_items_catalog_price`:

- Catalog: `catalog_unit_price_snapshot IS NOT NULL` and `catalog_unit_price_snapshot > 0`, and either `unit_price = catalog_unit_price_snapshot` with `price_override_reason IS NULL`, or `unit_price <> catalog_unit_price_snapshot` with a reason that is not null, equals `btrim(price_override_reason)`, and `char_length(btrim(price_override_reason)) > 0`.
- Free concept: both new columns are null.

Both money columns are `NUMERIC(12, 2)`, so `=` and `<>` are exact. Do not compare through float or text. `VARCHAR(200)` is the length ceiling. The application rejects a longer reason before insert so PostgreSQL is not the merchant-facing error. Internal whitespace collapse stays in the application. A SQL `CHECK` that re-collapses Unicode whitespace is not required.

`fk_sale_items_product_business` stays. A catalog line still cannot point at another tenant's product.

### 3. No pricing mode

Rejected: `price_source` / `pricing_mode`. The three rows in decision 1 are already enforced. A fourth label would not reject any state the checks do not already reject.

### 4. Reason length

Maximum 200 characters after normalization. That matches `product_name_snapshot` and `MAX_DISPLAY_SPAN`. Do not use 255.

### 5. Reason text

Normalize with the same structural cleanup as `collapse_display_span`: trim and collapse whitespace to a single space. Keep accents and casing. Do not run `normalize_product_name`. Do not strip punctuation. Reject the result when it is empty or longer than 200. Do not truncate. Do not invent a reason, including "manual override", unless the merchant typed those words.

The conversational reason is the raw completion message after that cleanup. It is not an `AgentDecision` field. Do not add one.

Copy when the reason is blank: `Necesito un motivo para registrar ese precio.` Pending stays.

Copy when it is too long: `Ese motivo es demasiado largo.` Pending stays.

### 6. Pending state

Extend `PendingSaleClarification`. New `kind`: `catalog_price_override`.

Store only server-derived or previously grounded values:

- `product_query`: the merchant query that resolved uniquely
- `product_id`: the resolved id, as a consistency check, not as a substitute for a re-read
- `quantity` and `unit`
- `unit_price`: the grounded override amount, scale 2
- `observed_catalog_unit_price`: `Product.current_price` when the question was asked

Do not store a reason on the first turn. Do not create a `SaleItem`, a `SaleSession`, schema `memory`, or a durable draft. The store remains process-local and keyed by tenant, actor, and `conversation_id`.

### 7. Locked product price on the reason turn

The reason turn re-resolves `product_query` in the tenant. It then opens the existing add-item write transaction. Inside that transaction, before creating a `SaleSession`, inserting a `SaleItem`, or reserving idempotency:

1. Re-read the tenant `Product`.
2. Lock that row with `SELECT ... FOR UPDATE` (or the ORM equivalent).
3. Require the same tenant, the pending `product_id`, and an active product. Otherwise roll the transaction back, clear the pending override, and use the existing ambiguous, missing, or inactive copy.
4. Read `Product.current_price` from the locked row. That value is the only catalog price for this mutation.

Do not `UPDATE` `catalog.products`. Do not hold the transaction open while waiting for another message. Do not add a distributed lock, Redis, or a new workflow. The lock lasts only for this short transaction.

Exactly one case follows.

**Case A.** The locked price equals the pending observed price and differs from the grounded override. Commit the override in this transaction. `catalog_unit_price_snapshot` is the locked price. `unit_price` is the override. Persist the merchant reason.

**Case B.** The locked price differs from the observed price and still differs from the override. Insert nothing, create no session, and do not call idempotency. Roll the transaction back so the lock is released. After that rollback, replace the pending observed price with the locked price, keep the product, quantity, unit, and override price, and discard the typed reason. Ask again: `{Name} ahora está registrado a ${current} por {kg|unidad|paquete}. ¿Por qué lo vendiste a ${override}?`

**Case C.** The locked price equals the grounded override. Commit a normal catalog line in this transaction. Snapshot and `unit_price` are the locked price. `price_override_reason` is null. The card omits `catalog_unit_price`.

A direct `price_override` call uses the same locked read inside its write transaction. It has no pending observed price, so it does not restart a question. Equality with the locked price still stores a normal catalog line and drops the reason.

### 8. Catalog price changed

Case B is the price-change behavior. No materiality threshold. Any scale-2 difference from both the observed price and the override restarts the question. The old reason is not stored.

### 9. Override becomes the catalog price

Case C persists one normal catalog line and reserves one idempotency key. The typed reason is ignored. Success copy is the normal catalog sentence. The card's unit price is the locked catalog price.

### 10. `sale.add_item@1` input

Stay on version `1`. Do not register `sale.override_price@1` or `sale.add_override_item@1`.

Catalog input may include optional `price_override`:

```json
{
  "unit_price": {"amount": "30.00", "currency": "MXN"},
  "reason": "precio especial para cliente"
}
```

Absent `price_override` keeps today's catalog path: the server stores `Product.current_price`. A direct catalog call without `price_override` stays on the message workflow.

The conversational workflow builds `price_override` only after the reason turn. It copies the grounded amount and the normalized user message. It does not copy a model-only amount or a model-only reason.

A direct call with `price_override` must pass the same domain checks: active tenant product, positive scale-2 amount, business currency, non-empty normalized reason when the amount differs, open session, `sale.create`. Inside its write transaction it locks the product and calculates `line_total` from the charged amount. If the direct amount equals the locked price, it stores a normal catalog line and drops the reason. It must not update `Product.current_price`.

### 11. Idempotency hash

The question turn reserves nothing.

The completion turn that writes uses existing `operation_type` `lumo.message.add_sale_item`. Request hash, UTF-8, fields joined by `|`:

`catalog-price-override|v1|{conversation_id}|{product_id}|{quantity}|{unit}|{snapshot_amount}|{charged_amount}|{normalized_reason}`

`conversation_id` is empty when null. Amounts are two-decimal strings. `normalized_reason` is empty when decision 9 discards it. `snapshot_amount` is the catalog price used for that commit.

Same key and same hash replay the stored body and do not insert a second item. Same key and a different hash keep the existing idempotency conflict. A new key on a genuinely new override utterance may insert another line, as a normal add does.

Ordinary catalog adds keep their current hash. This prefix applies only to an override completion, including the equal-after-recheck path.

### 12. Audit

Action remains `sale.add_item@1`. No new audit action and no new table.

`after_payload` adds, on every add-item from this change:

- `catalog_unit_price_snapshot`: money object, or null for `free_concept`
- `price_override_reason`: string, or null

Existing `source_type`, `product_id`, `product_name`, `unit_price`, and `line_total` stay. The question turn still writes no audit. On an override commit, `policy_decision.reason_code` is `catalog_price_override` and the rule ids include `SALE-001` and `CAT-001`. A normal catalog line must not use that reason code.

### 13. Outbox

Keep `sale.item.added`. Do not add `sale.price.overridden`.

Extend the payload with `catalog_unit_price_snapshot`, `unit_price`, and `price_override_reason`. Null snapshot and null reason mean free concept or, with snapshot equal to `unit_price`, a normal catalog line. No boolean. Downstream can derive the override from those three facts.

### 14. Card contract

Do not register version `2`. A version bump would make the current renderer show only `fallback_text`.

Add optional `catalog_unit_price` as a money object:

- present on `sale_item_added@1` `data`, and on each item of `sale_summary@1` and `sale_confirmed@1`, only for a catalog override
- absent for a normal catalog line and for `free_concept`

Existing fields keep their meaning. `unit_price` is the charged unit price. `line_total` is the server total. The registry schema stays a required-key minimum. Do not set `additionalProperties: false`.

The reason is not on the card.

### 15. Which cards show the exception

All three cards. When `catalog_unit_price` is present, Flutter adds one caption under the quantity line, using the existing unit label:

`Precio ajustado · antes $20.00/kg`

Flutter formats the server amount. It does not subtract, multiply, or invent the caption when the field is absent. The caption uses the existing caption type. It is not a status chip and it does not say "override". `fallback_text` stays the success sentence without that caption.

Tomate completion text: `Agregué 0.900 kg de Tomate · $27.00`.

### 16. Cancellation

Only while `kind=catalog_price_override` is pending. After `normalize_closed_phrase`, these phrases cancel: `cancelar`, `cancela`, `no`.

Clear that pending. Write no session, item, audit, outbox, or idempotency row. Copy: `Listo, no registré ese producto.`

Do not build a general cancellation framework. `no` during a free-concept mass-basis question keeps today's behavior.

A complete sale utterance replaces the pending override and is interpreted as a new add. Detection for the scripted interpreter: `parse_sale_utterance` kind `utterance` with both a quantity and a display span. `precio especial para cliente` has no quantity, so it is a reason. `2 galletas A` and `900gr tomate a 20` are new sales.

A closed intent (totalize, payment, day summary, cash count, close) clears the pending override, writes no override line, and runs that intent.

A reason-shaped message with no pending override does not create an override. It keeps the current unsupported reply.

### 17. Downgrade

`0008` cannot store a catalog snapshot that differs from `unit_price`, or a catalog reason. Downgrade counts only catalog overrides:

```sql
source_type = 'catalog'
AND (
  price_override_reason IS NOT NULL
  OR catalog_unit_price_snapshot IS DISTINCT FROM unit_price
)
```

`NULL IS DISTINCT FROM 18.00` is true in PostgreSQL. A free-concept row has a null snapshot and a non-null `unit_price`, so an unscoped `IS DISTINCT FROM` would block downgrade of every free-concept database. The `source_type = 'catalog'` guard prevents that. Free-concept rows do not block `0009` to `0008`.

If the catalog-override count is greater than zero, raise `cannot downgrade 0009 while a catalog price override exists` and leave the revision at `0009`. Do not delete those rows and do not null the columns first.

If the count is zero, drop `ck_sale_items_catalog_price` and both columns. Normal catalog rows, whose snapshot equals `unit_price`, lose no evidence. Free-concept rows remain, including `source_type`, null `product_id`, name, `unit_price`, and `line_total`. Restore `ENABLE` and `FORCE` row level security before returning, including on the abort path. Match the `0008` pattern: disable RLS only while the migration touches every tenant's rows, then force it back on. Do not grant `BYPASSRLS`. Do not change `tenant_isolation`.

Backfill on upgrade, before the check is validated:

- `source_type=catalog`: `catalog_unit_price_snapshot = unit_price`, `price_override_reason = NULL`
- `source_type=free_concept`: both new columns `NULL`

Head revision after upgrade is `0009_catalog_price_override`.

### 18. Normal catalog price read

Today's add-item write transaction already re-reads the product with `CatalogRepository.get` after locking the `SaleSession` and before insert, and it replaces `unit_price` with that `current_price`. That get is not `FOR UPDATE`. `line_total` is calculated earlier, from the resolve-time product, so the row can mix two prices.

This change does not add a product lock or a new workflow on the normal path. The resolve-time price only decides whether to ask for a reason. The in-transaction product read is the one price for that mutation: `catalog_unit_price_snapshot`, normal `unit_price`, and `line_total` all come from it. `line_total` is `quantity_normalized *` that price through `Money.times`. Do not keep a total from the earlier read.

An override uses the locked price from decision 7 as its snapshot. Its `line_total` uses the override `unit_price`, not a second product read.

### Money and units

`line_total = unit_price.times(quantity_normalized)` once, `ROUND_HALF_UP` to `0.01`. For a normal catalog line, `unit_price` is the snapshot from decision 18, so the product is `quantity_normalized *` that one catalog price. For an override, the product uses the override unit price, not the snapshot. Flutter and the LLM do not calculate it. A total of `0.00` or less is not persisted.

Override amount: explicit in merchant text, positive `Decimal`, scale at most 2, business currency. Higher or lower than the catalog price is allowed. No percentage cap.

For a unique catalog product priced per kilogram, `900gr tomate a 30` means 30.00 MXN per kilogram and 0.900 kg. The merchant does not say "por kilo". That shortcut is the product's `pricing_type`. It does not apply to `free_concept` mass, which still requires an explicit per-kilogram basis.

For catalog `unit` or `package`, the grounded amount is the per-each price. `2 galletas A a 10` with Galleta A at 12.00 asks for a reason, then stores quantity 2, snapshot 12.00, unit price 10.00, and line total 20.00.

### Policy

The first mismatch is `clarify`, rule `CAT-001`, reason `catalog_price_override_reason_required`. It replaces `catalog_price_mismatch` for this case. It is not `SALE-005`. Blank and overlong reasons on a pending override use the same clarify reason and do not reserve idempotency.

The override commit is `allow` under `SALE-001` and `CAT-001` with reason `catalog_price_override`. Permission remains `sale.create`. No new policy id.

### ADR

Write `docs/adr/ADR-021-catalog-price-override.md`. Do not edit ADR-015 through ADR-020. ADR-020's statement that override is future work stays as the record of that change. ADR-021 is the later decision.

## Risks / Trade-offs

- [A catalog edit between the question and the reason would charge 30 against a new baseline the merchant has not seen] → Lock the product inside the completion transaction. If that locked price still differs from both the observed price and the override, roll back with no write and ask again.
- [Adding a v1 field could be mistaken for a closed-schema break] → The field is absent unless the line is an override. Existing keys keep their meaning. Version `2` would hide the card on the current renderer.
- [Downgrade of a database that contains an override would drop the reason] → Downgrade aborts and keeps the rows.
- [`no` cancels an override question] → That phrase is cancellation only for this pending kind. It is not stored as a reason.
- [Process-local pending is lost on restart] → Same as other clarifications. The merchant repeats the sale. Nothing was written.

## Migration Plan

1. Apply `0009` in the same deploy as the workflow that writes the new columns. Old code must not run against the new check, and new code must not run before the columns exist.
2. Upgrade backfills, then adds `ck_sale_items_catalog_price`, then forces RLS back on.
3. Rollback is Alembic downgrade only when no override row exists. If one exists, fix or archive that evidence before downgrading. Do not delete it to force a downgrade.

## Open Questions

None. Decisions 1 through 17 are closed.
