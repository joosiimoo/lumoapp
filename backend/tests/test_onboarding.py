from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.dependencies.auth import issue_dev_token, issue_pre_tenant_dev_token
from app.domain.identity.onboarding import (
    next_required_field,
    normalize_business_name,
    payment_method_allowed,
    validate_currency,
    validate_payment_methods,
    validate_timezone,
    OnboardingValidationError,
)
from app.domain.shared.ids import new_uuid7
from app.infrastructure.persistence.models import BusinessRow, MembershipRow, UserRow
from app.infrastructure.persistence.rls import set_current_actor_id, set_current_business_id
from app.infrastructure.persistence.seed import CARROTA_BUSINESS_ID, ensure_carrota_seed
from tests.conftest import TEST_SECRET, make_settings, postgres_available, seed_business
from tests.isolation import register_test_tenant

pytestmark = pytest.mark.skipif(not postgres_available(make_settings()), reason="PostgreSQL is not available")


def _auth(token: str, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key:
        headers["Idempotency-Key"] = key
    return headers


def test_name_currency_timezone_and_methods_validation() -> None:
    assert normalize_business_name("  Pan   Dulce ") == "Pan Dulce"
    with pytest.raises(OnboardingValidationError):
        normalize_business_name("   ")
    assert validate_currency("mxn") == "MXN"
    with pytest.raises(OnboardingValidationError):
        validate_currency("USD")
    assert validate_timezone("America/Mexico_City") == "America/Mexico_City"
    with pytest.raises(OnboardingValidationError):
        validate_timezone("CST")
    with pytest.raises(OnboardingValidationError):
        validate_timezone("Mexico")
    with pytest.raises(OnboardingValidationError):
        validate_payment_methods([])
    assert validate_payment_methods(["transfer", "cash"]) == ["cash", "transfer"]
    assert (
        next_required_field(
            has_business=True,
            currency="MXN",
            timezone="America/Mexico_City",
            enabled_payment_methods=["cash"],
            onboarding_status="in_progress",
        )
        == "ready_to_complete"
    )
    assert payment_method_allowed(enabled_payment_methods=None, method="card")
    assert not payment_method_allowed(enabled_payment_methods=["cash"], method="card")


def test_onboarding_flow_resume_and_completion(client: TestClient, db_session) -> None:
    actor = new_uuid7()
    token = issue_pre_tenant_dev_token(user_id=actor, secret=TEST_SECRET)
    created = client.post(
        "/api/v1/onboarding/apply",
        json={"name": "  Panadería  Norte "},
        headers=_auth(token, "create-1"),
    )
    assert created.status_code == 200, created.text
    body = created.json()
    business_id = UUID(body["business_id"])
    register_test_tenant(business_id)
    assert body["onboarding_status"] == "in_progress"
    assert body["next_required_field"] == "currency"
    assert body["enabled_payment_methods"] is None
    assert UUID(body["business_id"]).version == 7
    tenant_token = body["access_token"]

    rejected = client.post(
        "/api/v1/onboarding/apply",
        json={"business_id": str(new_uuid7()), "currency": "MXN"},
        headers=_auth(tenant_token, "bad-id"),
    )
    assert rejected.status_code == 422

    usd = client.post(
        "/api/v1/onboarding/apply",
        json={"currency": "USD"},
        headers=_auth(tenant_token, "usd"),
    )
    assert usd.status_code == 422

    mxn = client.post(
        "/api/v1/onboarding/apply",
        json={"currency": "MXN"},
        headers=_auth(tenant_token, "mxn"),
    )
    assert mxn.status_code == 200
    assert mxn.json()["next_required_field"] == "timezone"

    status = client.get("/api/v1/onboarding/status", headers=_auth(tenant_token))
    assert status.json()["next_required_field"] == "timezone"
    assert status.json()["business"]["name"] == "Panadería Norte"

    zone = client.post(
        "/api/v1/onboarding/apply",
        json={"timezone": "America/Mexico_City"},
        headers=_auth(tenant_token, "zone"),
    )
    assert zone.status_code == 200
    methods = client.post(
        "/api/v1/onboarding/apply",
        json={"payment_methods": ["cash"]},
        headers=_auth(tenant_token, "cash"),
    )
    assert methods.status_code == 200
    assert methods.json()["onboarding_status"] == "in_progress"
    assert methods.json()["next_required_field"] == "ready_to_complete"
    assert methods.json()["confirmation"]["name"] == "Panadería Norte"
    assert methods.json()["ui"][0]["component"] == "onboarding_confirmation"
    assert methods.json()["ui"][0]["actions"][0]["action_id"] == "start_using_lumo"

    corrected = client.post(
        "/api/v1/onboarding/apply",
        json={"payment_methods": ["cash", "transfer"]},
        headers=_auth(tenant_token, "cash-transfer"),
    )
    assert corrected.json()["enabled_payment_methods"] == ["cash", "transfer"]
    assert corrected.json()["next_required_field"] == "ready_to_complete"

    done = client.post(
        "/api/v1/onboarding/apply",
        json={"start_using_lumo": True},
        headers=_auth(tenant_token, "start"),
    )
    assert done.status_code == 200
    assert done.json()["onboarding_status"] == "completed"

    closed = client.post(
        "/api/v1/onboarding/apply",
        json={"timezone": "America/Cancun"},
        headers=_auth(tenant_token, "after"),
    )
    assert closed.status_code == 422

    set_current_business_id(db_session, business_id)
    row = db_session.get(BusinessRow, business_id)
    assert row is not None
    assert row.timezone == "America/Mexico_City"
    assert row.onboarding_status == "completed"
    actions = {
        item[0]
        for item in db_session.execute(
            text(
                "SELECT action FROM audit.audit_events WHERE business_id = :business_id"
            ),
            {"business_id": business_id},
        )
    }
    assert {
        "business.created",
        "business.currency_configured",
        "business.timezone_configured",
        "business.payment_methods_configured",
        "business.onboarding_completed",
    } <= actions


def test_pre_tenant_replay_and_conflict(client: TestClient) -> None:
    actor = new_uuid7()
    token = issue_pre_tenant_dev_token(user_id=actor, secret=TEST_SECRET)
    first = client.post(
        "/api/v1/onboarding/apply",
        json={"name": "Replay Shop"},
        headers=_auth(token, "same"),
    )
    assert first.status_code == 200, first.text
    register_test_tenant(UUID(first.json()["business_id"]))
    second = client.post(
        "/api/v1/onboarding/apply",
        json={"name": "Replay Shop"},
        headers=_auth(token, "same"),
    )
    assert second.status_code == 200
    assert second.json()["business_id"] == first.json()["business_id"]
    conflict = client.post(
        "/api/v1/onboarding/apply",
        json={"name": "Other Shop"},
        headers=_auth(token, "same"),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_onboarding_apply_stays_open_while_lumo_routes_reject(client: TestClient) -> None:
    actor = new_uuid7()
    token = issue_pre_tenant_dev_token(user_id=actor, secret=TEST_SECRET)
    created = client.post(
        "/api/v1/onboarding/apply",
        json={"name": "Still Onboarding"},
        headers=_auth(token, "open-path"),
    )
    assert created.status_code == 200, created.text
    register_test_tenant(UUID(created.json()["business_id"]))
    tenant_token = created.json()["access_token"]
    blocked = client.post(
        "/api/v1/lumo/messages",
        json={"message": "una galleta"},
        headers=_auth(tenant_token, "blocked-sale"),
    )
    assert blocked.status_code == 409
    advanced = client.post(
        "/api/v1/onboarding/apply",
        json={"currency": "MXN"},
        headers=_auth(tenant_token, "still-onboarding"),
    )
    assert advanced.status_code == 200
    assert advanced.json()["next_required_field"] == "timezone"


def test_concurrent_first_bootstrap(app) -> None:
    actor = new_uuid7()
    token = issue_pre_tenant_dev_token(user_id=actor, secret=TEST_SECRET)

    def attempt(key: str, name: str):
        with TestClient(app, raise_server_exceptions=False) as local:
            return local.post(
                "/api/v1/onboarding/apply",
                json={"name": name},
                headers=_auth(token, key),
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(attempt, "race-a", "Race A")
        right = pool.submit(attempt, "race-b", "Race B")
        first = left.result(timeout=30)
        second = right.result(timeout=30)
    statuses = {first.status_code, second.status_code}
    assert 200 in statuses
    bodies = [item.json() for item in (first, second) if item.status_code == 200]
    business_ids = {item["business_id"] for item in bodies}
    assert len(business_ids) == 1
    from app.infrastructure.persistence.engine import create_engine_from_settings, create_session_factory

    engine = create_engine_from_settings(make_settings())
    session = create_session_factory(engine)()
    try:
        set_current_actor_id(session, actor)
        links = session.execute(
            text("SELECT business_id FROM identity.actor_business_links WHERE actor_id = :actor_id"),
            {"actor_id": actor},
        ).all()
        assert len(links) == 1
        business_id = links[0].business_id
        register_test_tenant(business_id)
        set_current_business_id(session, business_id)
        users = session.execute(
            text("SELECT count(*) FROM identity.users WHERE id = :actor_id"),
            {"actor_id": actor},
        ).scalar()
        memberships = session.execute(
            text("SELECT count(*) FROM identity.memberships WHERE user_id = :actor_id"),
            {"actor_id": actor},
        ).scalar()
        businesses = session.execute(
            text("SELECT count(*) FROM identity.businesses WHERE id = :business_id"),
            {"business_id": business_id},
        ).scalar()
        assert users == 1
        assert memberships == 1
        assert businesses == 1
    finally:
        session.close()
        engine.dispose()


def test_pre_tenant_cannot_sell(client: TestClient) -> None:
    token = issue_pre_tenant_dev_token(user_id=new_uuid7(), secret=TEST_SECRET)
    response = client.post(
        "/api/v1/lumo/messages",
        json={"message": "venta de galleta"},
        headers=_auth(token, "sale"),
    )
    assert response.status_code in {401, 403, 422}


def test_in_progress_sale_rejected_and_enabled_methods(client: TestClient, db_session) -> None:
    actor = new_uuid7()
    token = issue_pre_tenant_dev_token(user_id=actor, secret=TEST_SECRET)
    created = client.post(
        "/api/v1/onboarding/apply",
        json={
            "name": "Ready Shop",
            "currency": "MXN",
            "timezone": "America/Cancun",
            "payment_methods": ["cash", "transfer"],
        },
        headers=_auth(token, "bundle"),
    )
    assert created.status_code == 200, created.text
    business_id = UUID(created.json()["business_id"])
    register_test_tenant(business_id)
    assert created.json()["next_required_field"] == "ready_to_complete"
    tenant_token = created.json()["access_token"]
    sale = client.post(
        "/api/v1/lumo/messages",
        json={"message": "una galleta"},
        headers=_auth(tenant_token, "sale-early"),
    )
    assert sale.status_code == 409
    assert sale.json()["error"]["code"] == "ONBOARDING_INCOMPLETE"

    done = client.post(
        "/api/v1/onboarding/apply",
        json={"start_using_lumo": True},
        headers=_auth(tenant_token, "go"),
    )
    assert done.json()["onboarding_status"] == "completed"
    set_current_business_id(db_session, business_id)
    business = db_session.get(BusinessRow, business_id)
    assert business is not None
    assert list(business.enabled_payment_methods) == ["cash", "transfer"]


def test_carrota_stays_completed_with_null_methods(db_session) -> None:
    ensure_carrota_seed(db_session, token_secret=TEST_SECRET)
    db_session.commit()
    set_current_business_id(db_session, CARROTA_BUSINESS_ID)
    row = db_session.get(BusinessRow, CARROTA_BUSINESS_ID)
    assert row is not None
    assert row.name == "Carrota"
    assert row.currency == "MXN"
    assert row.timezone == "America/Mexico_City"
    assert row.onboarding_status == "completed"
    assert row.enabled_payment_methods is None
    assert payment_method_allowed(enabled_payment_methods=None, method="card")


def test_actor_link_primary_key_and_business_not_unique(db_session) -> None:
    actor = new_uuid7()
    business_id = new_uuid7()
    other_actor = new_uuid7()
    register_test_tenant(business_id)
    set_current_business_id(db_session, business_id)
    db_session.add(
        BusinessRow(
            id=business_id,
            name="Link Shop",
            currency="MXN",
            timezone="America/Mexico_City",
            onboarding_status="completed",
        )
    )
    db_session.flush()
    set_current_actor_id(db_session, actor)
    db_session.execute(
        text(
            "INSERT INTO identity.actor_business_links (actor_id, business_id, created_at) "
            "VALUES (:actor_id, :business_id, now())"
        ),
        {"actor_id": actor, "business_id": business_id},
    )
    db_session.flush()
    constraints = db_session.execute(
        text(
            """
            SELECT constraint_type, column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage ku
              ON tc.constraint_name = ku.constraint_name
             AND tc.table_schema = ku.table_schema
            WHERE tc.table_schema = 'identity'
              AND tc.table_name = 'actor_business_links'
              AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
            """
        )
    ).all()
    columns = {row.column_name for row in constraints}
    assert "actor_id" in columns
    assert "business_id" not in columns
    set_current_actor_id(db_session, other_actor)
    db_session.execute(
        text(
            "INSERT INTO identity.actor_business_links (actor_id, business_id, created_at) "
            "VALUES (:actor_id, :business_id, now())"
        ),
        {"actor_id": other_actor, "business_id": business_id},
    )
    db_session.flush()
    set_current_actor_id(db_session, actor)
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO identity.actor_business_links (actor_id, business_id, created_at) "
                "VALUES (:actor_id, :business_id, now())"
            ),
            {"actor_id": actor, "business_id": new_uuid7()},
        )
        db_session.flush()
    db_session.rollback()


def test_empty_method_array_rejected(db_session) -> None:
    business_id = new_uuid7()
    register_test_tenant(business_id)
    set_current_business_id(db_session, business_id)
    db_session.add(
        BusinessRow(
            id=business_id,
            name="Empty Methods",
            currency="MXN",
            timezone="America/Mexico_City",
            onboarding_status="in_progress",
            enabled_payment_methods=[],
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_cross_tenant_onboarding_hidden(client: TestClient, db_session) -> None:
    business_id, user_id, token = seed_business(db_session, name="Tenant A")
    other_id, _, other_token = seed_business(db_session, name="Tenant B")
    _ = user_id
    response = client.get("/api/v1/session", headers=_auth(other_token))
    assert response.status_code == 200
    assert response.json()["business"]["id"] == str(other_id)
    assert response.json()["business"]["id"] != str(business_id)
    denied = client.get("/api/v1/session", headers=_auth(token))
    assert denied.json()["business"]["name"] == "Tenant A"


def test_no_confirmation_policy_or_pending_payment() -> None:
    from app.policies.engine import REGISTERED_SLICE_TOOLS

    assert "confirmation.policy@2" not in REGISTERED_SLICE_TOOLS
    assert "payment.pending@1" not in REGISTERED_SLICE_TOOLS


def test_tool_registration() -> None:
    from app.agent.registrations import ONBOARDING_APPLY, ONBOARDING_CHOICE, ONBOARDING_CONFIRMATION
    from app.agent.tools import ToolRegistry
    from app.agent.generative_ui import GenerativeUIRegistry
    from app.agent.registrations import register_onboarding_tools, register_onboarding_ui

    tools = ToolRegistry()
    register_onboarding_tools(tools)
    item = tools.get("onboarding.apply@1")
    assert item is ONBOARDING_APPLY
    assert item is not None
    assert item.side_effect == "write"
    assert item.requires_idempotency is True
    ui = GenerativeUIRegistry()
    register_onboarding_ui(ui)
    assert ui.get("onboarding_choice", 1) is ONBOARDING_CHOICE
    assert ui.get("onboarding_confirmation", 1) is ONBOARDING_CONFIRMATION


def test_duplicate_create_keeps_one_business(client: TestClient, db_session) -> None:
    actor = new_uuid7()
    token = issue_pre_tenant_dev_token(user_id=actor, secret=TEST_SECRET)
    first = client.post(
        "/api/v1/onboarding/apply",
        json={"name": "Once"},
        headers=_auth(token, "once-a"),
    )
    register_test_tenant(UUID(first.json()["business_id"]))
    tenant_token = first.json()["access_token"]
    again = client.post(
        "/api/v1/onboarding/apply",
        json={"name": "Once Renamed"},
        headers=_auth(tenant_token, "once-b"),
    )
    assert again.status_code == 200
    assert again.json()["business_id"] == first.json()["business_id"]
    assert again.json()["name"] == "Once Renamed"
    set_current_actor_id(db_session, actor)
    count = db_session.execute(
        text("SELECT count(*) FROM identity.actor_business_links WHERE actor_id = :actor_id"),
        {"actor_id": actor},
    ).scalar()
    assert count == 1
    set_current_business_id(db_session, UUID(first.json()["business_id"]))
    users = db_session.execute(
        text("SELECT count(*) FROM identity.users WHERE id = :actor_id"),
        {"actor_id": actor},
    ).scalar()
    memberships = db_session.execute(
        text("SELECT count(*) FROM identity.memberships WHERE user_id = :actor_id"),
        {"actor_id": actor},
    ).scalar()
    assert users == 1
    assert memberships == 1
