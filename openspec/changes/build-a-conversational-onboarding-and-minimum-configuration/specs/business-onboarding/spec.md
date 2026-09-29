## ADDED Requirements

### Requirement: Deterministic onboarding state
The system MUST persist onboarding on the business row as `in_progress` or `completed`. It MUST derive the next required field in this order: `business_name` when the actor has no business, then `currency`, then `timezone`, then `payment_methods`, then `ready_to_complete` when name, currency, timezone, and a non-null non-empty payment-method set are stored and the merchant has not confirmed. `ready_to_complete` MUST NOT be a stored status. The system MUST keep `onboarding_status` as `in_progress` until an explicit `start_using_lumo` confirmation. It MUST NOT set `completed` only because every field is present. It MUST NOT use an LLM to choose the state, the next field, or confirmation. It MUST NOT derive progress from chat history or store the configuration only in a transcript, model memory, or client state.

#### Scenario: Next field is timezone
- **WHEN** the business has a name and a currency and a null timezone
- **THEN** the next required field MUST be `timezone` and the status MUST be `in_progress`

#### Scenario: Fields without confirmation stay in progress
- **WHEN** a valid name, a supported currency, a supported IANA timezone, and a non-null non-empty payment-method set are stored and the merchant has not confirmed
- **THEN** `onboarding_status` MUST remain `in_progress` and the next required field MUST be `ready_to_complete`

#### Scenario: Explicit confirmation completes
- **WHEN** the next required field is `ready_to_complete` and the merchant submits the explicit `start_using_lumo` action
- **THEN** the status MUST become `completed` without a catalog product, a sale, or a Daily Close, and the LLM MUST NOT be the source of that confirmation

### Requirement: Business name
A new business name MUST be non-empty after trim, MUST be at most 200 characters, and MUST preserve the merchant's casing aside from trimmed and collapsed whitespace. The same name MUST be allowed on different businesses. An empty name MUST be rejected and MUST NOT create a row.

#### Scenario: Empty name
- **WHEN** the merchant submits a blank name
- **THEN** the system MUST reject the write and MUST NOT insert a business

### Requirement: Currency configuration
The system MUST persist an uppercase currency code. The supported set for this slice MUST be exactly `MXN`. The system MUST reject any other code, including `USD`, and MUST leave the next required field at `currency`. It MUST NOT persist a suggested currency without a validated tool input. It MUST NOT store exchange rates. Adding another currency requires a future product decision and is out of this slice.

#### Scenario: MXN accepted
- **WHEN** the merchant confirms `MXN`
- **THEN** `businesses.currency` MUST be `MXN`

#### Scenario: Invalid currency
- **WHEN** the merchant submits a code outside the supported set
- **THEN** the system MUST reject the write and MUST leave currency unchanged

### Requirement: Timezone configuration
The system MUST persist a timezone only when it is one of `America/Mexico_City`, `America/Cancun`, `America/Tijuana`, `America/Hermosillo`, `America/Mazatlan`, `America/Chihuahua`, `America/Merida`, `America/Monterrey`, or `America/Bahia_Banderas`. It MUST reject labels that are not those identifiers, including `Mexico` and `CST`. It MUST NOT persist a device-inferred zone that the merchant did not confirm.

#### Scenario: Mexico City
- **WHEN** the merchant confirms `America/Mexico_City`
- **THEN** `businesses.timezone` MUST be `America/Mexico_City`

#### Scenario: Ambiguous label
- **WHEN** the merchant submits `CST`
- **THEN** the system MUST reject the write and MUST leave timezone unchanged

### Requirement: Enabled payment methods
The enabled set MUST contain only `cash`, `card`, and `transfer`. For a business created by this onboarding, `ready_to_complete` and `completed` MUST require `enabled_payment_methods` non-null and cardinality at least 1. An empty array MUST be rejected. A correction before `start_using_lumo` MUST replace the stored set with the new validated set and MUST NOT insert a duplicate business or membership. Methods outside that enum MUST be rejected.

#### Scenario: Empty set is not enough
- **WHEN** name, currency, and timezone are stored and the enabled set is null or empty
- **THEN** the status MUST remain `in_progress` and the next field MUST be `payment_methods`

#### Scenario: Add transfer before completion
- **WHEN** the enabled set is `cash` and a later apply adds `transfer` before completion
- **THEN** the stored set MUST be `cash` and `transfer` and there MUST still be one business row

### Requirement: Resume
Partial configuration MUST remain stored. A later session MUST continue at the first missing required field.

#### Scenario: Return after currency
- **WHEN** name and currency are stored and the merchant opens the app again before a timezone is stored
- **THEN** the next required field MUST be `timezone` and the stored name and currency MUST be unchanged

