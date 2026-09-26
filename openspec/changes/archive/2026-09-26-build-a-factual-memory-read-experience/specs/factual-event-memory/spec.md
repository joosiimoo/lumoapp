## MODIFIED Requirements

### Requirement: Event reads stay on the repository
The operations repository MUST be able to list one tenant's events for one `operational_day_id` ordered by `occurred_at` ascending, then `id` ascending. It MUST also be able to list that tenant's recent events ordered by `occurred_at` descending, then `id` descending, bounded by a caller limit of at most 50 and by an inclusive business-date window of at most 7 dates. The system MUST NOT register `memory.query_events`. The system MUST NOT expose a free-text, semantic, or arbitrary `event_type` search route. Natural-language history MUST NOT be executed as SQL or as a generic event query. A public timeline read MAY exist only as `GET /api/v1/memory/events` in `memoria-timeline`. Tenant B MUST NOT read tenant A's events.

#### Scenario: Another tenant cannot read events
- **WHEN** tenant B lists events for an operational day that belongs to tenant A
- **THEN** tenant B MUST receive no tenant A event

#### Scenario: Pure reads create no event
- **WHEN** the actor loads Next Best Action, the day summary, close preparation, or the sales export, or a caller evaluates `daily_close_ready@1`, or a caller runs a factual memory query or `GET /api/v1/memory/events`
- **THEN** the business event count for that business MUST be unchanged

#### Scenario: Search stays unavailable
- **WHEN** a client requests a memory route with free text or an `event_type` filter
- **THEN** that search MUST NOT be served and no business event MUST be inserted
