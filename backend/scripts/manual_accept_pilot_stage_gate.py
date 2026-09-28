"""One-off manual acceptance runner for build-a-pilot-stage-gate-instrumentation.

Test-owned tenants only (deterministic UUIDs). Not part of pytest.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, time, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.bootstrap.app import create_app
from app.bootstrap.settings import Settings
from app.domain.shared.ids import new_uuid7
from app.infrastructure.persistence.engine import create_engine_from_settings, create_session_factory
from app.infrastructure.persistence.models import (
    PilotPerceptionResponseRow,
    StageGateAssessmentRow,
)
from app.infrastructure.persistence.rls import set_current_business_id
from tests.conftest import settings_kwargs
from tests.isolation import register_test_tenant, seed_catalog_tenant
from tests.test_daily_close_confirmation import _confirm, _ready, _seed
from tests.test_daily_close_preparation import _cash_sale, _post

ZONE = ZoneInfo("America/Mexico_City")
COHORT = "build-a-manual-accept-2026"
COHORT_SHORT = "build-a-manual-accept-short-2026"
WINDOW_START = date(2026, 9, 1)
WINDOW_END = date(2026, 9, 14)
CUTOFF = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
CUTOFF_LATER = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
ENROLL_START = date(2026, 9, 1)
PERCEPTION_AT = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)

BIZ = {
    "insufficient": UUID("aaaaaaaa-bbbb-4ccc-8ddd-000000000001"),
    "not_ready": UUID("aaaaaaaa-bbbb-4ccc-8ddd-000000000002"),
    "cohort_a": UUID("aaaaaaaa-bbbb-4ccc-8ddd-000000000003"),
    "cohort_b": UUID("aaaaaaaa-bbbb-4ccc-8ddd-000000000004"),
    "cohort_c": UUID("aaaaaaaa-bbbb-4ccc-8ddd-000000000005"),
    "short_1": UUID("aaaaaaaa-bbbb-4ccc-8ddd-000000000006"),
    "short_2": UUID("aaaaaaaa-bbbb-4ccc-8ddd-000000000007"),
}
NAMES = {
    "insufficient": "MA Pilot Insufficient",
    "not_ready": "MA Pilot Not Ready",
    "cohort_a": "MA Pilot Cohort A",
    "cohort_b": "MA Pilot Cohort B",
    "cohort_c": "MA Pilot Cohort C",
    "short_1": "MA Pilot Short One",
    "short_2": "MA Pilot Short Two",
}


def _utc_for_day(d: date) -> str:
    instant = datetime.combine(d, time(20, 0), tzinfo=ZONE).astimezone(timezone.utc)
    return instant.isoformat()


def _cli(*args: str) -> str:
    env = {
        **dict(__import__("os").environ),
        "APP_ENV": "test",
        "DATABASE_URL": settings_kwargs()["DATABASE_URL"],
        "DATABASE_ADMIN_URL": settings_kwargs()["DATABASE_ADMIN_URL"],
        "DEV_TOKEN_SECRET": settings_kwargs()["DEV_TOKEN_SECRET"],
    }
    result = subprocess.run(
        [sys.executable, "-m", "app.cli.pilot_stage_gate", *args],
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"CLI failed: {args}\n{result.stderr}\n{result.stdout}")
    return result.stdout.strip()


_BIZ_IDS_ANY = "= ANY(CAST(:ids AS uuid[]))"


def _purge_acceptance_businesses(admin_url: str) -> None:
    engine = create_engine(admin_url)
    ids = [str(bid) for bid in BIZ.values()]
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE operations.pilot_perception_responses DISABLE TRIGGER pilot_perception_responses_append_only"))
        rls_tables = (
            "operations.pilot_perception_responses",
            "operations.stage_gate_assessments",
            "operations.pilot_program_enrollments",
            "operations.outcome_costs",
            "operations.work_absorption_records",
            "operations.outcome_runs",
            "operations.closing_snapshots",
            "operations.cash_counts",
            "operations.work_items",
            "operations.source_coverage_records",
            "operations.business_events",
            "operations.operational_days",
            "sales.payments",
            "sales.sale_items",
            "sales.sale_sessions",
            "catalog.product_aliases",
            "catalog.products",
            "audit.audit_events",
            "platform.idempotency_records",
            "platform.outbox_events",
            "platform.foundation_notes",
            "identity.memberships",
            "identity.users",
            "identity.businesses",
        )
        for table in rls_tables:
            if conn.execute(text("SELECT to_regclass(:name)"), {"name": table}).scalar() is None:
                continue
            conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
        conn.execute(
            text(f"DELETE FROM operations.pilot_perception_responses WHERE business_id {_BIZ_IDS_ANY}"),
            {"ids": ids},
        )
        conn.execute(
            text(f"DELETE FROM operations.stage_gate_assessments WHERE business_id {_BIZ_IDS_ANY}"),
            {"ids": ids},
        )
        conn.execute(
            text(
                "DELETE FROM operations.stage_gate_assessments WHERE cohort_code IN (:c1, :c2)"
            ),
            {"c1": COHORT, "c2": COHORT_SHORT},
        )
        conn.execute(
            text(f"DELETE FROM operations.pilot_program_enrollments WHERE business_id {_BIZ_IDS_ANY}"),
            {"ids": ids},
        )
        conn.execute(text(f"DELETE FROM sales.payments WHERE business_id {_BIZ_IDS_ANY}"), {"ids": ids})
        conn.execute(text(f"DELETE FROM sales.sale_items WHERE business_id {_BIZ_IDS_ANY}"), {"ids": ids})
        conn.execute(text(f"DELETE FROM sales.sale_sessions WHERE business_id {_BIZ_IDS_ANY}"), {"ids": ids})
        for table in (
            "operations.outcome_costs",
            "operations.work_absorption_records",
            "operations.work_items",
            "operations.outcome_runs",
            "operations.closing_snapshots",
            "operations.cash_counts",
            "operations.source_coverage_records",
            "operations.business_events",
            "operations.operational_days",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE business_id {_BIZ_IDS_ANY}"), {"ids": ids})
        conn.execute(text(f"DELETE FROM audit.audit_events WHERE business_id {_BIZ_IDS_ANY}"), {"ids": ids})
        conn.execute(
            text(f"DELETE FROM platform.idempotency_records WHERE business_id {_BIZ_IDS_ANY}"),
            {"ids": ids},
        )
        conn.execute(text(f"DELETE FROM platform.outbox_events WHERE business_id {_BIZ_IDS_ANY}"), {"ids": ids})
        conn.execute(
            text(f"DELETE FROM platform.foundation_notes WHERE business_id {_BIZ_IDS_ANY}"),
            {"ids": ids},
        )
        if conn.execute(text("SELECT to_regclass('catalog.product_aliases')")).scalar():
            conn.execute(
                text(f"DELETE FROM catalog.product_aliases WHERE business_id {_BIZ_IDS_ANY}"),
                {"ids": ids},
            )
        if conn.execute(text("SELECT to_regclass('catalog.products')")).scalar():
            conn.execute(text(f"DELETE FROM catalog.products WHERE business_id {_BIZ_IDS_ANY}"), {"ids": ids})
        conn.execute(text(f"DELETE FROM identity.memberships WHERE business_id {_BIZ_IDS_ANY}"), {"ids": ids})
        conn.execute(text(f"DELETE FROM identity.users WHERE business_id {_BIZ_IDS_ANY}"), {"ids": ids})
        deleted = conn.execute(
            text(f"DELETE FROM identity.businesses WHERE id {_BIZ_IDS_ANY} RETURNING id"),
            {"ids": ids},
        ).rowcount
        if deleted != len(ids):
            raise RuntimeError(
                f"acceptance purge left {len(ids) - deleted} businesses; fix FK purge order"
            )
        conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        conn.execute(text("ALTER TABLE operations.pilot_perception_responses ENABLE TRIGGER pilot_perception_responses_append_only"))
        for table in rls_tables:
            if conn.execute(text("SELECT to_regclass(:name)"), {"name": table}).scalar() is None:
                continue
            conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    engine.dispose()


def _close_days(
    client: TestClient,
    token: str,
    label: str,
    days: list[date],
    *,
    complete_all: bool = True,
    ready_only_from: int | None = None,
) -> None:
    for index, day in enumerate(days):
        prefix = f"{label}-d{index+1}"
        hdr = {"X-Debug-Now": _utc_for_day(day)}
        conv = f"conv-{prefix}"
        added = _post(client, token, "900gr zanahoria", f"{prefix}-add", conv, **hdr)
        assert added.status_code == 200, added.text
        totaled = _post(client, token, "totalizar", f"{prefix}-tot", conv, **hdr)
        assert totaled.status_code == 200, totaled.text
        paid = _post(client, token, "efectivo", f"{prefix}-pay", conv, **hdr)
        assert paid.status_code == 200, paid.text
        counted = _post(client, token, "conté 22.50", f"{prefix}-count", f"conv-{prefix}", **hdr)
        assert counted.status_code == 200, counted.text
        requested = _post(client, token, "cerrar el día", f"{prefix}-req", f"conv-{prefix}", **hdr)
        assert requested.status_code == 200, requested.text
        ui = requested.json()["ui"]
        confirmation = ui[0]["data"].get("confirmation_token") if ui else None
        assert confirmation
        if complete_all and (ready_only_from is None or index < ready_only_from):
            resp = _confirm(client, token, prefix, confirmation, **hdr)
            assert resp.status_code == 200, resp.text


def _seed_tenant(session, key: str) -> tuple[UUID, UUID, str]:
    tenant, token = seed_catalog_tenant(session, name=NAMES[key], business_id=BIZ[key])
    session.commit()
    return tenant.business_id, tenant.actor_id, token


def _enroll(bid: UUID, actor: UUID, cohort: str) -> None:
    _cli(
        "enroll",
        "--business-id",
        str(bid),
        "--actor-id",
        str(actor),
        "--cohort-code",
        cohort,
        "--pilot-started-on",
        ENROLL_START.isoformat(),
    )


def _perception(bid: UUID, actor: UUID, cohort: str, capture_id: UUID) -> None:
    _cli(
        "record-perception",
        "--business-id",
        str(bid),
        "--actor-id",
        str(actor),
        "--capture-id",
        str(capture_id),
        "--cohort-code",
        cohort,
        "--captured-at",
        PERCEPTION_AT.isoformat().replace("+00:00", "Z"),
        "--capture-source",
        "internal_interview",
        "--close-organizer",
        "lumo",
        "--information-delivery",
        "lumo_brings",
        "--product-category",
        "operator_help",
        "--workflow-ownership",
        "yes",
    )


def _assess_business(bid: UUID, actor: UUID, cohort: str, cutoff: datetime) -> UUID:
    out = _cli(
        "assess",
        "--scope",
        "business",
        "--business-id",
        str(bid),
        "--actor-id",
        str(actor),
        "--cohort-code",
        cohort,
        "--window-start",
        WINDOW_START.isoformat(),
        "--window-end",
        WINDOW_END.isoformat(),
        "--evidence-cutoff-at",
        cutoff.isoformat().replace("+00:00", "Z"),
    )
    return UUID(out)


def _assess_cohort(cohort: str, cutoff: datetime) -> UUID:
    out = _cli(
        "assess",
        "--scope",
        "cohort",
        "--cohort-code",
        cohort,
        "--window-start",
        WINDOW_START.isoformat(),
        "--window-end",
        WINDOW_END.isoformat(),
        "--evidence-cutoff-at",
        cutoff.isoformat().replace("+00:00", "Z"),
    )
    return UUID(out)


def _load_assessment(session, assessment_id: UUID, business_id: UUID | None) -> StageGateAssessmentRow:
    if business_id:
        set_current_business_id(session, business_id)
    return session.get(StageGateAssessmentRow, assessment_id)


def _criterion(row: StageGateAssessmentRow, code: str) -> dict:
    for item in row.criterion_results:
        if item["criterion_code"] == code:
            return item
    raise KeyError(code)


def main() -> None:
    settings = Settings.model_validate(settings_kwargs())
    _purge_acceptance_businesses(settings.sqlalchemy_admin_url)
    app = create_app(settings)
    factory = create_session_factory(create_engine_from_settings(settings))
    session = factory()
    report: dict = {}

    with TestClient(app) as client:
        actors: dict[str, UUID] = {}
        tokens: dict[str, str] = {}
        for key in BIZ:
            bid, actor, token = _seed_tenant(session, key)
            actors[key] = actor
            tokens[key] = token

        days3 = [date(2026, 9, d) for d in (1, 2, 3)]
        days5 = [date(2026, 9, d) for d in (1, 2, 3, 4, 5)]
        days10 = [date(2026, 9, d) for d in range(1, 11)]

        _close_days(client, tokens["insufficient"], "insuf", days3)
        _close_days(client, tokens["not_ready"], "nrdy", days5, ready_only_from=4)
        _close_days(client, tokens["cohort_a"], "ca", days10)
        _close_days(client, tokens["cohort_b"], "cb", days10)
        _close_days(client, tokens["cohort_c"], "cc", days10, ready_only_from=8)
        _close_days(client, tokens["short_1"], "s1", days5)
        _close_days(client, tokens["short_2"], "s2", days5)
        session.commit()

    for key in ("insufficient", "not_ready", "cohort_a", "cohort_b", "cohort_c", "short_1", "short_2"):
        cohort = COHORT if key in {"insufficient", "not_ready", "cohort_a", "cohort_b", "cohort_c"} else COHORT_SHORT
        _enroll(BIZ[key], actors[key], cohort)

    captures = {k: new_uuid7() for k in ("cohort_a", "cohort_b", "cohort_c")}
    for key in ("cohort_a", "cohort_b", "cohort_c"):
        _perception(BIZ[key], actors[key], COHORT, captures[key])

    aid_insuff = _assess_business(BIZ["insufficient"], actors["insufficient"], COHORT, CUTOFF)
    aid_not_ready = _assess_business(BIZ["not_ready"], actors["not_ready"], COHORT, CUTOFF)
    aid_ready = _assess_business(BIZ["cohort_a"], actors["cohort_a"], COHORT, CUTOFF)
    aid_cohort = _assess_cohort(COHORT, CUTOFF)
    aid_short = _assess_cohort(COHORT_SHORT, CUTOFF)
    aid_idem = _assess_business(BIZ["cohort_a"], actors["cohort_a"], COHORT, CUTOFF)
    aid_later = _assess_business(BIZ["cohort_a"], actors["cohort_a"], COHORT, CUTOFF_LATER)

    row_insuff = _load_assessment(session, aid_insuff, BIZ["insufficient"])
    row_not_ready = _load_assessment(session, aid_not_ready, BIZ["not_ready"])
    row_ready = _load_assessment(session, aid_ready, BIZ["cohort_a"])
    admin = create_engine(settings.sqlalchemy_admin_url)
    with admin.connect() as conn:
        row_cohort = conn.execute(
            text("SELECT overall_status, criterion_results, included_business_ids FROM operations.stage_gate_assessments WHERE id = :id"),
            {"id": aid_cohort},
        ).mappings().one()
        row_short = conn.execute(
            text("SELECT overall_status, criterion_results FROM operations.stage_gate_assessments WHERE id = :id"),
            {"id": aid_short},
        ).mappings().one()
    admin.dispose()

    report["assessments"] = {
        "insufficient": str(aid_insuff),
        "not_ready": str(aid_not_ready),
        "ready_business": str(aid_ready),
        "cohort": str(aid_cohort),
        "cohort_short": str(aid_short),
        "idempotent_rerun": str(aid_idem),
        "later_cutoff": str(aid_later),
    }
    report["status"] = {
        "insufficient": row_insuff.overall_status,
        "not_ready": row_not_ready.overall_status,
        "ready_business": row_ready.overall_status,
        "cohort": row_cohort["overall_status"],
        "cohort_short": row_short["overall_status"],
    }

    def _crit_from_row(row_map, code: str) -> dict:
        for item in row_map["criterion_results"]:
            if item["criterion_code"] == code:
                return item
        raise KeyError(code)

    report["criteria"] = {
        "insufficient_sample": _criterion(row_insuff, "sample_size_eligible_outcomes")["status"],
        "insufficient_completion": _criterion(row_insuff, "outcome_completion_rate")["status"],
        "not_ready_sample": _criterion(row_not_ready, "sample_size_eligible_outcomes")["status"],
        "not_ready_completion": _criterion(row_not_ready, "outcome_completion_rate")["status"],
        "cohort_count": _crit_from_row(row_cohort, "cohort_merchant_count")["status"],
        "cohort_short_count": _crit_from_row(row_short, "cohort_merchant_count")["status"],
        "cohort_completion": _crit_from_row(row_cohort, "outcome_completion_rate"),
    }
    delegation = _criterion(row_ready, "delegation_perception")
    report["perception_refs"] = {
        "delegation": delegation.get("evidence_refs"),
        "proactive": _criterion(row_ready, "proactive_information_delivery").get("evidence_refs"),
    }
    report["idempotent_match"] = aid_ready == aid_idem
    report["later_cutoff_new"] = aid_later != aid_ready

    set_current_business_id(session, BIZ["cohort_a"])
    perception_ids = {
        str(r.id) for r in session.scalars(select(PilotPerceptionResponseRow)).all()
    }
    ref_ids = {r["id"] for r in delegation["evidence_refs"] if r["kind"] == "pilot_perception_response"}
    report["perception_row_ids"] = sorted(perception_ids)
    report["delegation_ref_ids"] = sorted(ref_ids)

    set_current_business_id(session, BIZ["cohort_b"])
    report["cross_tenant_perception_visible"] = len(
        list(session.scalars(select(PilotPerceptionResponseRow)).all())
    )

    set_current_business_id(session, BIZ["cohort_a"])
    report["merchant_cohort_assessments"] = len(
        list(session.scalars(select(StageGateAssessmentRow)).all())
    )

    print(json.dumps(report, indent=2, default=str))
    session.close()


if __name__ == "__main__":
    main()
