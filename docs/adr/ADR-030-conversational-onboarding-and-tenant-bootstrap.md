# ADR-030: Conversational onboarding and tenant bootstrap

- Status: Proposed
- Date: 2026-09-28

## Context

PRD v0.11 RF-001, RF-002, RF-003, and RF-005 require conversational business creation, currency, timezone, payment methods, and completion without a catalog. Business rows today are created by seed and tests. `currency` and `timezone` are NOT NULL. Payment methods exist only as the sale enum `cash`, `card`, `transfer`. RLS on `identity.businesses` requires `app.current_business_id` to equal the row id, so the first insert cannot see a tenant that does not exist yet. Dev tokens always include `business_id`. `OutcomeRun` is the Daily Close outcome (ADR-012, ADR-024). The LLM cannot mutate (ADR-006). Tenancy stays shared-schema RLS (ADR-010).

## Decision

Onboarding is a deterministic workflow, not an OutcomeRun and not a wizard.

The merchant's configuration is stored on `identity.businesses`: name, currency, timezone, `onboarding_status` (`in_progress` or `completed`), and nullable `enabled_payment_methods`. NULL means a legacy business with no explicit method configuration. A non-null array is an explicit non-empty set. An empty array is invalid.

`identity.actor_business_links` has `actor_id` as primary key and `business_id UUID NOT NULL` with no unique constraint on `business_id`. Build A still bootstraps one business per actor because of that primary key. A future multi-user business is not structurally blocked. Authorization stays on membership and tenant context. The link is only bootstrap resolution.

Build A @1 closes currency as exactly `MXN`, timezone as the nine Mexico IANA ids with merchant confirmation, payment methods as `cash`, `card`, and `transfer`, one owner plus a pre-tenant token only on onboarding routes, rejection of configuration edits after `completed`, columns on `identity.businesses` plus `identity.actor_business_links`, and NULL payment methods for legacy businesses. Adding another currency or timezone later requires a future product decision.

The server generates `business_id` as UUIDv7. The client cannot choose it. One transaction sets `app.current_business_id` to that id, then writes the business with `onboarding_status` explicitly `in_progress`, the user, one membership with the existing `owner` role, and the link. The column default `completed` applies only to rows that already existed. Before a business exists, idempotency is `actor_id + operation_type + key`. Afterward it is `business_id + operation_type + key`. Same payload replays. A different payload is `IDEMPOTENCY_CONFLICT`. Any failure rolls the whole transaction back. A concurrent loser on `actor_id` rolls back too and leaves no orphan business, user, or membership. That does not add RBAC. After commit, `TenantContext` comes from the tenant token as it does today.

A pre-tenant token without `business_id` is accepted only by onboarding routes. Sale and close routes reject it. Actor-link RLS matches `app.current_actor_id`. Other tenant policies stay as they are.

Next required field is a pure function of the row: missing name, then currency, then timezone, then payment methods, then `ready_to_complete` when those fields are stored and status is still `in_progress`. Completion is a separate explicit `start_using_lumo` action. The LLM does not infer it. Confirmation does not require a catalog, a sale, or a Daily Close. Existing businesses default to `completed` with `enabled_payment_methods` NULL and no rewrite of their current columns. NULL keeps today's `sale.commit@1` acceptance of `cash`, `card`, and `transfer`. A new completed business enforces its non-null set.

The interpreter may fill tool arguments. Only `onboarding.apply@1` writes.

## Consequences

- Migration `0015` is required at implementation time. It is not part of proposing this ADR.
- Nullable currency and timezone are allowed only while status is `in_progress`. Operational tools refuse that status.
- Post-completion editing, extra currencies, and a wider timezone list are future work. They are not open decisions for this slice.
- This ADR stays Proposed until implementation and manual acceptance are complete.
