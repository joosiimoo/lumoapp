"""Work absorption and outcome cost instrumentation.

Revision ID: 0013_work_absorption_outcome_cost
Revises: 0012_source_coverage_event_memory
Create Date: 2026-09-27
"""

from __future__ import annotations

from alembic import op

revision = "0013_work_absorption_outcome_cost"
down_revision = "0012_source_coverage_event_memory"
branch_labels = None
depends_on = None

_EXECUTION_MODES = (
    "manual_by_business",
    "assisted_by_lumo",
    "prepared_by_lumo",
    "executed_with_confirmation",
    "executed_and_reversible",
    "executed_under_policy",
    "reviewed_by_lumo_operator",
    "fully_automated",
)
_TASK_TYPES = (
    "organize_registered_sales",
    "calculate_expected_cash",
    "record_cash_count",
    "reconcile_cash",
    "prepare_close",
    "confirm_close",
)
_COMPONENT_STATUS = ("measured", "estimated", "unavailable")


def upgrade() -> None:
    op.execute(
        """
        DO $fn$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_work_items_id_business'
                  AND conrelid = 'operations.work_items'::regclass
            ) THEN
                ALTER TABLE operations.work_items
                ADD CONSTRAINT uq_work_items_id_business UNIQUE (id, business_id);
            END IF;
        END
        $fn$;
        """
    )
    modes_sql = ", ".join(f"'{m}'" for m in _EXECUTION_MODES)
    tasks_sql = ", ".join(f"'{t}'" for t in _TASK_TYPES)
    status_sql = ", ".join(f"'{s}'" for s in _COMPONENT_STATUS)
    op.execute(
        f"""
        CREATE TABLE operations.work_absorption_records (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            outcome_run_id UUID NOT NULL,
            work_item_id UUID NULL,
            task_type VARCHAR(64) NOT NULL,
            previous_execution_mode VARCHAR(64) NOT NULL,
            current_execution_mode VARCHAR(64) NOT NULL,
            human_steps_before INTEGER NOT NULL,
            human_steps_after INTEGER NOT NULL,
            estimated_minutes_saved INTEGER NOT NULL,
            business_intervention_seconds INTEGER NULL,
            internal_intervention_seconds INTEGER NULL,
            automation_level VARCHAR(16) NOT NULL,
            evidence_ids JSONB NOT NULL,
            baseline_version VARCHAR(128) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_work_absorption_records_task
                UNIQUE (business_id, outcome_run_id, task_type),
            CONSTRAINT ck_work_absorption_task_type
                CHECK (task_type IN ({tasks_sql})),
            CONSTRAINT ck_work_absorption_previous_mode
                CHECK (previous_execution_mode IN ({modes_sql})),
            CONSTRAINT ck_work_absorption_current_mode
                CHECK (current_execution_mode IN ({modes_sql})),
            CONSTRAINT ck_work_absorption_automation_level
                CHECK (automation_level IN ('manual', 'assisted', 'automated')),
            CONSTRAINT ck_work_absorption_steps_nonneg
                CHECK (
                    human_steps_before >= 0
                    AND human_steps_after >= 0
                    AND estimated_minutes_saved >= 0
                ),
            CONSTRAINT ck_work_absorption_business_intervention
                CHECK (
                    business_intervention_seconds IS NULL
                    OR business_intervention_seconds >= 0
                ),
            CONSTRAINT ck_work_absorption_internal_intervention
                CHECK (
                    internal_intervention_seconds IS NULL
                    OR internal_intervention_seconds >= 0
                ),
            CONSTRAINT ck_work_absorption_evidence_array
                CHECK (jsonb_typeof(evidence_ids) = 'array'),
            CONSTRAINT fk_work_absorption_outcome_run
                FOREIGN KEY (outcome_run_id, business_id)
                REFERENCES operations.outcome_runs (id, business_id),
            CONSTRAINT fk_work_absorption_work_item
                FOREIGN KEY (work_item_id, business_id)
                REFERENCES operations.work_items (id, business_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_work_absorption_records_business_id "
        "ON operations.work_absorption_records (business_id)"
    )
    op.execute(
        "CREATE INDEX ix_work_absorption_records_outcome_run_id "
        "ON operations.work_absorption_records (outcome_run_id)"
    )
    op.execute(
        f"""
        CREATE TABLE operations.outcome_costs (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            outcome_run_id UUID NOT NULL,
            currency CHAR(3) NOT NULL,
            model_call_count INTEGER NULL,
            model_call_count_status VARCHAR(16) NOT NULL,
            prompt_tokens INTEGER NULL,
            completion_tokens INTEGER NULL,
            model_token_status VARCHAR(16) NOT NULL,
            model_cost_amount NUMERIC(12, 2) NULL,
            model_cost_status VARCHAR(16) NOT NULL,
            infrastructure_cost_amount NUMERIC(12, 2) NULL,
            infrastructure_cost_status VARCHAR(16) NOT NULL,
            retry_count INTEGER NOT NULL,
            retry_count_status VARCHAR(16) NOT NULL,
            business_intervention_seconds INTEGER NULL,
            internal_intervention_seconds INTEGER NULL,
            estimated_total_cost_amount NUMERIC(12, 2) NULL,
            cost_completeness VARCHAR(16) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_outcome_costs_identity UNIQUE (business_id, outcome_run_id),
            CONSTRAINT ck_outcome_costs_currency CHECK (currency = 'USD'),
            CONSTRAINT ck_outcome_costs_component_status
                CHECK (
                    model_call_count_status IN ({status_sql})
                    AND model_token_status IN ({status_sql})
                    AND model_cost_status IN ({status_sql})
                    AND infrastructure_cost_status IN ({status_sql})
                    AND retry_count_status IN ({status_sql})
                ),
            CONSTRAINT ck_outcome_costs_completeness
                CHECK (cost_completeness IN ('partial', 'complete')),
            CONSTRAINT ck_outcome_costs_retry_nonneg CHECK (retry_count >= 0),
            CONSTRAINT ck_outcome_costs_business_intervention
                CHECK (
                    business_intervention_seconds IS NULL
                    OR business_intervention_seconds >= 0
                ),
            CONSTRAINT ck_outcome_costs_internal_intervention
                CHECK (
                    internal_intervention_seconds IS NULL
                    OR internal_intervention_seconds >= 0
                ),
            CONSTRAINT fk_outcome_costs_outcome_run
                FOREIGN KEY (outcome_run_id, business_id)
                REFERENCES operations.outcome_runs (id, business_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_outcome_costs_business_id ON operations.outcome_costs (business_id)")
    op.execute(
        "CREATE INDEX ix_outcome_costs_outcome_run_id ON operations.outcome_costs (outcome_run_id)"
    )
    for table in ("work_absorption_records", "outcome_costs"):
        op.execute(f"ALTER TABLE operations.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE operations.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON operations.{table}
            USING (business_id::text = current_setting('app.current_business_id', true))
            """
        )
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON operations.{table} TO lumo_app"
        )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION operations.reject_instrumentation_when_outcome_completed()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM operations.outcome_runs r
                WHERE r.id = NEW.outcome_run_id
                  AND r.business_id = NEW.business_id
                  AND r.status = 'completed'
            ) THEN
                RAISE EXCEPTION 'instrumentation is immutable after outcome completion';
            END IF;
            RETURN NEW;
        END
        $fn$;
        """
    )
    for table in ("work_absorption_records", "outcome_costs"):
        op.execute(
            f"""
            CREATE TRIGGER {table}_freeze_completed
            BEFORE INSERT OR UPDATE ON operations.{table}
            FOR EACH ROW
            EXECUTE FUNCTION operations.reject_instrumentation_when_outcome_completed();
            """
        )


def downgrade() -> None:
    op.execute(
        """
        DO $fn$
        DECLARE
            absorption_rows integer;
            cost_rows integer;
        BEGIN
            SELECT count(*)::integer INTO absorption_rows FROM operations.work_absorption_records;
            SELECT count(*)::integer INTO cost_rows FROM operations.outcome_costs;
            IF absorption_rows > 0 OR cost_rows > 0 THEN
                RAISE EXCEPTION 'cannot downgrade 0013 while instrumentation rows exist';
            END IF;
        END
        $fn$;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS work_absorption_records_freeze_completed ON operations.work_absorption_records")
    op.execute("DROP TRIGGER IF EXISTS outcome_costs_freeze_completed ON operations.outcome_costs")
    op.execute("DROP FUNCTION IF EXISTS operations.reject_instrumentation_when_outcome_completed()")
    op.execute("DROP TABLE operations.outcome_costs")
    op.execute("DROP TABLE operations.work_absorption_records")
