from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from uuid import UUID

from app.infrastructure.persistence.pilot_stage_gate_runner import (
    assess_business_stage_gate,
    assess_cohort_stage_gate,
)
from app.bootstrap.settings import get_settings
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.engine import create_engine_from_settings, create_session_factory
from app.infrastructure.persistence.pilot_stage_gate import PilotStageGateRepository


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pilot stage gate internal tools")
    sub = parser.add_subparsers(dest="command", required=True)

    enroll = sub.add_parser("enroll")
    enroll.add_argument("--business-id", type=UUID, required=True)
    enroll.add_argument("--actor-id", type=UUID, required=True)
    enroll.add_argument("--cohort-code", required=True)
    enroll.add_argument("--pilot-started-on", type=_parse_date, required=True)
    enroll.add_argument("--pilot-ended-on", type=_parse_date)

    record = sub.add_parser("record-perception")
    record.add_argument("--business-id", type=UUID, required=True)
    record.add_argument("--actor-id", type=UUID, required=True)
    record.add_argument("--capture-id", type=UUID, required=True)
    record.add_argument("--cohort-code")
    record.add_argument("--captured-at", type=_parse_datetime, required=True)
    record.add_argument("--capture-source", required=True)
    record.add_argument("--note")
    record.add_argument("--close-organizer", required=True)
    record.add_argument("--information-delivery", required=True)
    record.add_argument("--product-category", required=True)
    record.add_argument("--workflow-ownership", required=True)

    assess = sub.add_parser("assess")
    assess.add_argument("--scope", choices=("business", "cohort"), required=True)
    assess.add_argument("--cohort-code", required=True)
    assess.add_argument("--business-id", type=UUID)
    assess.add_argument("--actor-id", type=UUID)
    assess.add_argument("--window-start", type=_parse_date, required=True)
    assess.add_argument("--window-end", type=_parse_date, required=True)
    assess.add_argument("--evidence-cutoff-at", type=_parse_datetime, required=True)
    assess.add_argument("--evaluated-at", type=_parse_datetime)

    args = parser.parse_args()
    settings = get_settings()
    factory = create_session_factory(create_engine_from_settings(settings))

    if args.command == "enroll":
        evaluated_at = datetime.now(timezone.utc)
        with factory() as session:
            tenant = TenantContext(business_id=args.business_id, actor_id=args.actor_id)
            PilotStageGateRepository(session).enroll_business(
                tenant=tenant,
                cohort_code=args.cohort_code,
                pilot_started_on=args.pilot_started_on,
                pilot_ended_on=args.pilot_ended_on,
                created_at=evaluated_at,
            )
            session.commit()
        print("enrolled")
        return

    if args.command == "record-perception":
        answers = {
            "close_organizer": args.close_organizer,
            "information_delivery": args.information_delivery,
            "product_category": args.product_category,
            "workflow_ownership": args.workflow_ownership,
        }
        with factory() as session:
            tenant = TenantContext(business_id=args.business_id, actor_id=args.actor_id)
            repo = PilotStageGateRepository(session)
            first = True
            for question_code, response_code in answers.items():
                repo.record_perception_capture(
                    tenant=tenant,
                    capture_id=args.capture_id,
                    cohort_code=args.cohort_code,
                    answers={question_code: response_code},
                    captured_at=args.captured_at,
                    capture_source=args.capture_source,
                    note=args.note if first else None,
                )
                first = False
            session.commit()
        print("recorded")
        return

    if args.command == "assess":
        evaluated_at = args.evaluated_at or args.evidence_cutoff_at
        if args.scope == "business":
            if args.business_id is None or args.actor_id is None:
                raise SystemExit("business scope requires --business-id and --actor-id")
            with factory() as session:
                tenant = TenantContext(business_id=args.business_id, actor_id=args.actor_id)
                assessment_id = assess_business_stage_gate(
                    session=session,
                    tenant=tenant,
                    cohort_code=args.cohort_code,
                    evidence_window_start=args.window_start,
                    evidence_window_end=args.window_end,
                    evidence_cutoff_at=args.evidence_cutoff_at,
                    evaluated_at=evaluated_at,
                )
                session.commit()
            print(assessment_id)
            return
        assessment_id = assess_cohort_stage_gate(
            admin_url=settings.sqlalchemy_admin_url,
            cohort_code=args.cohort_code,
            evidence_window_start=args.window_start,
            evidence_window_end=args.window_end,
            evidence_cutoff_at=args.evidence_cutoff_at,
            evaluated_at=evaluated_at,
        )
        print(assessment_id)


if __name__ == "__main__":
    main()
