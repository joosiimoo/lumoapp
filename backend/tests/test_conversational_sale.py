from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.agent.registrations import register_conversational_sale_tools, register_sale_item_added_ui, register_sale_summary_ui
from app.agent.generative_ui import GenerativeUIComposer, GenerativeUIContract, GenerativeUIRegistry
from app.agent.tools import ToolRegistry
from app.domain.catalog import ProductMatch
from app.domain.shared.ids import new_uuid7
from app.infrastructure.persistence.catalog_sales import CatalogRepository
from app.infrastructure.persistence.models import (
    AuditEventRow,
    IdempotencyRecordRow,
    OutboxEventRow,
    ProductRow,
    SaleItemRow,
    SaleSessionRow,
)
from app.infrastructure.persistence.rls import set_current_business_id
from app.infrastructure.persistence.seed import (
    GALLETA_A_NAME,
    TOMATE_NAME,
    ZANAHORIA_NAME,
    ensure_carrota_seed,
)
from tests.conftest import make_settings, postgres_available, seed_business
from tests.sale_cleanup import (
    SALE_AUDIT_ACTIONS,
    SALE_MESSAGE_OPERATION,
    SALE_OUTBOX_EVENT,
    clear_tenant_sale_mutations,
    sale_integrity_orphans,
)


pytestmark = pytest.mark.skipif(not postgres_available(make_settings()), reason="PostgreSQL is not available")


