## 1. Domain catalog

- [x] 1.1 Add `backend/app/domain/catalog` entities and enums: `Product`, `sale_unit` (`unit`|`package`|`kilogram`), `pricing_type`, `status`, name normalization (NFKD, strip marks, lowercase, collapse space). No SQLAlchemy imports.
- [x] 1.2 Implement unique/ambiguous/none resolution against name and optional aliases; exclude inactive products. Unit-test accent match for `ZANAHORÍA` → Zanahoria and inactive exclusion.

## 2. Domain sales

- [x] 2.1 Add `backend/app/domain/sales` entities `SaleSession` (`open` only) and `SaleItem` with Decimal quantity and money fields.
- [x] 2.2 Implement gram→kilogram normalization (`quantity / 1000`) and line total `quantity_normalized * current_price` via the existing money helper (MXN 2 decimals, reject float). Unit-test `900 gram` + `25.00` → `0.900` kg and `22.50` MXN.
- [x] 2.3 Reject non-positive quantity, missing unit, and incompatible units (`UNIT_NOT_SUPPORTED`). Do not infer unit from `sale_unit`.

## 3. Persistence

- [x] 3.1 Alembic migration: PostgreSQL schemas `catalog` and `sales`; tables `products`, `product_aliases`, `sale_sessions`, `sale_items`; UUIDv7, `timestamptz`, `numeric`; unique open session per interaction context; RLS for `lumo_app`. Do not create `operations`, `workflow`, or `memory`.
- [x] 3.2 Infrastructure models and tenant-required repositories for catalog and sales. Reuse audit, idempotency, and outbox ports.
- [x] 3.3 Update foundation tests that asserted product schemas are absent.

## 4. Seed

- [x] 4.1 Local/test seed: business Carrota, owner membership, active product Zanahoria, `sale_unit=kilogram`, `pricing_type=per_kilogram`, `current_price=25.00` MXN, no alias required.

## 5. Policies and AgentDecision

