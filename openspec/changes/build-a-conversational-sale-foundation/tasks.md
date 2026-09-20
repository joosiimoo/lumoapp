## 1. Domain catalog

- [ ] 1.1 Add `backend/app/domain/catalog` entities and enums: `Product`, `sale_unit` (`unit`|`package`|`kilogram`), `pricing_type`, `status`, name normalization (NFKD, strip marks, lowercase, collapse space). No SQLAlchemy imports.
- [ ] 1.2 Implement unique/ambiguous/none resolution against name and optional aliases; exclude inactive products. Unit-test accent match for `ZANAHORÍA` → Zanahoria and inactive exclusion.

## 2. Domain sales

- [ ] 2.1 Add `backend/app/domain/sales` entities `SaleSession` (`open` only) and `SaleItem` with Decimal quantity and money fields.
- [ ] 2.2 Implement gram→kilogram normalization (`quantity / 1000`) and line total `quantity_normalized * current_price` via the existing money helper (MXN 2 decimals, reject float). Unit-test `900 gram` + `25.00` → `0.900` kg and `22.50` MXN.
- [ ] 2.3 Reject non-positive quantity, missing unit, and incompatible units (`UNIT_NOT_SUPPORTED`). Do not infer unit from `sale_unit`.

## 3. Persistence

- [ ] 3.1 Alembic migration: PostgreSQL schemas `catalog` and `sales`; tables `products`, `product_aliases`, `sale_sessions`, `sale_items`; UUIDv7, `timestamptz`, `numeric`; unique open session per interaction context; RLS for `lumo_app`. Do not create `operations`, `workflow`, or `memory`.
- [ ] 3.2 Infrastructure models and tenant-required repositories for catalog and sales. Reuse audit, idempotency, and outbox ports.
- [ ] 3.3 Update foundation tests that asserted product schemas are absent.

## 4. Seed

- [ ] 4.1 Local/test seed: business Carrota, owner membership, active product Zanahoria, `sale_unit=kilogram`, `pricing_type=per_kilogram`, `current_price=25.00` MXN, no alias required.

## 5. Policies and AgentDecision

- [ ] 5.1 Register policies `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, `CAT-001`, `CAT-002`, `SALE-001` alongside `SEC-001`–`SEC-003`. Unregistered tools remain `deny`.
- [ ] 5.2 Extend `AgentDecision` with optional `product_query`, `quantity`, `unit`. Invalid payloads still discard with no mutation.
- [ ] 5.3 Add error types/envelope codes `AMBIGUOUS_PRODUCT`, `PRODUCT_NOT_FOUND`, `UNIT_NOT_SUPPORTED`.

## 6. Tools and workflow

- [ ] 6.1 Register `catalog.resolve_product@1` (read, `sale.create`) with the spec input/output schema.
- [ ] 6.2 Register `sale.start@1` (write, idempotent as its own operation): create or reuse one `open` session per interaction context. On the message path it MUST NOT commit before add-item.
- [ ] 6.3 Register `sale.add_item@1` (write, idempotent as its own operation): re-read product, revalidate args, normalize, calculate, persist item. On the message path those writes MUST share the workflow transaction.
- [ ] 6.4 Implement the conversational workflow: interpret → resolve (read, before any write tx) → one application-owned write transaction (start/reuse + add-item + audit/outbox/message idempotency) → compose UI after commit. If wrapping both tool facades in one Unit of Work is impractical, use a single command that performs start-or-reuse and add-item in that transaction and still audit both tool ids. Never commit an empty new session if add-item fails. Ambiguous/none/missing unit MUST NOT open the write transaction. Orchestrator MUST NOT open ORM sessions.

## 7. Agent API and interpreter

- [ ] 7.1 Replace the foundation always-unsupported fake interpret with a scripted interpreter that maps `900gr` / `900 gr` / `900 g` / `900 gramos` + zanahoria to `add_sale_item` and clarifies otherwise. No vendor SDK.
- [ ] 7.2 Add `POST /api/v1/lumo/messages` (`Idempotency-Key`, auth, correlation). Handler delegates to the orchestrator; no pricing math in the route.
- [ ] 7.3 Wire tools, policies, UI registry, and workflow in `bootstrap`. Message `Idempotency-Key` MUST cover the whole add-item workflow, not two nested committed tool calls.

## 8. Generative UI backend

- [ ] 8.1 Register `sale_item_added@1` and compose it only after committed add-item using server values (`0.900`, `25.00`, `22.50`, fallback_text). `actions=[]`. Refuse `sale_confirmed_card` and other unregistered components.

## 9. Flutter renderer and Inicio

- [ ] 9.1 Map `sale_item_added@1` in `GenerativeUIRenderer` to Lumo mark + `LumoCard` product row (name, qty × unit · unit price, subtotal). Format server strings only; unknown version shows `fallback_text`.
- [ ] 9.2 Enable Inicio stream + sticky composer: append user bubble, `POST /api/v1/lumo/messages` via typed client, append Lumo text/card. Preserve four-tab shell, 420px canvas, retry-same-idempotency-key. Do not add payment chips or Registrar.

## 10. Golden-path verification

- [ ] 10.1 Integration test: seeded Carrota posts `"900gr zanahoria"` → unique resolve, one open session, one item `0.900` kg / `22.50` MXN, audit present, `sale_item_added@1` in `ui`.
- [ ] 10.2 Tests: idempotent replay of the message; new-session + failed add-item leaves zero sessions and zero items; reused-session + failed add-item leaves the session unchanged; model-hinted total ignored; missing unit / unknown product / ambiguous name do not persist and do not create a session; cross-tenant resolve/add denied; `sale.commit@1` unregistered.
- [ ] 10.3 Flutter test: renderer shows Zanahoria / 0.900 kg / $22.50 from payload fields without multiplying; Inicio send uses the typed client.
- [ ] 10.4 Write ADR-013 (conversational sale tools as first registered catalog). Do not implement payment, commit, operational day, export, or catalog CRUD UI.
