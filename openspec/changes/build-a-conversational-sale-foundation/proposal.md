## Why

The archived foundation gives Lumo a modular monolith, tenant isolation, and empty AI-native ports, but a merchant still cannot record a sale. Architecture §23 step 1 is complete; the next proof is the first AI-native product slice: interpret `"900gr zanahoria"`, resolve the catalog, calculate in the backend, persist a sale item, and render a versioned Generative UI contract in Flutter. This is PRD §7.3 / §11 scenario 1 and SRS CA-001, narrowed to one conversational add-item path rather than the full daily operator.

## What Changes

- Add PostgreSQL schemas `catalog` and `sales` with `Product`, `SaleSession`, and `SaleItem`.
- Seed local/test data for business Carrota and product Zanahoria sold by kilogram.
- Register tools `catalog.resolve_product@1`, `sale.start@1`, and `sale.add_item@1`. The LLM interprets; registered tools mutate.
- Register the minimum policies for those tools (`CAT-001`, `CAT-002`, `SALE-001`, `INT-001`, `INT-003`, `INTP-001`, `INTP-002`, plus existing `SEC-001`–`SEC-003`).
- Extend `AgentDecision` only as needed for product, quantity, and unit entities.
- Expose `POST /api/v1/lumo/messages` so Inicio can send user text through the single orchestrator.
- Register Generative UI contract `sale_item_added@1`. Flutter maps it onto the approved sale-item / soft-card language.
- Enable the Inicio composer and conversation stream without changing navigation or visual identity.

**BREAKING** relative to the active baseline: `ToolRegistry`, `PolicyEngine`, and `GenerativeUIRegistry` are no longer empty; persistence now includes product schemas `catalog` and `sales`.

## Non-goals

- Payment selection, sale confirmation/`sale.commit`, operational day, daily close, cash count, historical queries, CSV/XLSX export.
- Price override, discounts, unknown/non-catalog products, multi-product interpretation.
- Full catalog CRUD, inventory, purchasing, recommendations, advanced memory, voice, camera.
- Multiple independent agents or a POS form flow.
- Real vendor LLM SDK; a scripted/fake interpreter MUST cover the golden utterance for local and tests.
- Outcome definitions (`daily_sales_operations_ready@1`, `daily_close_ready@1`).
- Redesign of Lumo screens, tokens, or the user-bubble / Lumo-mark visual pattern.

## Capabilities

### New Capabilities

- `catalog-foundation`: Product persistence, name normalization, sale units, pricing types, current price, and tenant-scoped resolution against the active catalog.
- `sales-session-foundation`: One active `SaleSession` per interaction context, `SaleItem` persistence, gram→kilogram normalization, and deterministic Decimal line totals.
- `conversational-sale-runtime`: Agent message API, tool registrations, policy gates, application workflow that resolves then commits start/reuse + add-item in one write transaction, and server-side revalidation.
- `sale-item-added-ui`: Versioned `sale_item_added@1` contract, composer emission, and Flutter rendering on Inicio.

### Modified Capabilities

- `persistence`: Create schemas `catalog` and `sales`. Schemas `operations`, `workflow`, and `memory` remain absent.
- `ai-native-contracts`: Register the three product tools, the listed policies, and `sale_item_added@1`. Empty-registry foundation scenarios no longer hold.
- `mobile-shell`: Inicio is no longer a non-sending placeholder; the composer posts user text and the stream renders the structured Lumo response.

## Impact

- Backend: `domain/catalog`, `domain/sales`, application commands/workflows, Alembic migrations, seed, `POST /api/v1/lumo/messages`, bootstrap wiring of tools/policies/UI contracts.
- Mobile: Inicio stream + sticky composer; `GenerativeUIRenderer` learns `sale_item_added@1`; typed client calls the agent endpoint. No domain math on the client.
- Integrity: the message path uses one application-owned write transaction for session create/reuse plus item; audit, idempotency, RLS, and Decimal money helpers are reused. The orchestrator does not open the transaction.
- Tests: golden path `"900gr zanahoria"` plus ambiguity, missing unit, idempotent replay, tenant isolation, and unknown UI fallback.
