## ADDED Requirements

### Requirement: Cohort stage gate evaluation does not weaken merchant RLS
Trusted internal cohort evaluation MAY aggregate metrics across multiple `business_id` values only by sequential per-tenant reads under each tenant context or an equivalent admin connection explicitly allowed for internal instrumentation. Merchant-facing `lumo_app` role MUST NOT receive `SELECT` on cohort-scoped `stage_gate_assessments` or cross-tenant perception rows. Cohort results MUST NOT be exposed through merchant APIs.

#### Scenario: Merchant role cannot list cohort assessments
- **WHEN** `lumo_app` queries `operations.stage_gate_assessments` with `scope_type=cohort`
- **THEN** zero rows MUST be returned
