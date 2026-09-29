## Why

PRD v0.11 RF-001, RF-002, RF-003, and RF-005 require a merchant to create a business in conversation, set currency and timezone, configure accepted payment methods, and finish with zero catalog products. Today `identity.businesses` is created only by seed, admin, and tests; `OnboardingPage` is a placeholder; and no persisted enabled-payment-method set exists. A new merchant cannot reach the existing operating experience.

## What Changes

- Add capability `business-onboarding`: a deterministic conversational workflow that creates one business, stores currency, IANA timezone, and enabled payment methods, then waits at `ready_to_complete` until the merchant explicitly confirms `start_using_lumo`. Completion does not require a catalog.
- The interpreter may parse utterances. Only a registered tool and domain validation may write. The LLM must not invent currency, timezone, payment methods, or completion.
- Persist configuration on the business row (and one actor-to-business bootstrap link). Do not store it only in chat, model memory, or UI state.
- Route an incomplete onboarding away from Business Stream. A completed onboarding enters the existing Inicio experience, including noncatalog sale.
- Backfill existing businesses (including Carrota) as onboarding-completed without changing their name, currency, timezone, locale, or sales data.
- Do not use `OutcomeRun`. Daily Close remains the Build A operational outcome.
- Expected migration `0015` is specified only. This change does not create it. Its `onboarding_status` default of `completed` is only for pre-0015 rows. New bootstrap inserts `in_progress` explicitly.
- Build A @1 currency, timezone, payment methods, owner bootstrap, post-completion edits, persistence shape, and legacy NULL payment methods are closed. None of them blocks implementation.

## Capabilities

### New Capabilities

- `business-onboarding`: Creation contract, derived onboarding state, field validation, resume, pre-completion correction, completion without catalog, and legacy-tenant bypass.

### Modified Capabilities

- `persistence`: Nullable currency/timezone for in-progress businesses, onboarding status, enabled payment methods, actor bootstrap link, revision `0015` (not created here).
- `tenant-isolation`: Trusted pre-tenant bootstrap that sets the new business id locally, then normal RLS. No global policy weaken.
- `ai-native-contracts`: Register `onboarding.apply@1` and a small onboarding choice card. No new sale or closing tools.
- `conversational-sale-runtime`: Operational sale tools reject a business whose onboarding is not completed. Completed legacy tenants stay on the current payment path.
- `mobile-shell`: Startup routes incomplete onboarding to the conversational onboarding surface and completed tenants to the existing shell.

## Impact

- Backend domain, onboarding workflow, tool registry, session payload, audit actions, and tests.
- Flutter `OnboardingPage` and startup routing. No dashboard, wizard, or settings center.
- ADR-030 Proposed.
- Seeded Carrota remains usable and is not sent through onboarding.

## Non-goals

- RF-004 confirmation policy, RF-006 assisted-operation consent, RF-007 roles, RF-009 payment-or-pending, RF-010 mixed payments.
- Catalog, inventory, tax, invoicing, fiscal data, address, hours, branding, bank account, integrations, pricing, subscription, payment processing, sales import.
- Post-completion settings UI, organization hierarchy, multiple users, generic NBA, merchant analytics, admin dashboard, Build B, policy @2.
- Archive, application code, migration files, commit, or push in this step.
