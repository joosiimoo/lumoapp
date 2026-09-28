"""Pilot stage gate and perception instrumentation.

Revision ID: 0014_pilot_stage_gate_instrumentation
Revises: 0013_work_absorption_outcome_cost
Create Date: 2026-09-27
"""

from __future__ import annotations

from alembic import op

revision = "0014_pilot_stage_gate_instrumentation"
down_revision = "0013_work_absorption_outcome_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        CREATE TABLE operations.pilot_program_enrollments (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            cohort_code VARCHAR(64) NOT NULL,
            pilot_started_on DATE NOT NULL,
            pilot_ended_on DATE NULL,
            created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT ck_pilot_program_enrollments_dates
                CHECK (pilot_ended_on IS NULL OR pilot_ended_on >= pilot_started_on),
            CONSTRAINT fk_pilot_program_enrollments_business
                FOREIGN KEY (business_id) REFERENCES identity.businesses (id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_pilot_program_enrollments_business_id "
        "ON operations.pilot_program_enrollments (business_id)"
    )
    op.execute(
        """
        ALTER TABLE operations.pilot_program_enrollments
        ADD CONSTRAINT excl_pilot_program_enrollments_no_overlap
        EXCLUDE USING gist (
            business_id WITH =,
            cohort_code WITH =,
            daterange(
                pilot_started_on,
                COALESCE(pilot_ended_on, 'infinity'::date),
                '[]'
            ) WITH &&
        )
        """
    )

    op.execute(
        """
        CREATE TABLE operations.pilot_perception_responses (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            capture_id UUID NOT NULL,
            cohort_code VARCHAR(64) NULL,
            question_set_version VARCHAR(64) NOT NULL,
            question_code VARCHAR(64) NOT NULL,
            response_code VARCHAR(64) NOT NULL,
            note VARCHAR(500) NULL,
            captured_at TIMESTAMPTZ NOT NULL,
            capture_source VARCHAR(32) NOT NULL,
            CONSTRAINT uq_pilot_perception_responses_capture_question
                UNIQUE (business_id, capture_id, question_code),
            CONSTRAINT ck_pilot_perception_question_code
                CHECK (question_code IN (
                    'close_organizer', 'information_delivery',
                    'product_category', 'workflow_ownership'
                )),
            CONSTRAINT ck_pilot_perception_capture_source
                CHECK (capture_source IN ('internal_interview', 'internal_import')),
            CONSTRAINT ck_pilot_perception_note_length
                CHECK (note IS NULL OR length(note) <= 500),
            CONSTRAINT fk_pilot_perception_responses_business
                FOREIGN KEY (business_id) REFERENCES identity.businesses (id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_pilot_perception_responses_business_id "
        "ON operations.pilot_perception_responses (business_id)"
    )

    op.execute(
        """
        CREATE TABLE operations.stage_gate_assessments (
            id UUID PRIMARY KEY,
            scope_type VARCHAR(16) NOT NULL,
            business_id UUID NULL,
            cohort_code VARCHAR(64) NOT NULL,
            build_identifier VARCHAR(64) NOT NULL,
            policy_version VARCHAR(64) NOT NULL,
            evidence_window_start DATE NOT NULL,
            evidence_window_end DATE NOT NULL,
            evidence_cutoff_at TIMESTAMPTZ NOT NULL,
            overall_status VARCHAR(32) NOT NULL,
            criterion_results JSONB NOT NULL,
            included_outcome_run_refs JSONB NOT NULL,
            included_business_ids JSONB NULL,
            evaluated_at TIMESTAMPTZ NOT NULL,
            finalized_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT ck_stage_gate_assessments_scope
                CHECK (scope_type IN ('business', 'cohort')),
            CONSTRAINT ck_stage_gate_assessments_build
                CHECK (build_identifier = 'mvp_build_a'),
            CONSTRAINT ck_stage_gate_assessments_window
                CHECK (evidence_window_end >= evidence_window_start),
            CONSTRAINT ck_stage_gate_assessments_scope_business
                CHECK (
                    (scope_type = 'business' AND business_id IS NOT NULL)
                    OR (scope_type = 'cohort' AND business_id IS NULL)
                ),
            CONSTRAINT ck_stage_gate_assessments_overall
                CHECK (overall_status IN ('ready', 'not_ready', 'insufficient_evidence')),
            CONSTRAINT ck_stage_gate_assessments_results
                CHECK (jsonb_typeof(criterion_results) = 'array'),
            CONSTRAINT ck_stage_gate_assessments_refs
                CHECK (jsonb_typeof(included_outcome_run_refs) = 'array')
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_stage_gate_assessments_identity
        ON operations.stage_gate_assessments (
            scope_type,
            COALESCE(business_id, '00000000-0000-0000-0000-000000000000'::uuid),
            cohort_code,
            policy_version,
            evidence_window_start,
            evidence_window_end,
            evidence_cutoff_at
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_stage_gate_assessments_business_id "
        "ON operations.stage_gate_assessments (business_id)"
    )

    for table in ("pilot_program_enrollments", "pilot_perception_responses"):
        op.execute(f"ALTER TABLE operations.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE operations.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON operations.{table}
            USING (business_id::text = current_setting('app.current_business_id', true))
            """
        )
        grants = "SELECT, INSERT, DELETE" if table == "pilot_program_enrollments" else "SELECT, INSERT"
        op.execute(f"GRANT {grants} ON operations.{table} TO lumo_app")

    op.execute("ALTER TABLE operations.stage_gate_assessments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operations.stage_gate_assessments FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON operations.stage_gate_assessments
        USING (
            business_id IS NOT NULL
            AND business_id::text = current_setting('app.current_business_id', true)
        )
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON operations.pilot_perception_responses TO lumo_app"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON operations.stage_gate_assessments TO lumo_app"
    )
    op.execute(
        """
        CREATE POLICY stage_gate_cohort_admin ON operations.stage_gate_assessments
        AS PERMISSIVE
        FOR ALL
        TO lumo_admin
        USING (scope_type = 'cohort' AND business_id IS NULL)
        WITH CHECK (scope_type = 'cohort' AND business_id IS NULL)
        """
    )
    op.execute(
        "GRANT SELECT, INSERT ON operations.stage_gate_assessments TO lumo_admin"
    )
    op.execute(
        "GRANT SELECT ON operations.pilot_program_enrollments TO lumo_admin"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION operations.reject_pilot_perception_mutation()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            RAISE EXCEPTION 'pilot perception responses are append-only';
        END
        $fn$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER pilot_perception_responses_append_only
        BEFORE UPDATE OR DELETE ON operations.pilot_perception_responses
        FOR EACH ROW
        EXECUTE FUNCTION operations.reject_pilot_perception_mutation();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION operations.reject_finalized_stage_gate_assessment_mutation()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            IF OLD.finalized_at IS NOT NULL THEN
                RAISE EXCEPTION 'stage gate assessment is immutable after finalization';
            END IF;
            RETURN NEW;
        END
        $fn$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER stage_gate_assessments_immutable
        BEFORE UPDATE OR DELETE ON operations.stage_gate_assessments
        FOR EACH ROW
        EXECUTE FUNCTION operations.reject_finalized_stage_gate_assessment_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $fn$
        DECLARE
            perception_rows integer;
            assessment_rows integer;
            enrollment_rows integer;
        BEGIN
            SELECT count(*)::integer INTO perception_rows FROM operations.pilot_perception_responses;
            SELECT count(*)::integer INTO assessment_rows FROM operations.stage_gate_assessments;
            SELECT count(*)::integer INTO enrollment_rows FROM operations.pilot_program_enrollments;
            IF perception_rows > 0 OR assessment_rows > 0 OR enrollment_rows > 0 THEN
                RAISE EXCEPTION 'cannot downgrade 0014 while pilot stage gate rows exist';
            END IF;
        END
        $fn$;
        """
    )
    op.execute(
        "DROP POLICY IF EXISTS stage_gate_cohort_admin ON operations.stage_gate_assessments"
    )
    op.execute("DROP TRIGGER IF EXISTS stage_gate_assessments_immutable ON operations.stage_gate_assessments")
    op.execute("DROP TRIGGER IF EXISTS pilot_perception_responses_append_only ON operations.pilot_perception_responses")
    op.execute("DROP FUNCTION IF EXISTS operations.reject_finalized_stage_gate_assessment_mutation()")
    op.execute("DROP FUNCTION IF EXISTS operations.reject_pilot_perception_mutation()")
    op.execute("DROP TABLE operations.stage_gate_assessments")
    op.execute("DROP TABLE operations.pilot_perception_responses")
    op.execute("DROP TABLE operations.pilot_program_enrollments")
