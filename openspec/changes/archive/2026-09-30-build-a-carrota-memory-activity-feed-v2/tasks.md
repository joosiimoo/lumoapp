## 1. Guardrails

- [x] 1.1 Confirm no backend/API change is required (existing `GET /api/v1/memory/events` DTO covers type, `local_time`, facts, actions, grouping dates, cursor)
- [x] 1.2 Do not edit paused onboarding change, Build B memory features, Event Memory write contracts, or invent Lovable event types / actions
- [x] 1.3 Do not add ADR or Alembic migration for this presentation-only slice

## 2. Feed model and copy

- [x] 2.1 Refactor `memoria_timeline.dart` from card view to compact activity-item view (timestamp, type label, primary, optional secondary, optional void action)
- [x] 2.2 Implement deterministic rendering matrix for `sale_confirmed`, `sale_voided`, `cash_count_recorded`, `daily_close_completed` using server facts only
- [x] 2.3 Keep date grouping (`Hoy` / `Ayer` / calendar date) from server `business_date` / `business_today` / `business_yesterday`; omit speculative relative labels
- [x] 2.4 Update empty state to `Aún no hay actividad registrada.`; remove footer `Memoria muestra operaciones confirmadas registradas en Lumo.`
- [x] 2.5 Preserve `memoriaVoidRequest` / Anular eligibility as backend-action-only (no client inference)

## 3. Memoria UI

- [x] 3.1 Rebuild `MemoriaPage` list as compact chronological activity feed on warm canvas with restrained chips and soft dividers (no oversized card stack, no vertical rail requirement)
- [x] 3.2 Keep header `MEMORIA` + `Lo que Lumo recuerda`; keep “Ver anteriores” cursor pagination; do not add search, composer, question chips, or unsupported actions
- [x] 3.3 Wire existing void confirmation path from compact Venta items; refresh feed after successful void

## 4. Tests — feed rendering

- [x] 4.1 Newest-first ordering preserved from API payload order
- [x] 4.2 Date grouping: Hoy / Ayer / calendar date from server business dates (including UTC-boundary case)
- [x] 4.3 `sale_confirmed` compact rendering (type Venta, amount, payment method, time)
- [x] 4.4 `sale_voided` rendering including `Motivo:` when reason present; no Anular
- [x] 4.5 `cash_count_recorded` rendering (counted primary, expected/diff secondary, cash status)
- [x] 4.6 `daily_close_completed` rendering (sales total primary; status/diff secondary)
- [x] 4.7 `close_note` shown when present; omitted when absent
- [x] 4.8 No duplicated unnecessary facts across primary/secondary

## 5. Tests — actions and state

- [x] 5.1 Anular shown only when backend supplies `sale.void.request@1`
- [x] 5.2 Anular absent when backend omits action (voided, closed day, ineligible)
- [x] 5.3 Action still works after app restart/reload (fresh token + server `conversation_id`)
- [x] 5.4 Empty state copy and absence of fake examples
- [x] 5.5 Closed-day / history behavior: items remain; Anular not inferred

## 6. Tests — regression

- [x] 6.1 Existing sale void workflow from Memoria unaffected (request → confirm → refresh)
- [x] 6.2 Factual memory remains immutable / history-preserving (confirmed + voided both visible)
- [x] 6.3 No client-side eligibility inference; no unsupported Lovable features in UI
- [x] 6.4 Pagination/window behavior unchanged (limit/before / Ver anteriores)

## 7. Validation

- [x] 7.1 Run targeted Flutter memoria tests and any affected void/timeline backend tests if touched
- [x] 7.2 `openspec validate build-a-carrota-memory-activity-feed-v2 --strict`
- [x] 7.3 `openspec validate --all --strict`

## 8. Manual acceptance

- [x] 8.1 Manual visual acceptance of Memoria activity-feed timeline (compact Activity surface, nodes/connector, sale copy, Conteo balanced chip suppression)
- [x] 8.2 Confirm Anular, Ver anteriores, empty state, and date grouping behave as accepted on device/pilot review
