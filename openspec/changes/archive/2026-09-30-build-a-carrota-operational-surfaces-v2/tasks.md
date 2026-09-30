## 1. Guardrails

- [x] 1.1 Confirm today GET still covers Inicio + Hoy summary facts; update `primary_action` to `prepare_daily_close` / `close_workspace` / label `Preparar el cierre del día`. Do not mint confirm tokens on GET
- [x] 1.2 Do not edit paused onboarding change, Memoria Slice 3 redesign, RF-009, inventory, analytics, reopen, mixed payments, refunds, or Build B
- [x] 1.3 Author ADR for structured cash-count UiAction + ClosingSnapshot `close_note` before implementing those contracts

## 2. Inicio light operational header (retain)

- [x] 2.1 Inicio light header: greeting, short sales sentence, VENTAS HOY + CAJA indicators when facts exist
- [x] 2.2 Inicio never renders Daily Close CTAs / tender breakdown / close detail lines; transcript + composer primary; refresh after mutations
- [x] 2.3 Design-system treatment; no charts/inventory/top products/comparisons/forecasting

## 3. Hoy day surface + prepare-close entry

- [x] 3.1 Keep title `Así va {business_name} hoy`, summary, payment split from server facts; export below operational/close content
- [x] 3.2 Replace Registrar/Revisar progression with single CTA `Preparar el cierre del día` + supporting copy `Confirma efectivo y revisa pendientes` when close-eligible; closed state has no close CTA
- [x] 3.3 Remove obsolete Hoy→Inicio composer handoff and inline A/B/C review presentation for the operator path

## 4. Close workspace

- [x] 4.1 Open dedicated bottom sheet/modal on prepare-close; render server facts (title Cierre del día, totals, tenders, expected cash, coverage/attention when available); no unsupported warnings
- [x] 4.2 Numeric counted-cash input; submit via structured cash-count action reusing `RecordCashCount`; no Inicio navigation; no phrase entry; refresh server facts after success
- [x] 4.3 Show server balanced / Faltante / Sobrante + difference; keep workspace open; allow confirm per existing short/over policy
- [x] 4.4 Optional `Agregar nota` free text before confirm; persist via confirm payload → snapshot `close_note` (migration)
- [x] 4.5 `Cerrar el día` uses silent token mint + `closing.confirm@1` (+ note); preserve fingerprint/staleness; completion pane then `Listo` → closed Hoy

## 5. Backend contracts

- [x] 5.1 Register structured `closing.submit_cash_count@1` action path with amount payload; same domain workflow as message count
- [x] 5.2 Alembic nullable `close_note` on `closing_snapshots`; confirm + audit/event/Memoria fact wiring; amend foundation deltas
- [x] 5.3 Update business-stream `primary_action` composer for prepare-close workspace invocation

## 6. Conversational fallback + navbar

- [x] 6.1 Preserve typed `cerrar el día` transcript path as secondary fallback
- [x] 6.2 Preserve Inicio/Hoy/Memoria/Negocio tabs and active-tab accent pill styling

## 7. Automated tests

- [x] 7.1 Hoy shows `Preparar el cierre del día`; opens workspace; expected cash/server facts render
- [x] 7.2 Count entered in workspace without navigating to Inicio; balanced / shortage / surplus; server difference displayed
- [x] 7.3 Optional note lifecycle; cancel leaves day open; final close succeeds; stale confirm refused; closed Hoy has no close CTA
- [x] 7.4 Regression: typed `cerrar el día`; no client money math; Inicio light header; sale corrections unaffected; onboarding untouched
- [x] 7.5 Closed-day Inicio: historical sale cards remain visible; sale mutation controls (Quitar / Lista para cobrar / payments / Anular) are not rendered; open-day sale actions unchanged

## 8. Manual acceptance (Carrota)

- [x] 8.1 Walk prepare-close workspace end-to-end (count, difference, note, confirm, Listo)
- [x] 8.2 Confirm Lovable-only unsupported features were not added. Do not archive/commit/push unless requested
- [x] 8.3 After close, Inicio shows Día cerrado / closed stream state without active-sale mutation controls on leftover transcript cards
