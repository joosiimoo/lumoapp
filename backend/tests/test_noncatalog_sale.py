from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.application.workflows.add_catalog_sale_item import AddCatalogSaleItem
from app.domain.catalog import PricingType, ProductStatus, SaleUnit, normalize_product_name
from app.domain.catalog.product import Product as CatalogProduct
from app.domain.shared.ids import new_uuid7
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.audit import SqlAlchemyAuditService
from app.infrastructure.persistence.catalog_sales import CatalogRepository, SalesRepository
from app.infrastructure.persistence.idempotency import SqlAlchemyIdempotencyService
from app.infrastructure.persistence.models import (
    AuditEventRow,
    IdempotencyRecordRow,
    OutboxEventRow,
    ProductRow,
    SaleItemRow,
)
from app.infrastructure.persistence.outbox import SqlAlchemyOutbox
from app.infrastructure.persistence.rls import set_current_business_id
from app.infrastructure.persistence.seed import TOMATE_NAME, ZANAHORIA_NAME
from tests.test_conversational_sale import _post, _sales_for, _seed_carrota
from tests.sale_cleanup import clear_tenant_sale_mutations
from tests.test_daily_close_confirmation import _confirm, _day, _snapshots, _token_of
from tests.test_daily_close_preparation import _post as _close_post


def _products(db_session, business_id) -> int:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return db_session.scalar(select(func.count()).select_from(ProductRow).where(ProductRow.business_id == business_id))


def _workflow(db_session) -> AddCatalogSaleItem:
    from app.infrastructure.persistence.repositories import IdentityRepository

    return AddCatalogSaleItem(
        catalog=CatalogRepository(db_session),
        sales=SalesRepository(db_session),
        identities=IdentityRepository(db_session),
        audit=SqlAlchemyAuditService(db_session),
        idempotency=SqlAlchemyIdempotencyService(db_session),
        outbox=SqlAlchemyOutbox(db_session),
    )


