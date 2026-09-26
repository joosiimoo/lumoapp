# ADR-026: Factual memory read model

- Status: Accepted
- Date: 2026-09-25

## Decision

Build A's first memory read is a closed, deterministic projection over facts Lumo has already stored. It is not a search engine and it does not write.

The query taxonomy is exactly `day_summary`, `day_events`, `sales_summary`, `cash_summary`, `close_summary`, `latest_close`, and `recent_cash_differences`. Time scopes are `today`, `yesterday`, an explicit business-local `YYYY-MM-DD`, `latest` (only `latest_close`), and `recent_days` from 1 to 30 (only `recent_cash_differences`). Today and yesterday use the business IANA timezone. The repository does not accept natural-language periods, free text, SQL, or an arbitrary date range.

Domain tables remain authoritative for operational state. `OperationalDay`, confirmed sales, the current `CashCount`, the frozen `ClosingSnapshot`, `OutcomeRun`, and open `WorkItem`s supply the numbers. `business_events` are chronology. They do not replace a snapshot or a current count. A closed day's sale and cash totals come from `ClosingSnapshot` and are not recomputed from later mutable rows. An open day is a current projection: `day_status=open` and `close_status=not_completed`.

`recent_cash_differences` returns one `ClosingSnapshot` per closed business date in the window where `cash_status` is `short` or `over`, ordered by `business_date DESC`. It does not include an open day's current count and it does not label a difference severe, suspicious, unusual, or recurring. `get_latest_completed_close` returns one tenant row ordered by `business_date DESC`, `closed_at DESC`, `id DESC`.

An empty result means no matching fact is recorded in Lumo. Allowed empty reasons are `no_operational_day`, `no_confirmed_sales`, `no_cash_count`, `no_completed_close`, and `no_matching_facts`. `no_matching_facts` means no matching factual result. A day with no business events uses it, and so does a recent-cash-difference window with no qualifying `ClosingSnapshot`. The reason does not name the storage table. The read must not say that the real-world event did not happen, and it must not infer completeness. `limitation_code` stays `only_lumo_registered_operations`. Source coverage on a resolved day is the existing recorded-operations declaration, not a score.

One tool is registered: `memory.business_facts@1`. It is read-only, tenant-scoped, and policy `MEM-001` is mandatory. `side_effect` is `read`. `requires_idempotency` is false. The tool performs no mutation. Permission `sale.create` is temporarily reused as the existing operational-access permission. That reuse does not mean the tool can create a sale. Granular read permissions are outside this slice. The tool does not take `business_id`, SQL, or free text. `memory.query_events` stays unregistered. The Flutter timeline uses `GET /api/v1/memory/events` only: default 20, maximum 50, last 7 business dates, cursor `(occurred_at, id)`. Memoria is a normal Flutter surface. There is no new Generative UI component. Cards render typed facts. Flutter does not calculate totals.

This slice adds no table, column, index, or migration. Head stays `0012_source_coverage_event_memory`. Reads do not audit, enqueue outbox, reserve idempotency, insert events, or update coverage. There are no embeddings and no vector search.

ADR-015 through ADR-025 are unchanged.

## Consequences

Lumo can show and answer from confirmed registered facts: a day, its sales, its cash, a close, the latest close, recent short or over closes, and a short Memoria timeline. It still cannot claim that every real-world operation was captured, and it still cannot search memory by meaning.
