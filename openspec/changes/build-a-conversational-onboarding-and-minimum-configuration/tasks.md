## 1. Domain contracts

- [x] 1.1 Add onboarding status, next-field derivation, name normalization, currency set, timezone allowlist, and payment-method set validation in the domain without framework imports.
- [x] 1.2 Reject empty names, unsupported currencies, non-allowlisted timezones, unknown payment methods, and completion with an empty method set.

## 2. Persistence and bootstrap

- [x] 2.1 Add Alembic revision `0015` after `0014` with onboarding columns, nullable currency and timezone, actor link, checks, and actor-scoped RLS. Do not rewrite existing Carrota values.
- [x] 2.2 Implement the bootstrap transaction that sets the new business id locally, inserts business, user, owner membership, and actor link once, and sets `onboarding_status` to `in_progress` in that insert.

## 3. Onboarding workflow

- [x] 3.1 Implement `onboarding.apply` so it writes only validated fields, resumes at the first gap, and sets `next_required_field` to `ready_to_complete` while status stays `in_progress` when name, currency, timezone, and a non-null non-empty method set exist.
- [x] 3.2 Complete only on the explicit `start_using_lumo` action. Allow corrections before that action, including from `ready_to_complete`, and reject changes after `completed`. Do not create catalog rows.

## 4. Interpreter and tool contracts

- [x] 4.1 Register `onboarding.apply@1`, `onboarding_choice` version `1`, and `onboarding_confirmation` version `1` with `start_using_lumo`. Keep the LLM off the database and off the confirmation decision.
- [x] 4.2 Map interpreter slots to the tool input and ignore unregistered writes.

## 5. Flutter onboarding UI

- [x] 5.1 Replace the `OnboardingPage` placeholder with the conversational surface, composer, choice cards, and the compact confirmation summary card.
- [x] 5.2 Keep the tab bar hidden and do not add a wizard or dashboard.

## 6. App startup and routing

- [x] 6.1 Extend session and pre-tenant status so the client can tell no business, in progress, and completed apart.
- [x] 6.2 Route incomplete onboarding to `OnboardingPage` and completed tenants, including Carrota, to the existing Inicio shell.

## 7. Tenancy and RLS

- [x] 7.1 Accept a pre-tenant dev token only on onboarding routes. Reject it on sale and close routes.
- [x] 7.2 Prove tenant B cannot read tenant A onboarding fields, that business RLS policies are unchanged, and that `actor_business_links.business_id` has no unique constraint.

## 8. Audit and idempotency

- [x] 8.1 Append the five onboarding audit actions in the same transaction as the write.
- [x] 8.2 Before a business exists, key idempotency by `actor_id + operation_type + idempotency_key`. Afterward, key it by `business_id + operation_type + idempotency_key`. Same payload replays. A different payload is `IDEMPOTENCY_CONFLICT`.

## 9. Automated tests

- [x] 9.1 Cover name, currency, timezone, and payment-method validation, including empty name, invalid currency, ambiguous timezone, and empty method set.
- [x] 9.2 Cover `ready_to_complete` while all required fields stay `in_progress`, explicit `start_using_lumo` completion, resume onto the confirmation summary, pre-confirmation correction, post-completion rejection, idempotent create and config write, and no catalog required.
- [x] 9.3 Cover legacy Carrota as `completed` with NULL payment methods and unchanged sale behavior, rejection of an empty method array as a wildcard, and the new-completion rule that methods are non-null and non-empty.
- [x] 9.4 Cover a new bootstrap row with `onboarding_status` `in_progress`, a pre-0015 row that stays `completed` after migration, server-generated UUIDv7 `business_id`, client rejection of a supplied business id, unique `actor_id`, and non-unique `business_id` on the link table.
- [x] 9.5 Cover RLS bootstrap, cross-tenant denial, and sale rejection while `in_progress`, including `ready_to_complete`.
- [x] 9.6 Assert this slice adds no confirmation policy and no payment-pending state.
- [x] 9.7 Cover pre-tenant same key and same payload returning one business, pre-tenant same key and different payload returning `IDEMPOTENCY_CONFLICT`, no duplicate user, membership, or link on replay, full bootstrap rollback, and concurrent different keys for one actor leaving one association and no orphan rows.

## 10. Manual acceptance

- [ ] 10.1 New merchant: name, currency, timezone, payment methods, confirmation summary, explicit `start_using_lumo`, Inicio, noncatalog sale, zero catalog rows.
- [ ] 10.2 Resume after name and currency at timezone, and resume a fully filled unconfirmed onboarding at the confirmation summary.
- [ ] 10.3 Before completion, add transfer to an existing cash selection without a duplicate business.
- [ ] 10.4 Carrota opens Inicio. Name, currency, and timezone stay `Carrota`, `MXN`, and `America/Mexico_City`. `enabled_payment_methods` stays NULL.

## 11. ADR acceptance

- [ ] 11.1 After implementation and manual acceptance, move ADR-030 from Proposed to Accepted only with an explicit decision. Do not accept it in the OpenSpec-only step.

## 12. Archive readiness

- [ ] 12.1 Run `openspec validate --all --strict` and confirm non-goals are untouched before any archive. Do not archive in the OpenSpec-only step.
