# Acceptance notes

Manual acceptance PASS. Tasks 17/17. The six design.md scenarios were accepted before the first final backend-suite run. They were not repeated after restoration.

1. `¿Cuánto vendí hoy?` routes to `memory.business_facts@1` / `sales_summary`, uses conservative registered-sales wording, and writes nothing. `¿Cuánto vendimos hoy?` stays on `operational_day.summary@1`.
2. `¿Hubo diferencia de caja?` is `cash_summary`: expected 22.50, counted 20.00, difference -2.50, short / Faltante, and writes nothing.
3. `¿Cómo cerré hoy?` is `close_summary` from the frozen ClosingSnapshot, with no recomputation and no writes.
4. `¿Cuál fue mi último cierre?` is `latest_close` from the latest frozen snapshot and writes nothing.
5. Memoria is a deterministic timeline of the close, the cash count, and the sale, grouped by `business_date`, using server `local_time`, with no Flutter calculations and no writes.
6. `¿Qué pasó el 24 de septiembre?` is `no_operational_day`, answers "No encuentro … registrado en Lumo", creates no day, and does not claim that nothing happened.

Memoria UI correction: the close card uses `facts.gross_sales_total` ("Ventas registradas 22.50"), not `sale_count`. Cash status uses `LumoStatusChip` (Cuadrado / Faltante / Sobrante).

Old API image routing incident: the workspace already routed `¿Cuánto vendí hoy?` to `sales_summary`. The running image was stale and returned the catalog fallback. The image was rebuilt, and an endpoint regression test now covers that phrase.

Test isolation, recorded here because it is a test-infrastructure issue and not a product-behavior defect:

- the first final backend-suite run deleted the pilot state
- sale and close tests reused Carrota's pilot business id, and committed cleanup removed Carrota's operational data
- migration downgrade tests globally purged operational tables on the application database
- ordinary tests now use test-owned tenant ids
- cleanup requires a process-registered test tenant and rejects a pilot id before DELETE
- schema migration tests run on `lumo_migration_test`
- the normal application database remains `lumo`
- the full backend suite passed 306 tests
- a separate sentinel test tenant survived unchanged, including its OperationalDay, business events, source coverage, CashCount, ClosingSnapshot, OutcomeRun, and WorkItems

Carrota was restored afterward through the running API only: `900gr zanahoria`, `totalizar`, `efectivo`, `conté 20.00`, `preparar el cierre`, `cerrar el día`, and `confirmar cierre`. No SQL domain insert and no pytest seed. Business date `2026-09-26`. One confirmed cash sale of 22.50, cash count 20.00, difference -2.50, status short, day closed.

Final smokes, both read-only:

- `¿Cuál fue mi último cierre?` begins `El último cierre registrado en Lumo` and includes `22.50 MXN`, `Faltante`, and `-2.50`
- `GET /api/v1/memory/events` returns `daily_close_completed`, `cash_count_recorded`, and `sale_confirmed` in that order, with `next_cursor` null
- repeating both left business events, coverage, audit, outbox, idempotency, the OutcomeRun, WorkItems, and the ClosingSnapshot unchanged

Technical acceptance: no migration. Head remains `0012_source_coverage_event_memory`. ADR-026 is Accepted. OpenSpec strict validation passed before archive. Flutter tests passed and `flutter analyze` was clean.