def test_catalog_price_guard_and_existing_path(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    carrot = _post(client, token, "900gr zanahoria", "cat-z", "conv-cat")
    assert carrot.status_code == 200, carrot.text
    assert carrot.json()["ui"][0]["data"]["product_name"] == ZANAHORIA_NAME
    assert carrot.json()["ui"][0]["data"]["line_total"]["amount"] == "22.50"
    equal = _post(client, token, "900gr tomate a 20", "cat-eq", "conv-cat-eq")
    assert equal.json()["ui"][0]["data"]["product_name"] == TOMATE_NAME
    assert equal.json()["ui"][0]["data"]["unit_price"]["amount"] == "20.00"
    assert equal.json()["ui"][0]["data"]["line_total"]["amount"] == "18.00"
    before = _products(db_session, tenant.business_id)
    mismatch = _post(client, token, "900gr tomate a 30", "cat-mis", "conv-cat-mis")
    assert mismatch.json()["ui"] == []
    assert "Tomate está registrado a $20.00 por kg" in mismatch.json()["text"]
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len(sessions) == 2
    assert _products(db_session, tenant.business_id) == before
    assert not any(item.product_name_snapshot == "tomate" for item in items)
    set_current_business_id(db_session, tenant.business_id)
    keys = db_session.scalars(
        select(IdempotencyRecordRow).where(IdempotencyRecordRow.key == "cat-mis")
    ).all()
    assert keys == []


def test_free_concept_packages_units_and_follow_ups(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    before = _products(db_session, tenant.business_id)
    bags = _post(client, token, "2 bolsas de hielo a 18", "bags", "conv-bags")
    assert bags.status_code == 200, bags.text
    card = bags.json()["ui"][0]
    assert card["version"] == 1
    assert card["data"]["product_name"] == "bolsas de hielo"
    assert card["data"]["line_total"]["amount"] == "36.00"
    assert card["actions"] == []
    assert "Concepto libre" not in bags.json()["text"]
    assert bags.json()["text"] == "Agregué 2 bolsas de hielo · $36.00"
    _, items = _sales_for(db_session, tenant.business_id)
    assert items[0].source_type == "free_concept"
    assert items[0].product_id is None
    assert items[0].unit_normalized == "package"
    assert _products(db_session, tenant.business_id) == before

    cada = _post(client, token, "2 bolsas de hielo a 18 cada una", "cada", "conv-cada")
    assert cada.json()["ui"][0]["data"]["product_name"] == "bolsas de hielo"
    assert cada.json()["ui"][0]["data"]["line_total"]["amount"] == "36.00"

    pastel = _post(client, token, "1 pastel 250", "pastel", "conv-pastel")
    assert pastel.json()["ui"][0]["data"]["product_name"] == "pastel"
    assert pastel.json()["ui"][0]["data"]["unit_normalized"] == "unit"
    assert pastel.json()["ui"][0]["data"]["line_total"]["amount"] == "250.00"

    missing = _post(client, token, "2 bolsas de hielo", "miss", "conv-miss")
    assert missing.json()["ui"] == []
    assert missing.json()["text"] == "¿A qué precio vendiste cada bolsa?"
    sessions, items = _sales_for(db_session, tenant.business_id)
    assert len([item for item in items if item.product_name_snapshot == "bolsas de hielo"]) == 2
    done = _post(client, token, "18", "miss-18", "conv-miss")
    assert done.json()["ui"][0]["data"]["line_total"]["amount"] == "36.00"
    _, items = _sales_for(db_session, tenant.business_id)
    assert len([item for item in items if item.product_name_snapshot == "bolsas de hielo"]) == 3

    bare = _post(client, token, "pastel", "pq", "conv-pq")
    assert bare.json()["text"] == "¿Cuántos vendiste y a qué precio?"
    still = _post(client, token, "2", "pq-2", "conv-pq")
    assert still.json()["ui"] == []
    assert "precio" in still.json()["text"]
    final = _post(client, token, "250", "pq-250", "conv-pq")
    assert final.json()["ui"][0]["data"]["line_total"]["amount"] == "500.00"
    _, items = _sales_for(db_session, tenant.business_id)
    assert len([item for item in items if item.product_name_snapshot == "pastel"]) == 2

    before_box = len(_sales_for(db_session, tenant.business_id)[1])
    bad = _post(client, token, "2 cajas de hielo a 18", "box", "conv-box")
    assert bad.json()["ui"] == []
    assert "No reconozco esa unidad" in bad.json()["text"]
    assert len(_sales_for(db_session, tenant.business_id)[1]) == before_box


def test_mass_basis_display_and_direct_tool(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    ambiguous = _post(client, token, "500g de hielo a 40", "mass-ask", "conv-mass")
    assert ambiguous.json()["ui"] == []
    assert ambiguous.json()["text"] == "¿Los $40.00 son por kilogramo? Responde por kilo."
    assert _sales_for(db_session, tenant.business_id)[0] == []
    yes = _post(client, token, "sí", "mass-si", "conv-mass")
    assert yes.json()["ui"] == []
    assert "por kilo" in yes.json()["text"]
    assert _sales_for(db_session, tenant.business_id)[1] == []
    done = _post(client, token, "por kilo", "mass-ok", "conv-mass")
    assert done.json()["ui"][0]["data"]["product_name"] == "hielo"
    assert done.json()["ui"][0]["data"]["quantity_normalized"] == "0.500"
    assert done.json()["ui"][0]["data"]["line_total"]["amount"] == "20.00"
    _, items = _sales_for(db_session, tenant.business_id)
    assert len(items) == 1

    explicit = _post(client, token, "500g de hielo a 40 por kilo", "mass-ex", "conv-mass-ex")
    assert explicit.json()["ui"][0]["data"]["line_total"]["amount"] == "20.00"

    coffee = _post(client, token, "1 Café Orgánico 50", "cafe", "conv-cafe")
    assert coffee.json()["ui"][0]["data"]["product_name"] == "Café Orgánico"
    assert "cafe organico" not in coffee.json()["text"]
    molido = _post(client, token, "500g de Café Molido a 240 por kilo", "molido", "conv-molido")
    assert molido.json()["ui"][0]["data"]["product_name"] == "Café Molido"
    assert molido.json()["ui"][0]["data"]["unit_normalized"] == "kilogram"

    workflow = _workflow(db_session)
    context = TenantContext(business_id=tenant.business_id, actor_id=tenant.actor_id)
    from app.agent.contracts import AgentDecision

    ignored = workflow.execute(
        tenant=context,
        decision=AgentDecision(
            intent="add_sale_item",
            product_query="bolsas de hielo",
            quantity="2",
            unit="package",
            unit_price="99.00",
        ),
        conversation_id="conv-model",
        idempotency_key="model-99",
        correlation_id="c",
        raw_message="2 bolsas de hielo",
    )
    assert ignored.kind == "clarify"
    assert "precio" in ignored.text
    direct = workflow.execute_tool(
        tenant=context,
        arguments={
            "source_type": "free_concept",
            "concept_name": "Café Orgánico",
            "quantity": "1",
            "unit": "unit",
            "unit_price": {"amount": "50.00", "currency": "MXN"},
            "sale_session_id": "ignored",
        },
        conversation_id="conv-direct",
        idempotency_key="direct-1",
        correlation_id="c",
    )
    db_session.commit()
    assert direct.payload["product_name"] == "Café Orgánico"
    assert direct.payload["source_type"] == "free_concept"

    catalog = CatalogRepository(db_session)
    catalog.add(
        tenant=context,
        product=CatalogProduct(
            id=new_uuid7(),
            business_id=tenant.business_id,
            name="Café de la casa",
            normalized_name=normalize_product_name("Café Orgánico"),
            sale_unit=SaleUnit.UNIT,
            pricing_type=PricingType.PER_UNIT,
            current_price=Money(Decimal("50.00"), "MXN"),
            status=ProductStatus.ACTIVE,
        ),
    )
    db_session.commit()
    refused = workflow.execute_tool(
        tenant=context,
        arguments={
            "source_type": "free_concept",
            "concept_name": "Café Orgánico",
            "quantity": "1",
            "unit": "unit",
            "unit_price": {"amount": "50.00", "currency": "MXN"},
            "sale_session_id": "ignored",
        },
        conversation_id="conv-direct-2",
        idempotency_key="direct-2",
        correlation_id="c",
    )
    assert refused.kind == "clarify"
    spoken = _post(client, token, "1 Café Orgánico 50", "cafe-hit", "conv-cafe-hit")
    assert spoken.json()["ui"][0]["data"]["product_name"] == "Café de la casa"
    _, items = _sales_for(db_session, tenant.business_id)
    assert any(item.product_name_snapshot == "Café de la casa" and item.source_type == "catalog" for item in items)
    clear_tenant_sale_mutations(db_session, tenant.business_id)
    set_current_business_id(db_session, tenant.business_id)
    db_session.execute(ProductRow.__table__.delete().where(ProductRow.normalized_name == "cafe organico"))
    db_session.commit()


def test_mixed_session_payments_replay_and_audit(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    _post(client, token, "900gr zanahoria", "mix-z", "conv-mix")
    bags = _post(client, token, "2 bolsas de hielo a 18", "mix-b", "conv-mix")
    assert bags.json()["ui"][0]["data"]["session_total"]["amount"] == "58.50"
    summary = _post(client, token, "totalizar", "mix-tot", "conv-mix")
    assert summary.json()["ui"][0]["data"]["total"]["amount"] == "58.50"
    paid = _post(client, token, "efectivo", "mix-pay", "conv-mix")
    assert paid.status_code == 200, paid.text
    assert paid.json()["ui"][0]["component"] == "sale_confirmed"
    names = [item["product_name"] for item in paid.json()["ui"][0]["data"]["items"]]
    assert "bolsas de hielo" in names
    assert ZANAHORIA_NAME in names

    card_add = _post(client, token, "1 pastel 250", "card-add", "conv-card")
    _post(client, token, "totalizar", "card-tot", "conv-card")
    card = _post(client, token, "tarjeta", "card-pay", "conv-card")
    assert card.json()["ui"][0]["data"]["payment"]["method"] == "card"
    transfer_add = _post(client, token, "1 pastel 250", "xfer-add", "conv-xfer")
    assert transfer_add.status_code == 200
    _post(client, token, "totalizar", "xfer-tot", "conv-xfer")
    transfer = _post(client, token, "transferencia", "xfer-pay", "conv-xfer")
    assert transfer.json()["ui"][0]["data"]["payment"]["method"] == "transfer"

    first = _post(client, token, "2 bolsas de hielo a 18", "replay-free", "conv-replay")
    replay = _post(client, token, "2 bolsas de hielo a 18", "replay-free", "conv-replay")
    assert replay.json()["ui"][0]["data"]["sale_item_id"] == first.json()["ui"][0]["data"]["sale_item_id"]
    second = _post(client, token, "2 bolsas de hielo a 18", "replay-free-2", "conv-replay")
    assert second.json()["ui"][0]["data"]["sale_item_id"] != first.json()["ui"][0]["data"]["sale_item_id"]

    set_current_business_id(db_session, tenant.business_id)
    audit = db_session.scalars(
        select(AuditEventRow).where(
            AuditEventRow.business_id == tenant.business_id,
            AuditEventRow.action == "sale.add_item@1",
            AuditEventRow.idempotency_key == "mix-b",
        )
    ).one()
    assert audit.after_payload["source_type"] == "free_concept"
    assert audit.after_payload["product_id"] is None
    assert audit.after_payload["product_name"] == "bolsas de hielo"
    assert audit.after_payload["unit_price"]["amount"] == "18.00"
    event = db_session.scalars(
        select(OutboxEventRow).where(
            OutboxEventRow.business_id == tenant.business_id,
            OutboxEventRow.event_type == "sale.item.added",
        )
    ).all()
    free_events = [row for row in event if row.payload.get("product_name") == "bolsas de hielo"]
    assert free_events[0].payload["source_type"] == "free_concept"
    assert free_events[0].payload["product_id"] is None
    catalog_audit = db_session.scalars(
        select(AuditEventRow).where(
            AuditEventRow.business_id == tenant.business_id,
            AuditEventRow.idempotency_key == "mix-z",
            AuditEventRow.action == "sale.add_item@1",
        )
    ).one()
    assert catalog_audit.after_payload["source_type"] == "catalog"
    assert catalog_audit.after_payload["product_id"]


def test_display_limits_day_and_post_close(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    empty = _post(client, token, "2 a 18", "empty", "conv-empty")
    assert empty.json()["ui"] == []
    assert _sales_for(db_session, tenant.business_id)[1] == []
    long_name = "A" * 201
    too_long = _post(client, token, f"1 {long_name} 10", "long", "conv-long")
    assert too_long.json()["ui"] == []
    assert "demasiado largo" in too_long.json()["text"]
    _, items = _sales_for(db_session, tenant.business_id)
    assert items == []

    added = _post(client, token, "2 bolsas de hielo a 18", "day-add", "conv-day-free")
    assert added.status_code == 200
    _post(client, token, "totalizar", "day-tot", "conv-day-free")
    _post(client, token, "efectivo", "day-pay", "conv-day-free")
    summary = _post(client, token, "cuanto vendimos hoy", "day-sum", "conv-day-sum")
    assert summary.json()["ui"][0]["data"]["gross_sales_total"] == "36.00"
    counted = _close_post(client, token, "conté 36.00", "day-count", "conv-day-free")
    assert counted.status_code == 200, counted.text
    requested = _close_post(client, token, "cerrar el día", "day-req", "conv-day-free")
    confirmation = _token_of(requested)
    closed = _confirm(client, token, "day-free", confirmation, key="day-confirm")
    assert closed.status_code == 200, closed.text
    assert _snapshots(db_session, tenant.business_id)[0].gross_sales_total == Decimal("36.00")
    assert _day(db_session, tenant.business_id).status == "closed"
    _post(client, token, "1 pastel 250", "after", "conv-after")
    _post(client, token, "totalizar", "after-tot", "conv-after")
    refused = _post(client, token, "efectivo", "after-pay", "conv-after")
    assert "ya está cerrada" in refused.json()["text"]
    sessions, _items = _sales_for(db_session, tenant.business_id)
    assert all(session.status != "confirmed" or session.confirmed_at is not None for session in sessions)
    assert not any(session.status == "confirmed" and session.conversation_id == "conv-after" for session in sessions)