def _auth(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def _post(client: TestClient, token: str, message: str, key: str, conversation_id: str, **extra: str):
    return client.post(
        "/api/v1/lumo/messages",
        json={"message": message, "conversation_id": conversation_id},
        headers=_auth(token, **{"Idempotency-Key": key, **extra}),
    )


def _sales_for(db_session, business_id):
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    sessions = db_session.scalars(select(SaleSessionRow).where(SaleSessionRow.business_id == business_id)).all()
    items = db_session.scalars(select(SaleItemRow).where(SaleItemRow.business_id == business_id)).all()
    return sessions, items


def _seed_carrota(db_session):
    tenant, token = ensure_carrota_seed(db_session, token_secret="test-dev-secret-16-chars-minimum")
    db_session.commit()
    clear_tenant_sale_mutations(db_session, tenant.business_id)
    return tenant, token


def test_registered_tools_do_not_include_commit() -> None:
    registry = ToolRegistry()
    register_conversational_sale_tools(registry)
    assert registry.is_registered("catalog.resolve_product@1")
    assert registry.is_registered("sale.start@1")
    assert registry.is_registered("sale.add_item@1")
    assert registry.is_registered("sale.totalize@1")
    assert registry.get("sale.commit@1") is None


def test_golden_path_900gr_zanahoria(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    conversation_id = "conv-golden"
    response = _post(client, token, "900gr zanahoria", "golden-1", conversation_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ui"]
    card = body["ui"][0]
    assert card["component"] == "sale_item_added"
    assert card["version"] == 1
    assert card["data"]["product_name"] == ZANAHORIA_NAME
    assert card["data"]["quantity_normalized"] == "0.900"
    assert card["data"]["unit_normalized"] == "kilogram"
    assert card["data"]["unit_price"]["amount"] == "25.00"
    assert card["data"]["line_total"]["amount"] == "22.50"
    assert card["data"]["session_item_count"] == 1
    assert card["data"]["session_total"]["amount"] == "22.50"
    sessions, items = _sales_for(db_session, tenant.business_id)
    audits = db_session.scalars(select(AuditEventRow).where(AuditEventRow.business_id == tenant.business_id)).all()
    assert len(sessions) == 1
    assert sessions[0].status == "open"
    assert sessions[0].conversation_id == conversation_id
    assert len(items) == 1
    assert str(items[0].line_total) in {"22.50", "22.500000"}
    assert any(event.route_or_tool == "sale.start@1" for event in audits)
    assert any(event.route_or_tool == "sale.add_item@1" for event in audits)
    assert sale_integrity_orphans(db_session, tenant.business_id) == []


def test_message_idempotent_replay(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    conversation_id = "conv-replay"
    first = _post(client, token, "900gr zanahoria", "replay-sale", conversation_id)
    replay = _post(client, token, "900gr zanahoria", "replay-sale", conversation_id)
    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["ui"][0]["data"]["sale_item_id"] == first.json()["ui"][0]["data"]["sale_item_id"]
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 1
    assert sessions[0].conversation_id == conversation_id
    assert len(items) == 1


def test_new_session_rolled_back_with_failed_add_item(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    response = _post(
        client,
        token,
        "900gr zanahoria",
        "fail-new",
        "conv-fail-new",
        **{"X-Debug-Fail-After-Write": "1"},
    )
    assert response.status_code == 500
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert sessions == []
    assert items == []
    failed_audits = db_session.scalars(
        select(AuditEventRow).where(
            AuditEventRow.business_id == tenant.business_id,
            AuditEventRow.idempotency_key == "fail-new",
        )
    ).all()
    assert failed_audits == []
    assert sale_integrity_orphans(db_session, tenant.business_id) == []
    retry = _post(client, token, "900gr zanahoria", "fail-new", "conv-fail-new")
    assert retry.status_code == 200


def test_reused_session_unchanged_after_failed_add_item(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    conversation_id = "conv-reuse-fail"
    first = _post(client, token, "900gr zanahoria", "reuse-1", conversation_id)
    assert first.status_code == 200
    session_id = first.json()["ui"][0]["data"]["sale_session_id"]
    failed = _post(
        client,
        token,
        "900 g zanahoria",
        "reuse-2",
        conversation_id,
        **{"X-Debug-Fail-After-Write": "1"},
    )
    assert failed.status_code == 500
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 1
    assert str(sessions[0].id) == session_id
    assert sessions[0].conversation_id == conversation_id
    assert len(items) == 1
    assert sale_integrity_orphans(db_session, tenant.business_id) == []


def test_missing_unit_and_unknown_product_do_not_persist(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    missing = _post(client, token, "900 zanahoria", "no-unit", "conv-no-unit")
    unknown = _post(client, token, "900gr papa", "unknown", "conv-unknown")
    assert missing.status_code == 200
    assert unknown.status_code == 200
    assert missing.json()["ui"] == []
    assert unknown.json()["ui"] == []
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert sessions == []
    assert items == []


def test_model_hinted_total_is_ignored(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    response = _post(client, token, "900gr zanahoria", "hint-99", "conv-hint")
    assert response.json()["ui"][0]["data"]["line_total"]["amount"] == "22.50"


def test_cross_tenant_cannot_use_carrota_catalog(client: TestClient, db_session) -> None:
    ensure_carrota_seed(db_session, token_secret="test-dev-secret-16-chars-minimum")
    db_session.commit()
    _other_id, _user, token_b = seed_business(db_session, name="Other")
    response = _post(client, token_b, "900gr zanahoria", "other-1", "conv-other")
    assert response.status_code == 200
    assert response.json()["ui"] == []


def test_ambiguous_product_does_not_persist(client: TestClient, db_session) -> None:
    from decimal import Decimal

    from app.domain.catalog import PricingType, Product, ProductStatus, SaleUnit, normalize_product_name
    from app.domain.shared.money import Money
    from app.domain.shared.tenant import TenantContext

    business_id, user_id, token = seed_business(db_session, name="AmbiguousMart")
    tenant = TenantContext(business_id=business_id, actor_id=user_id)
    catalog = CatalogRepository(db_session)
    first = catalog.add(
        tenant=tenant,
        product=Product(
            id=new_uuid7(),
            business_id=business_id,
            name="Zanahoria A",
            normalized_name=normalize_product_name("Zanahoria A"),
            sale_unit=SaleUnit.KILOGRAM,
            pricing_type=PricingType.PER_KILOGRAM,
            current_price=Money(Decimal("25.00"), "MXN"),
            status=ProductStatus.ACTIVE,
        ),
    )
    second = catalog.add(
        tenant=tenant,
        product=Product(
            id=new_uuid7(),
            business_id=business_id,
            name="Zanahoria B",
            normalized_name=normalize_product_name("Zanahoria B"),
            sale_unit=SaleUnit.KILOGRAM,
            pricing_type=PricingType.PER_KILOGRAM,
            current_price=Money(Decimal("25.00"), "MXN"),
            status=ProductStatus.ACTIVE,
        ),
    )
    catalog.add_alias(tenant=tenant, product_id=first.id, alias="zanahoria", normalized_alias="zanahoria")
    catalog.add_alias(tenant=tenant, product_id=second.id, alias="zanahoria", normalized_alias="zanahoria")
    db_session.commit()
    response = _post(client, token, "900gr zanahoria", "amb-1", "conv-amb")
    assert response.status_code == 200
    assert response.json()["ui"] == []
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    assert db_session.scalars(select(SaleSessionRow).where(SaleSessionRow.business_id == business_id)).all() == []


def test_two_turn_missing_unit_then_gr_completes_add(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    conversation_id = "conv-clarify"
    first = _post(client, token, "900 zanahoria", "clarify-1", conversation_id)
    assert first.status_code == 200
    assert first.json()["ui"] == []
    assert "unidad" in first.json()["text"].lower()
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert sessions == []
    assert items == []
    second = _post(client, token, "gr", "clarify-2", conversation_id)
    assert second.status_code == 200, second.text
    card = second.json()["ui"][0]
    assert card["component"] == "sale_item_added"
    assert card["data"]["quantity_normalized"] == "0.900"
    assert card["data"]["unit_normalized"] == "kilogram"
    assert card["data"]["line_total"]["amount"] == "22.50"
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 1
    assert sessions[0].conversation_id == conversation_id
    assert len(items) == 1


def test_unit_only_without_pending_does_not_persist(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    response = _post(client, token, "gr", "orphan-unit", "conv-orphan-unit")
    assert response.status_code == 200
    assert response.json()["ui"] == []
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert sessions == []
    assert items == []


def test_same_conversation_id_reuses_one_session(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    conversation_id = "conv-same"
    first = _post(client, token, "900gr zanahoria", "same-1", conversation_id)
    second = _post(client, token, "900gr zanahoria", "same-2", conversation_id)
    assert first.status_code == 200
    assert second.status_code == 200
    first_session = first.json()["ui"][0]["data"]["sale_session_id"]
    second_session = second.json()["ui"][0]["data"]["sale_session_id"]
    assert first_session == second_session
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 1
    assert sessions[0].conversation_id == conversation_id
    assert str(sessions[0].id) == first_session
    assert len(items) == 2
    assert {str(item.line_total) for item in items} == {"22.50"}


def test_different_conversation_ids_create_different_sessions(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    first = _post(client, token, "900gr zanahoria", "diff-1", "conv-a")
    second = _post(client, token, "900gr zanahoria", "diff-2", "conv-b")
    assert first.status_code == 200
    assert second.status_code == 200
    first_session = first.json()["ui"][0]["data"]["sale_session_id"]
    second_session = second.json()["ui"][0]["data"]["sale_session_id"]
    assert first_session != second_session
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 2
    assert {session.conversation_id for session in sessions} == {"conv-a", "conv-b"}
    assert len(items) == 2
    items_by_session = {str(item.sale_session_id): item for item in items}
    assert set(items_by_session) == {first_session, second_session}


def test_message_without_conversation_id_does_not_reuse_named_session(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    named = _post(client, token, "900gr zanahoria", "named-1", "conv-named")
    assert named.status_code == 200
    named_session = named.json()["ui"][0]["data"]["sale_session_id"]
    unnamed = client.post(
        "/api/v1/lumo/messages",
        json={"message": "900gr zanahoria"},
        headers=_auth(token, **{"Idempotency-Key": "unnamed-1"}),
    )
    assert unnamed.status_code == 200
    unnamed_session = unnamed.json()["ui"][0]["data"]["sale_session_id"]
    assert unnamed_session != named_session
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 2
    assert {session.conversation_id for session in sessions} == {"conv-named", None}
    assert len(items) == 2


def test_committed_sale_integrity_rows_reference_live_ids(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    response = _post(client, token, "900gr zanahoria", "integrity-live", "conv-integrity")
    assert response.status_code == 200
    payload = response.json()["ui"][0]["data"]
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    audits = db_session.scalars(
        select(AuditEventRow).where(
            AuditEventRow.business_id == tenant.business_id,
            AuditEventRow.action.in_(SALE_AUDIT_ACTIONS),
        )
    ).all()
    outbox = db_session.scalars(
        select(OutboxEventRow).where(
            OutboxEventRow.business_id == tenant.business_id,
            OutboxEventRow.event_type == SALE_OUTBOX_EVENT,
        )
    ).all()
    idempotency = db_session.scalars(
        select(IdempotencyRecordRow).where(
            IdempotencyRecordRow.business_id == tenant.business_id,
            IdempotencyRecordRow.operation_type == SALE_MESSAGE_OPERATION,
        )
    ).all()
    assert len(audits) == 2
    assert len(outbox) == 1
    assert len(idempotency) == 1
    assert outbox[0].payload["sale_session_id"] == payload["sale_session_id"]
    assert outbox[0].payload["sale_item_id"] == payload["sale_item_id"]
    assert sale_integrity_orphans(db_session, tenant.business_id) == []


def test_sale_cleanup_does_not_leave_orphan_integrity(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    response = _post(client, token, "900gr zanahoria", "cleanup-1", "conv-cleanup")
    assert response.status_code == 200
    clear_tenant_sale_mutations(db_session, tenant.business_id)
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert sessions == []
    assert items == []
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    assert (
        db_session.scalars(
            select(AuditEventRow).where(
                AuditEventRow.business_id == tenant.business_id,
                AuditEventRow.action.in_(SALE_AUDIT_ACTIONS),
            )
        ).all()
        == []
    )
    assert (
        db_session.scalars(
            select(OutboxEventRow).where(
                OutboxEventRow.business_id == tenant.business_id,
                OutboxEventRow.event_type == SALE_OUTBOX_EVENT,
            )
        ).all()
        == []
    )
    assert (
        db_session.scalars(
            select(IdempotencyRecordRow).where(
                IdempotencyRecordRow.business_id == tenant.business_id,
                IdempotencyRecordRow.operation_type == SALE_MESSAGE_OPERATION,
            )
        ).all()
        == []
    )
    assert sale_integrity_orphans(db_session, tenant.business_id) == []


def test_piecemeal_sales_delete_is_detected_and_official_cleanup_heals(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    response = _post(client, token, "900gr zanahoria", "live-clarify-2-shape", "conv-orphan-shape")
    assert response.status_code == 200
    set_current_business_id(db_session, tenant.business_id)
    db_session.execute(SaleItemRow.__table__.delete().where(SaleItemRow.business_id == tenant.business_id))
    db_session.execute(SaleSessionRow.__table__.delete().where(SaleSessionRow.business_id == tenant.business_id))
    db_session.execute(
        IdempotencyRecordRow.__table__.delete().where(
            IdempotencyRecordRow.business_id == tenant.business_id,
            IdempotencyRecordRow.operation_type == SALE_MESSAGE_OPERATION,
        )
    )
    db_session.commit()
    orphans = sale_integrity_orphans(db_session, tenant.business_id)
    assert orphans, "piecemeal sales/idempotency DELETE must leave audit/outbox orphans"
    clear_tenant_sale_mutations(db_session, tenant.business_id)
    assert sale_integrity_orphans(db_session, tenant.business_id) == []


def _totalize_outbox(db_session, business_id):
    return db_session.scalars(
        select(OutboxEventRow).where(
            OutboxEventRow.business_id == business_id,
            OutboxEventRow.event_type == "sale.ready_to_charge",
        )
    ).all()


def _totalize_keys(db_session, business_id):
    return db_session.scalars(
        select(IdempotencyRecordRow).where(
            IdempotencyRecordRow.business_id == business_id,
            IdempotencyRecordRow.operation_type == "lumo.message.totalize_sale",
        )
    ).all()


def _totalize_audits(db_session, business_id):
    return db_session.scalars(
        select(AuditEventRow).where(
            AuditEventRow.business_id == business_id,
            AuditEventRow.action == "sale.totalize@1",
        )
    ).all()


def test_seed_resolves_representative_catalog(db_session) -> None:
    tenant, _token = _seed_carrota(db_session)
    catalog = CatalogRepository(db_session)
    tomate = catalog.resolve(tenant=tenant, query="tomate")
    galleta = catalog.resolve(tenant=tenant, query="galleta a")
    galletas = catalog.resolve(tenant=tenant, query="galletas a")
    papa = catalog.resolve(tenant=tenant, query="papa")
    assert tomate.match is ProductMatch.UNIQUE
    assert tomate.product is not None and tomate.product.name == TOMATE_NAME
    assert galleta.match is ProductMatch.UNIQUE
    assert galleta.product is not None and galleta.product.name == GALLETA_A_NAME
    assert galletas.match is ProductMatch.UNIQUE
    assert galletas.product is not None and galletas.product.id == galleta.product.id
    assert papa.match is ProductMatch.NONE
    names = {
        row.name
        for row in db_session.scalars(select(ProductRow).where(ProductRow.business_id == tenant.business_id)).all()
    }
    assert names == {ZANAHORIA_NAME, TOMATE_NAME, GALLETA_A_NAME}


def test_active_index_preserves_coalesce_and_widens_status(db_session) -> None:
    definition = db_session.execute(
        text(
            """
            SELECT indexdef FROM pg_indexes
            WHERE schemaname = 'sales' AND indexname = 'uq_sale_sessions_active_context'
            """
        )
    ).scalar_one()
    assert "COALESCE(conversation_id" in definition
    assert "open" in definition
    assert "ready_to_charge" in definition
    column = db_session.execute(
        text(
            """
            SELECT data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'sales' AND table_name = 'sale_sessions' AND column_name = 'conversation_id'
            """
        )
    ).one()
    assert column.data_type == "character varying"
    assert column.character_maximum_length == 128
    columns = db_session.scalars(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'sales' AND table_name = 'sale_sessions'
            """
        )
    ).all()
    assert "total" not in columns


def test_multi_item_then_galleta_a(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    conversation_id = "conv-multi"
    first = _post(client, token, "900gr zanahoria", "multi-1", conversation_id)
    second = _post(client, token, "500gr tomate", "multi-2", conversation_id)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["ui"][0]["data"]["sale_session_id"] == second.json()["ui"][0]["data"]["sale_session_id"]
    assert second.json()["ui"][0]["data"]["session_item_count"] == 2
    assert second.json()["ui"][0]["data"]["session_total"]["amount"] == "32.50"
    third = _post(client, token, "2 galletas A", "multi-3", conversation_id)
    assert third.status_code == 200, third.text
    card = third.json()["ui"][0]
    assert card["data"]["product_name"] == GALLETA_A_NAME
    assert card["data"]["unit_normalized"] == "unit"
    assert card["data"]["line_total"]["amount"] == "24.00"
    assert card["data"]["session_item_count"] == 3
    assert card["data"]["session_total"]["amount"] == "56.50"
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 1
    assert sessions[0].status == "open"
    assert len(items) == 3


def test_kilogram_missing_unit_inside_active_sale(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    conversation_id = "conv-tomate-clarify"
    first = _post(client, token, "900gr zanahoria", "tc-1", conversation_id)
    missing = _post(client, token, "500 tomate", "tc-2", conversation_id)
    assert first.status_code == 200
    assert missing.status_code == 200
    assert missing.json()["ui"] == []
    assert "unidad" in missing.json()["text"].lower()
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 1
    assert len(items) == 1
    follow = _post(client, token, "gr", "tc-3", conversation_id)
    assert follow.status_code == 200, follow.text
    card = follow.json()["ui"][0]
    assert card["data"]["product_name"] == TOMATE_NAME
    assert card["data"]["quantity_normalized"] == "0.500"
    assert card["data"]["line_total"]["amount"] == "10.00"
    assert card["data"]["session_item_count"] == 2
    assert card["data"]["session_total"]["amount"] == "32.50"
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 1
    assert len(items) == 2


def test_count_product_without_unit_completes_and_kilogram_still_asks(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    galleta = _post(client, token, "2 galletas A", "unit-galleta", "conv-unit-galleta")
    assert galleta.status_code == 200, galleta.text
    assert galleta.json()["ui"][0]["data"]["line_total"]["amount"] == "24.00"
    ask = _post(client, token, "2 zanahoria", "unit-zana", "conv-unit-zana")
    assert ask.status_code == 200
    assert ask.json()["ui"] == []
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert all(session.conversation_id != "conv-unit-zana" for session in sessions)
    assert len(items) == 1


def test_totalize_transition_replay_and_different_key_read_back(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    conversation_id = "conv-totalize"
    _post(client, token, "900gr zanahoria", "tot-1", conversation_id)
    _post(client, token, "500gr tomate", "tot-2", conversation_id)
    first = _post(client, token, "totalizar", "tot-key", conversation_id)
    assert first.status_code == 200, first.text
    card = first.json()["ui"][0]
    assert card["component"] == "sale_summary"
    assert card["version"] == 1
    assert card["data"]["status"] == "ready_to_charge"
    assert card["data"]["item_count"] == 2
    assert card["data"]["total"]["amount"] == "32.50"
    assert card["data"]["subtotal"]["amount"] == "32.50"
    names = {item["product_name"] for item in card["data"]["items"]}
    assert names == {ZANAHORIA_NAME, TOMATE_NAME}
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert sessions[0].status == "ready_to_charge"
    item_sum = sum(Decimal(str(item.line_total)) for item in items)
    assert card["data"]["total"]["amount"] == f"{item_sum.quantize(Decimal('0.01')):.2f}"
    assert len(_totalize_outbox(db_session, tenant.business_id)) == 1
    assert len(_totalize_keys(db_session, tenant.business_id)) == 1
    assert len(_totalize_audits(db_session, tenant.business_id)) == 1

    replay = _post(client, token, "totalizar", "tot-key", conversation_id)
    assert replay.status_code == 200
    assert replay.json()["ui"][0]["data"]["sale_session_id"] == card["data"]["sale_session_id"]
    assert replay.json()["ui"][0]["data"]["total"]["amount"] == "32.50"
    assert len(_totalize_outbox(db_session, tenant.business_id)) == 1
    assert len(_totalize_keys(db_session, tenant.business_id)) == 1
    assert len(_totalize_audits(db_session, tenant.business_id)) == 1

    other = _post(client, token, "totalizar", "tot-other-key", conversation_id)
    assert other.status_code == 200
    assert other.json()["ui"][0]["component"] == "sale_summary"
    assert other.json()["ui"][0]["data"]["total"]["amount"] == "32.50"
    assert len(_totalize_outbox(db_session, tenant.business_id)) == 1
    assert len(_totalize_keys(db_session, tenant.business_id)) == 1
    assert len(_totalize_audits(db_session, tenant.business_id)) == 1
    keys = {row.key for row in _totalize_keys(db_session, tenant.business_id)}
    assert keys == {"tot-key"}


def test_empty_totalize_does_not_mutate(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    response = _post(client, token, "totalizar", "empty-tot", "conv-empty-tot")
    assert response.status_code == 200
    assert response.json()["ui"] == []
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert sessions == []
    assert items == []
    assert _totalize_outbox(db_session, tenant.business_id) == []
    assert _totalize_keys(db_session, tenant.business_id) == []


def test_add_after_ready_rejected_and_new_conversation_isolated(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    conversation_id = "conv-ready"
    _post(client, token, "900gr zanahoria", "ready-1", conversation_id)
    totalize = _post(client, token, "totalizar", "ready-tot", conversation_id)
    assert totalize.status_code == 200
    denied = _post(client, token, "900gr zanahoria", "ready-add", conversation_id)
    assert denied.status_code == 200
    assert denied.json()["ui"] == []
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 1
    assert sessions[0].status == "ready_to_charge"
    assert len(items) == 1
    other = _post(client, token, "900gr zanahoria", "ready-new", "conv-ready-new")
    assert other.status_code == 200
    assert other.json()["ui"][0]["component"] == "sale_item_added"
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 2
    by_conv = {session.conversation_id: session for session in sessions}
    assert by_conv[conversation_id].status == "ready_to_charge"
    assert by_conv["conv-ready-new"].status == "open"
    assert other.json()["ui"][0]["data"]["sale_session_id"] != totalize.json()["ui"][0]["data"]["sale_session_id"]


def test_unknown_papa_does_not_damage_open_sale(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    conversation_id = "conv-papa"
    first = _post(client, token, "900gr zanahoria", "papa-1", conversation_id)
    unknown = _post(client, token, "900gr papa", "papa-2", conversation_id)
    assert first.status_code == 200
    assert unknown.status_code == 200
    assert unknown.json()["ui"] == []
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 1
    assert sessions[0].status == "open"
    assert len(items) == 1
    assert first.json()["ui"][0]["data"]["session_total"]["amount"] == "22.50"


def test_totalize_forced_failure_rolls_back_integrity(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    conversation_id = "conv-fail-tot"
    _post(client, token, "900gr zanahoria", "fail-tot-1", conversation_id)
    failed = _post(
        client,
        token,
        "totalizar",
        "fail-tot-key",
        conversation_id,
        **{"X-Debug-Fail-After-Write": "1"},
    )
    assert failed.status_code == 500
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 1
    assert sessions[0].status == "open"
    assert len(items) == 1
    assert _totalize_outbox(db_session, tenant.business_id) == []
    assert _totalize_keys(db_session, tenant.business_id) == []
    assert _totalize_audits(db_session, tenant.business_id) == []
    assert sale_integrity_orphans(db_session, tenant.business_id) == []
    retry = _post(client, token, "totalizar", "fail-tot-key", conversation_id)
    assert retry.status_code == 200
    sessions, _items = _sales_for(db_session, tenant.business_id)
    assert sessions[0].status == "ready_to_charge"


def test_cross_business_cannot_see_carrota_sale(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    _post(client, token, "900gr zanahoria", "rls-sale", "conv-rls-sale")
    business_b, _user_b, token_b = seed_business(db_session, name="OtherSale")
    hidden = _post(client, token_b, "900gr zanahoria", "rls-other", "conv-rls-other")
    assert hidden.status_code == 200
    assert hidden.json()["ui"] == []
    set_current_business_id(db_session, business_b)
    db_session.expire_all()
    seen = db_session.scalars(select(SaleSessionRow)).all()
    assert all(row.business_id == business_b for row in seen)
    assert not any(row.business_id == tenant.business_id for row in seen)


def test_concurrent_add_item_vs_totalize(app, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    conversation_id = "conv-race"
    with TestClient(app, raise_server_exceptions=False) as setup:
        seeded = _post(setup, token, "900gr zanahoria", "race-setup", conversation_id)
    assert seeded.status_code == 200

    def add_item():
        with TestClient(app, raise_server_exceptions=False) as client:
            return _post(client, token, "500gr tomate", "race-add", conversation_id)

    def totalize():
        with TestClient(app, raise_server_exceptions=False) as client:
            return _post(client, token, "totalizar", "race-total", conversation_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        add_future = pool.submit(add_item)
        total_future = pool.submit(totalize)
        add_resp = add_future.result(timeout=30)
        tot_resp = total_future.result(timeout=30)

    assert tot_resp.status_code == 200, tot_resp.text
    assert add_resp.status_code == 200, add_resp.text
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 1
    assert sessions[0].status == "ready_to_charge"
    summary = tot_resp.json()["ui"][0]
    assert summary["component"] == "sale_summary"
    item_sum = sum(Decimal(str(item.line_total)) for item in items)
    assert summary["data"]["total"]["amount"] == f"{item_sum.quantize(Decimal('0.01')):.2f}"
    assert len(items) in {1, 2}
    if add_resp.json().get("ui"):
        assert add_resp.json()["ui"][0]["component"] == "sale_item_added"
        assert len(items) == 2
    else:
        assert len(items) == 1
    assert all(item.sale_session_id == sessions[0].id for item in items)


def test_sale_summary_and_confirmed_card_registry() -> None:
    registry = GenerativeUIRegistry()
    register_sale_item_added_ui(registry)
    register_sale_summary_ui(registry)
    composer = GenerativeUIComposer(registry)
    assert registry.get("sale_summary", 1) is not None
    try:
        composer.compose(GenerativeUIContract(component="sale_ready_to_charge", version=1, fallback_text="no"))
        raise AssertionError("expected unregistered component to fail")
    except Exception as exc:
        assert "unregistered" in str(exc).lower()
    try:
        composer.compose(GenerativeUIContract(component="sale_confirmed_card", version=1, fallback_text="no"))
        raise AssertionError("expected unregistered component to fail")
    except Exception as exc:
        assert "unregistered" in str(exc).lower()
