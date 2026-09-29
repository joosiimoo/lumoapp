## ADDED Requirements

### Requirement: Startup follows onboarding status
When the authenticated actor has no business or the business onboarding status is `in_progress`, including when the next field is `ready_to_complete`, Flutter MUST show the conversational onboarding surface without the tab bar and MUST NOT load Business Stream. When status is `completed`, Flutter MUST show the existing `LumoHome` shell. The onboarding surface MUST use the existing Lumo scaffold, composer, and message styling. It MUST NOT present a multi-step configuration wizard, a settings page, a dashboard, or a POS setup screen. It MUST render `onboarding_choice` version `1` and `onboarding_confirmation` version `1` when the backend emits them. The confirmation card is part of the conversation. It MUST NOT persist a timezone that the merchant has not confirmed. It MUST NOT mark onboarding complete except by sending the explicit `start_using_lumo` action.

#### Scenario: Incomplete onboarding
- **WHEN** the session reports `onboarding_status` `in_progress`
- **THEN** the visible surface MUST be onboarding and Business Stream MUST NOT be mounted

#### Scenario: Completed onboarding
- **WHEN** the session reports `onboarding_status` `completed`
- **THEN** the app MUST show the existing Inicio experience
