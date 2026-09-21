from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.infrastructure.persistence.models import AuditEventRow, FoundationNoteRow, OutboxEventRow, ProductRow
from app.infrastructure.persistence.rls import set_current_business_id
from tests.conftest import make_settings, postgres_available, seed_business, settings_kwargs


pytestmark = pytest.mark.skipif(not postgres_available(make_settings()), reason="PostgreSQL is not available")


def _auth(token: str, **extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}", **extra}
    return headers


def test_session_is_tenant_scoped(client: TestClient, db_session) -> None:
    business_id, _user_id, token = seed_business(db_session, name="Carrota")
    response = client.get("/api/v1/session", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["business"]["id"] == str(business_id)
    assert body["business"]["name"] == "Carrota"


def test_client_supplied_business_id_is_ignored(client: TestClient, db_session) -> None:
    business_id, _, token = seed_business(db_session, name="A")
    other = UUID("00000000-0000-7000-8000-000000000099")
    response = client.post(
        "/api/v1/platform/notes",
        json={"text": "hola", "business_id": str(other)},
        headers=_auth(token, **{"Idempotency-Key": "note-1", "X-Business-Id": str(other)}),
    )
    assert response.status_code == 201
    assert response.json()["business_id"] == str(business_id)


def test_missing_idempotency_key(client: TestClient, db_session) -> None:
    _, _, token = seed_business(db_session, name="A")
    response = client.post("/api/v1/platform/notes", json={"text": "hola"}, headers=_auth(token))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_idempotent_replay_and_conflict(client: TestClient, db_session) -> None:
    _, _, token = seed_business(db_session, name="A")
    first = client.post(
        "/api/v1/platform/notes",
        json={"text": "hola"},
        headers=_auth(token, **{"Idempotency-Key": "same"}),
    )
    replay = client.post(
        "/api/v1/platform/notes",
        json={"text": "hola"},
        headers=_auth(token, **{"Idempotency-Key": "same"}),
    )
    conflict = client.post(
        "/api/v1/platform/notes",
        json={"text": "adios"},
        headers=_auth(token, **{"Idempotency-Key": "same"}),
    )
    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["id"] == first.json()["id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_rollback_leaves_no_partial_writes(client: TestClient, db_session) -> None:
    business_id, _, token = seed_business(db_session, name="A")
    response = client.post(
        "/api/v1/platform/notes",
        json={"text": "boom"},
        headers=_auth(token, **{"Idempotency-Key": "fail-1", "X-Debug-Fail-After-Write": "1"}),
    )
    assert response.status_code == 500
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    notes = db_session.scalars(
        select(FoundationNoteRow).where(FoundationNoteRow.business_id == business_id)
    ).all()
    audits = db_session.scalars(
        select(AuditEventRow).where(AuditEventRow.business_id == business_id)
    ).all()
    outbox = db_session.scalars(
        select(OutboxEventRow).where(OutboxEventRow.business_id == business_id)
    ).all()
    assert notes == []
    assert audits == []
    assert outbox == []


def test_retry_after_failure(client: TestClient, db_session) -> None:
    _, _, token = seed_business(db_session, name="A")
    failed = client.post(
        "/api/v1/platform/notes",
        json={"text": "retry-me"},
        headers=_auth(token, **{"Idempotency-Key": "retry-1", "X-Debug-Fail-After-Write": "1"}),
    )
    assert failed.status_code == 500
    retry = client.post(
        "/api/v1/platform/notes",
        json={"text": "retry-me"},
        headers=_auth(token, **{"Idempotency-Key": "retry-1"}),
    )
    assert retry.status_code == 201


def test_audit_and_outbox_commit_with_mutation(client: TestClient, db_session) -> None:
    business_id, _, token = seed_business(db_session, name="A")
    created = client.post(
        "/api/v1/platform/notes",
        json={"text": "audit me"},
        headers=_auth(token, **{"Idempotency-Key": "audit-1"}),
    )
    assert created.status_code == 201
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    audits = db_session.scalars(
        select(AuditEventRow).where(AuditEventRow.business_id == business_id)
    ).all()
    outbox = db_session.scalars(
        select(OutboxEventRow).where(OutboxEventRow.business_id == business_id)
    ).all()
    assert len(audits) == 1
    assert len(outbox) == 1


def test_audit_is_append_only(client: TestClient, db_session) -> None:
    _, _, token = seed_business(db_session, name="A")
    response = client.delete("/api/v1/audit/events/00000000-0000-7000-8000-000000000001", headers=_auth(token))
    assert response.status_code == 422
    assert "append-only" in response.json()["error"]["message"]


def test_cross_tenant_note_is_hidden(client: TestClient, db_session) -> None:
    _, _, token_a = seed_business(db_session, name="A")
    business_b, _, token_b = seed_business(db_session, name="B")
    created = client.post(
        "/api/v1/platform/notes",
        json={"text": "secret"},
        headers=_auth(token_b, **{"Idempotency-Key": "b-1"}),
    )
    note_id = created.json()["id"]
    hidden = client.get(f"/api/v1/platform/notes/{note_id}", headers=_auth(token_a))
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "TENANT_SCOPE_VIOLATION"


def test_api_session_uses_lumo_app_without_rls_bypass(app, db_session) -> None:
    with app.state.engine.connect() as connection:
        current_user = connection.exec_driver_sql("SELECT current_user").scalar_one()
        privileges = connection.exec_driver_sql(
            """
            SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
            FROM pg_roles
            WHERE rolname = current_user
            """
        ).one()
    assert current_user == "lumo_app"
    assert privileges.rolsuper is False
    assert privileges.rolcreatedb is False
    assert privileges.rolcreaterole is False
    assert privileges.rolbypassrls is False
    session_user = db_session.execute(text("SELECT current_user")).scalar_one()
    assert session_user == "lumo_app"


def test_rls_hides_other_tenant_rows(db_session) -> None:
    business_a, _, _ = seed_business(db_session, name="A-rls")
    business_b, user_b, _ = seed_business(db_session, name="B-rls")
    set_current_business_id(db_session, business_b)
    db_session.add(FoundationNoteRow(business_id=business_b, actor_id=user_b, text="only B"))
    db_session.commit()
    set_current_business_id(db_session, business_a)
    db_session.expire_all()
    rows = db_session.scalars(select(FoundationNoteRow)).all()
    assert all(row.business_id == business_a for row in rows)
    assert not any(row.business_id == business_b for row in rows)


def test_catalog_and_sales_schemas_are_present(db_session) -> None:
    names = db_session.scalars(text("SELECT nspname FROM pg_namespace")).all()
    assert "catalog" in names
    assert "sales" in names
    for schema in ("operations", "workflow", "memory"):
        assert schema not in names
    tables = db_session.scalars(
        text(
            """
            SELECT table_schema || '.' || table_name
            FROM information_schema.tables
            WHERE table_schema IN ('catalog', 'sales')
            """
        )
    ).all()
    expected = {
        "catalog.products",
        "catalog.product_aliases",
        "sales.sale_sessions",
        "sales.sale_items",
        "sales.payments",
    }
    assert expected.issubset(set(tables))
    assert "sales.sales" not in tables
    assert "sales.sale_lines" not in tables


def test_dev_token_rejected_in_production(db_session) -> None:
    from app.bootstrap.app import create_app
    from app.bootstrap.settings import Settings

    _, _, token = seed_business(db_session, name="ProdCheck")
    settings = Settings.model_validate(
        settings_kwargs(
            APP_ENV="production",
            DATABASE_URL=make_settings().database_url,
            DATABASE_ADMIN_URL=make_settings().database_admin_url,
        )
    )
    prod_client = TestClient(create_app(settings), raise_server_exceptions=False)
    response = prod_client.get("/api/v1/session", headers=_auth(token))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    token_response = prod_client.get("/api/v1/dev/carrota-token")
    assert token_response.status_code == 403
    assert token_response.json()["error"]["code"] == "FORBIDDEN"


def test_debug_fail_after_write_only_in_local_and_test() -> None:
    from app.bootstrap.settings import Settings

    test_settings = Settings.model_validate(settings_kwargs())
    prod_settings = Settings.model_validate(
        settings_kwargs(
            APP_ENV="production",
            DATABASE_URL=make_settings().database_url,
            DATABASE_ADMIN_URL=make_settings().database_admin_url,
        )
    )
    assert test_settings.allows_debug_fail_after_write is True
    assert test_settings.allows_dev_tokens is True
    assert prod_settings.allows_debug_fail_after_write is False
    assert prod_settings.allows_dev_tokens is False


def test_unscoped_catalog_select_is_empty_despite_seed(db_session) -> None:
    from app.infrastructure.persistence.engine import create_engine_from_settings, create_session_factory
    from app.infrastructure.persistence.seed import ensure_carrota_seed

    ensure_carrota_seed(db_session, token_secret="test-dev-secret-16-chars-minimum")
    db_session.commit()
    engine = create_engine_from_settings(make_settings())
    other = create_session_factory(engine)()
    try:
        count = other.scalar(select(func.count()).select_from(ProductRow))
        assert count == 0
    finally:
        other.close()
        engine.dispose()