- [x] 5.1 Register policies `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, `SALE-001` alongside `SEC-001`–`SEC-003`. Unregistered tools remain `deny`.
- [x] 5.2 Extend `AgentDecision` with optional `product_query`, `quantity`, `unit`. Invalid payloads still discard with no mutation.
- [x] 5.3 Add error types/envelope codes `AMBIGUOUS_PRODUCT`, `PRODUCT_NOT_FOUND`, `UNIT_NOT_SUPPORTED`.

## 6. Tools and workflow

- [x] 6.1 Register `catalog.resolve_product@1` (read, `sale.create`) with the spec input/output schema.
- [x] 6.2 Register `sale.start@1` (write, idempotent as its own operation): create or reuse one `open` session per interaction context. On the message path it MUST NOT commit before add-item.
- [x] 6.3 Register `sale.add_item@1` (write, idempotent as its own operation): re-read product, revalidate args, normalize, calculate, persist item. On the message path those writes MUST share the workflow transaction.
- [x] 6.4 Implement the conversational workflow: interpret → resolve (read, before any write tx) → one application-owned write transaction (start/reuse + add-item + audit/outbox/message idempotency) → compose UI after commit. If wrapping both tool facades in one Unit of Work is impractical, use a single command that performs start-or-reuse and add-item in that transaction and still audit both tool ids. Never commit an empty new session if add-item fails. Ambiguous/none/missing unit MUST NOT open the write transaction. Orchestrator MUST NOT open ORM sessions.

## 7. Agent API and interpreter

- [x] 7.1 Replace the foundation always-unsupported fake interpret with a scripted interpreter that maps `900gr` / `900 gr` / `900 g` / `900 gramos` + zanahoria to `add_sale_item` and clarifies otherwise. No vendor SDK.
- [x] 7.2 Add `POST /api/v1/lumo/messages` (`Idempotency-Key`, auth, correlation). Handler delegates to the orchestrator; no pricing math in the route.
- [x] 7.3 Wire tools, policies, UI registry, and workflow in `bootstrap`. Message `Idempotency-Key` MUST cover the whole add-item workflow, not two nested committed tool calls.

## 8. Generative UI backend

- [x] 8.1 Register `sale_item_added@1` and compose it only after committed add-item using server values (`0.900`, `25.00`, `22.50`, fallback_text). `actions=[]`. Refuse `sale_confirmed_card` and other unregistered components.

## 9. Flutter renderer and Inicio

- [x] 9.1 Map `sale_item_added@1` in `GenerativeUIRenderer` to Lumo mark + `LumoCard` product row (name, qty × unit · unit price, subtotal). Format server strings only; unknown version shows `fallback_text`.
- [x] 9.2 Enable Inicio stream + sticky composer: append user bubble, `POST /api/v1/lumo/messages` via typed client, append Lumo text/card. Preserve four-tab shell, 420px canvas, retry-same-idempotency-key. Do not add payment chips or Registrar.

## 10. Golden-path verification

- [x] 10.1 Integration test: seeded Carrota posts `"900gr zanahoria"` → unique resolve, one open session, one item `0.900` kg / `22.50` MXN, audit present, `sale_item_added@1` in `ui`.
- [x] 10.2 Tests: idempotent replay of the message; new-session + failed add-item leaves zero sessions and zero items; reused-session + failed add-item leaves the session unchanged; model-hinted total ignored; missing unit / unknown product / ambiguous name do not persist and do not create a session; cross-tenant resolve/add denied; `sale.commit@1` unregistered.
- [x] 10.3 Flutter test: renderer shows Zanahoria / 0.900 kg / $22.50 from payload fields without multiplying; Inicio send uses the typed client.
- [x] 10.4 Write ADR-013 (conversational sale tools as first registered catalog). Do not implement payment, commit, operational day, export, or catalog CRUD UI.

## 11. Acceptance-test fixes

- [x] 11.1 Publish Compose Postgres to host `5432:5432`. Update README, pytest defaults, and local scripts from `5433`. If host 5432 is occupied, stop and report; do not kill the other process.
- [x] 11.2 Confirm local seed: `APP_ENV=local` API boot runs `ensure_carrota_seed` idempotently; tests seed explicitly; staging/production never seed. Document FORCE RLS empty `SELECT` without `app.current_business_id`. Verify Carrota + Zanahoria rows after boot.
- [x] 11.3 Composer Enter and send button share one submit path; whitespace does not send; Flutter keyboard-submit test.
- [x] 11.4 Pending missing-unit clarification scoped to tenant + actor + conversation: `"900 zanahoria"` then `"gr"` (also `g`/`gramos`/`kg`/`kilogramo`/`kilogramos`) completes add-item. No session/item until the second turn. Integration test required.
- [x] 11.5 Inicio eyebrow `LUMO · {business name}` from session (Carrota when seeded), uppercase. `Buenos días` uses display greeting + Lumo gradient.
- [x] 11.6 Sale-item row display `0.900 kg · $25.00/kg` from server strings; canonical `unit_normalized=kilogram` unchanged. Labels: kg, g, unidad, paquete.
- [x] 11.7 `GET /api/v1/dev/carrota-token` and `X-Debug-Fail-After-Write` are inert in staging/production. Regression tests.

## 12. Conversation scope and integrity cleanup

- [x] 12.1 Inicio generates a stable client UUID `conversation_id` and sends it on every `POST /api/v1/lumo/messages`. Persist it on `SaleSession`. Reuse open sessions by `(business_id, actor_id, conversation_id)` when present. Different ids MUST create different sessions. Do not add a Conversation aggregate.
- [x] 12.2 Tests: same `conversation_id` reuses one session; different ids create two sessions; two-turn `"900 zanahoria"` then `"gr"` keeps the same id and persists it; Flutter posts include `conversation_id`.
- [x] 12.3 Move sale test reset to one transaction that deletes `sale_items`, `sale_sessions`, related `sale.start@1`/`sale.add_item@1` audit, `sale.item.added` outbox, and `lumo.message.add_sale_item` idempotency. Do not piecemeal-delete sales/idempotency only. Regression: cleanup/rollback cannot leave audit/outbox referencing missing sale rows.