#### Scenario: Resume at confirmation
- **WHEN** all required fields are stored, status is `in_progress`, and the merchant opens the app again
- **THEN** the next required field MUST be `ready_to_complete` and the summary MUST be shown again without reading chat history

### Requirement: Correction before completion
Before `start_using_lumo`, including while the next field is `ready_to_complete`, a valid replacement of name, currency, timezone, or the payment-method set MUST update that field. After `completed`, this slice MUST reject further configuration changes.

#### Scenario: Replace currency before completion
- **WHEN** currency is `MXN`, status is `in_progress`, and the supported set is still only `MXN`
- **THEN** a second apply of `MXN` MUST leave a single currency value `MXN`

#### Scenario: Edit after completion
- **WHEN** status is `completed` and the merchant submits a new timezone
- **THEN** the system MUST reject the change and MUST leave the stored timezone unchanged

### Requirement: No catalog required
Completing onboarding MUST NOT require a product, category, inventory quantity, SKU, or barcode. After completion the existing noncatalog sale flow MUST remain usable.

#### Scenario: Zero products
- **WHEN** onboarding completes and the business has no catalog rows
- **THEN** the status MUST be `completed` and a noncatalog sale MUST still be allowed by the sale runtime

### Requirement: Existing operational businesses bypass onboarding
A business that already existed before this slice MUST be `completed` without changes to its name, currency, timezone, locale, memberships, catalog, or sales. Its `enabled_payment_methods` MUST remain NULL. NULL MUST NOT force onboarding.

#### Scenario: Carrota starts in Inicio
- **WHEN** the seeded Carrota tenant opens the app after migration
- **THEN** onboarding status MUST be `completed`, `enabled_payment_methods` MUST be NULL, name MUST remain `Carrota`, currency MUST remain `MXN`, timezone MUST remain `America/Mexico_City`, and the client MUST show the existing Inicio experience

### Requirement: Idempotent creation
The server MUST generate `business_id` as UUIDv7. The client request MUST NOT contain or select it. The bootstrap insert MUST set `onboarding_status` to `in_progress` explicitly and MUST NOT rely on the column default. `enabled_payment_methods` MUST be NULL until the merchant configures a non-empty set. Repeating business creation for the same actor MUST return the existing business and MUST NOT insert a second business, user, membership, or actor link. The first bootstrap transaction MUST insert business, user, owner membership, and actor link together and MUST roll back all of those writes on any failure. Two concurrent first bootstraps for the same actor MUST leave at most one actor link and MUST NOT leave an orphan business, user, or membership from the loser. `actor_id` is the primary key. `business_id` on `actor_business_links` MUST NOT be unique.

#### Scenario: New business starts in progress
- **WHEN** bootstrap creates a business
- **THEN** `onboarding_status` MUST be `in_progress` and `enabled_payment_methods` MUST be NULL

### Requirement: Onboarding idempotency before and after a business exists
`onboarding.apply@1` MUST require an idempotency key and MUST reuse the existing idempotency records. Before a business exists, the identity MUST be the authenticated `actor_id`, the operation type, and the idempotency key. After a business exists, the identity MUST be `business_id`, the operation type, and the idempotency key. The same identity and the same payload MUST replay the original result. The same identity and a different payload MUST return `IDEMPOTENCY_CONFLICT`. The `actor_id` primary key MUST NOT replace those replay rules.

#### Scenario: Pre-tenant replay
- **WHEN** the same actor repeats `onboarding.apply@1` with the same key and the same payload before or during first creation
- **THEN** the result MUST be the original result and there MUST still be one business, one user, one membership, and one actor link

#### Scenario: Pre-tenant conflict
- **WHEN** the same actor repeats `onboarding.apply@1` with the same key and a different payload
- **THEN** the response MUST be `IDEMPOTENCY_CONFLICT` and MUST NOT create a second business

#### Scenario: Duplicate create
- **WHEN** the actor submits the business name again after the business exists
- **THEN** the business count for that actor MUST remain one

### Requirement: Onboarding audit
Each successful create, currency write, timezone write, payment-method write, and completion MUST append one audit event in the same transaction, using the existing audit table. Action names MUST be `business.created`, `business.currency_configured`, `business.timezone_configured`, `business.payment_methods_configured`, and `business.onboarding_completed`.

#### Scenario: Currency audit
- **WHEN** a currency is stored for the first time
- **THEN** an audit event with action `business.currency_configured` MUST exist for that business

### Requirement: Out of scope behavior stays absent
This capability MUST NOT implement confirmation policy, assisted-operation consent, role administration, payment-pending sales, mixed payments, or a post-completion settings UI.

#### Scenario: No pending payment
- **WHEN** onboarding completes
- **THEN** the system MUST NOT create a payment-pending sale state and MUST NOT add a confirmation-policy configuration
