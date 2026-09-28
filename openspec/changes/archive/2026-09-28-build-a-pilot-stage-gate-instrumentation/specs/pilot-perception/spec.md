## ADDED Requirements

### Requirement: Anti-POS perception uses a versioned question set
The system MUST support question set version `anti_pos@1` for RF-096. Each persisted answer MUST store `question_set_version`, `question_code`, and closed `response_code`. Allowed questions for `@1` MUST be exactly `close_organizer`, `information_delivery`, `product_category`, and `workflow_ownership`. Allowed response codes MUST be defined per question in policy `anti_pos@1` and MUST be rejected by the database or domain if unknown.

#### Scenario: Unknown question is rejected
- **WHEN** a write uses `question_code=net_promoter`
- **THEN** the write MUST be rejected

### Requirement: PilotPerceptionResponse is tenant-scoped and structured
The system MUST persist responses in `operations.pilot_perception_responses` with `id`, `business_id`, `capture_id`, optional `cohort_code`, `question_set_version`, `question_code`, `response_code`, optional `note` (max 500 characters), `captured_at`, and `capture_source` (`internal_interview` or `internal_import`). Rows MUST be append-only after insert. `note` MUST NOT be classified by an LLM for gate decisions.

#### Scenario: Multiple answers share one capture
- **WHEN** an interview records four questions in one session
- **THEN** four rows MUST share the same `capture_id` and distinct `question_code` values

### Requirement: Anti-POS classification is deterministic
Classification version `anti_pos_classification@1` MUST map a business's latest complete capture in window to exactly one of `operator_perceived`, `mixed`, `pos_like`, or `insufficient_evidence` using only structured `response_code` values. Rules MUST match design: `pos_like` when `product_category=another_system` OR the merchant-organizes-and-searches pattern; `operator_perceived` when operator-help and Lumo/shared organizer and affirmative workflow ownership; `mixed` when at least two non-unsure answers remain; `insufficient_evidence` when fewer than three answered questions or all `unsure`.

#### Scenario: POS-only description classifies pos_like
- **WHEN** `product_category=another_system` regardless of other answers
- **THEN** classification MUST be `pos_like`

#### Scenario: All unsure is insufficient
- **WHEN** all four responses are `unsure`
- **THEN** classification MUST be `insufficient_evidence`

### Requirement: Perception capture has no merchant UI in this slice
Recording perception MUST be available through a trusted internal write path only. The system MUST NOT add Flutter survey UI, Business Stream prompts, or merchant HTTP routes for perception in this capability.

#### Scenario: No new merchant route
- **WHEN** OpenAPI for merchant `lumo_app` routes is inspected after implementation
- **THEN** no path MUST expose stage gate or perception write APIs

### Requirement: Sufficient capture is defined for gate perception
A sufficient `anti_pos@1` capture for a business MUST be the latest capture with `captured_at <= evidence_cutoff_at` where all four questions (`close_organizer`, `information_delivery`, `product_category`, `workflow_ownership`) are answered with `response_code` not equal to `unsure`. One merchant MUST contribute at most one such capture per assessment. Captures after cutoff MUST NOT affect the assessment. Incomplete or unsure-heavy captures MUST NOT count in cohort perception denominators and MUST NOT count as negative.

#### Scenario: Three unsure answers is not sufficient
- **WHEN** the latest capture has only one non-unsure answer
- **THEN** that business MUST NOT count toward cohort perception denominators

### Requirement: Anti-POS classification is diagnostic for the gate
Classification `anti_pos_classification@1` MUST be computed and stored on assessments for diagnosis including `pos_like` incidence. Blocking perception rules for policy `@1` MUST be only `delegation_perception` and `proactive_information_delivery`. There MUST be no blocking rule based solely on majority `operator_perceived`.

#### Scenario: Operator perceived majority is not blocking alone
- **WHEN** cohort diagnostic classification shows majority `operator_perceived` but `delegation_perception` fails the seventy percent rule
- **THEN** overall status MUST be `not_ready` from `delegation_perception` and MUST NOT be `ready` based on classification alone

### Requirement: Perception feeds gate criteria without sentiment scoring
Blocking criteria MUST consume structured `response_code` values only. The system MUST NOT persist or compute an LLM sentiment score or natural-language summary as a gate input.

#### Scenario: Free-text note is not scored
- **WHEN** a response includes a `note` explaining frustration
- **THEN** blocking criterion status MUST depend only on `response_code` fields from the question set
