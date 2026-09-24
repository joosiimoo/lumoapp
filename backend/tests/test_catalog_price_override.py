from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent.contracts import AgentDecision
from app.domain.catalog import PricingType, ProductStatus, SaleUnit, normalize_product_name
from app.domain.catalog.product import Product as CatalogProduct
from app.domain.shared.ids import new_uuid7
from app.domain.shared.money import Money
from app.infrastructure.persistence.models import AuditEventRow, IdempotencyRecordRow, OutboxEventRow, ProductRow, SaleItemRow
from app.infrastructure.persistence.rls import set_current_business_id
from app.infrastructure.persistence.seed import GALLETA_A_NAME, TOMATE_NAME, TOMATE_PRODUCT_ID, ZANAHORIA_NAME
from tests.test_conversational_sale import _post, _sales_for, _seed_carrota
from tests.test_daily_close_confirmation import _confirm, _ready
from tests.test_noncatalog_sale import _products, _workflow


def _set_price(db_session, business_id, product_id, amount: str) -> None:
    set_current_business_id(db_session, business_id)
    row = db_session.get(ProductRow, product_id)
    row.current_price = Decimal(amount)
    db_session.commit()


def test_override_question_reason_and_normal_paths(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    normal = _post(client, token, "900gr zanahoria", "ov-z", "conv-ov")
    assert normal.json()["ui"][0]["data"]["line_total"]["amount"] == "22.50"
    assert "catalog_unit_price" not in normal.json()["ui"][0]["data"]
    equal = _post(client, token, "900gr tomate a 20", "ov-eq", "conv-ov-eq")
    assert equal.json()["ui"][0]["data"]["unit_price"]["amount"] == "20.00"
    assert equal.json()["ui"][0]["data"]["line_total"]["amount"] == "18.00"
    assert "catalog_unit_price" not in equal.json()["ui"][0]["data"]
    before = _products(db_session, tenant.business_id)
    asked = _post(client, token, "900gr tomate a 30", "ov-ask", "conv-ov-ask")
    assert asked.json()["ui"] == []
    assert asked.json()["text"] == "Tomate está registrado a $20.00 por kg. ¿Por qué lo vendiste a $30.00?"
    _, items = _sales_for(db_session, tenant.business_id)
    assert not any(item.price_override_reason for item in items)
    assert _products(db_session, tenant.business_id) == before
    set_current_business_id(db_session, tenant.business_id)
    assert (
        db_session.scalars(select(IdempotencyRecordRow).where(IdempotencyRecordRow.key == "ov-ask")).all() == []
    )
    blank = _post(client, token, "   ", "ov-blank", "conv-ov-ask")
    assert blank.json()["text"] == "Necesito un motivo para registrar ese precio."
    long = _post(client, token, "á" * 201, "ov-long", "conv-ov-ask")
    assert long.json()["text"] == "Ese motivo es demasiado largo."
    _, still = _sales_for(db_session, tenant.business_id)
    assert len(still) == len(items)
    done = _post(client, token, "  Precio   especial  para cliente  ", "ov-why", "conv-ov-ask")
    assert done.json()["text"] == "Agregué 0.900 kg de Tomate · $27.00"
    card = done.json()["ui"][0]
    assert card["version"] == 1
    assert card["data"]["catalog_unit_price"]["amount"] == "20.00"
    assert card["data"]["unit_price"]["amount"] == "30.00"
    assert card["data"]["line_total"]["amount"] == "27.00"
    assert "precio" not in card["fallback_text"].lower() or "especial" not in card["fallback_text"].lower()
    replay = _post(client, token, "Precio especial para cliente", "ov-why", "conv-ov-ask")
    assert replay.json()["ui"][0]["data"]["sale_item_id"] == card["data"]["sale_item_id"]
    conflict = _post(client, token, "otro motivo distinto", "ov-why", "conv-ov-ask")
    assert conflict.status_code == 409
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    product = db_session.get(ProductRow, TOMATE_PRODUCT_ID)
    assert product.current_price == Decimal("20.00")
    line = db_session.scalars(
        select(SaleItemRow).where(SaleItemRow.id == card["data"]["sale_item_id"])
    ).one()
    assert line.source_type == "catalog"
    assert line.catalog_unit_price_snapshot == Decimal("20.00")
    assert line.unit_price == Decimal("30.00")
    assert line.price_override_reason == "Precio especial para cliente"
    assert line.quantity_normalized == Decimal("0.900")
    assert line.line_total == Decimal("27.00")
    audit = db_session.scalars(
        select(AuditEventRow).where(
            AuditEventRow.business_id == tenant.business_id,
            AuditEventRow.action == "sale.add_item@1",
            AuditEventRow.idempotency_key == "ov-why",
        )
    ).one()
    assert audit.after_payload["price_override_reason"] == "Precio especial para cliente"
    assert audit.after_payload["catalog_unit_price_snapshot"]["amount"] == "20.00"
    assert audit.policy_decision["reason_code"] == "catalog_price_override"
    assert "SALE-001" in audit.policy_decision["rule_ids"]
    assert "CAT-001" in audit.policy_decision["rule_ids"]
    event = db_session.scalars(
        select(OutboxEventRow).where(
            OutboxEventRow.business_id == tenant.business_id,
            OutboxEventRow.event_type == "sale.item.added",
        )
    ).all()
    override_events = [row for row in event if row.payload.get("price_override_reason")]
    assert override_events[0].payload["unit_price"]["amount"] == "30.00"
    assert override_events[0].payload["catalog_unit_price_snapshot"]["amount"] == "20.00"
    assert not any(row.event_type == "sale.price.overridden" for row in event)


def test_lower_price_unit_package_cancel_and_replacement(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    lower = _post(client, token, "3 kg zanahoria a 11", "ov-low", "conv-low")
    assert "¿Por qué lo vendiste a $11.00?" in lower.json()["text"]
    saved = _post(client, token, "precio de cierre", "ov-low-why", "conv-low")
    assert saved.json()["ui"][0]["data"]["line_total"]["amount"] == "33.00"
    assert saved.json()["ui"][0]["data"]["catalog_unit_price"]["amount"] == "25.00"
    unit = _post(client, token, "2 galletas A a 10", "ov-unit", "conv-unit")
    assert unit.json()["text"] == "Galleta A está registrado a $12.00 por unidad. ¿Por qué lo vendiste a $10.00?"
    unit_done = _post(client, token, "promoción", "ov-unit-why", "conv-unit")
    assert unit_done.json()["ui"][0]["data"]["line_total"]["amount"] == "20.00"
    assert unit_done.json()["ui"][0]["data"]["catalog_unit_price"]["amount"] == "12.00"
    assert unit_done.json()["ui"][0]["data"]["product_name"] == GALLETA_A_NAME
    from app.infrastructure.persistence.catalog_sales import CatalogRepository
    from app.domain.shared.tenant import TenantContext

    context = TenantContext(business_id=tenant.business_id, actor_id=tenant.actor_id)
    set_current_business_id(db_session, tenant.business_id)
    existing = db_session.scalar(
        select(ProductRow).where(
            ProductRow.business_id == tenant.business_id,
            ProductRow.normalized_name == normalize_product_name("Canasta"),
        )
    )
    if existing is None:
        package_id = new_uuid7()
        CatalogRepository(db_session).add(
            tenant=context,
            product=CatalogProduct(
                id=package_id,
                business_id=tenant.business_id,
                name="Canasta",
                normalized_name=normalize_product_name("Canasta"),
                sale_unit=SaleUnit.PACKAGE,
                pricing_type=PricingType.PER_PACKAGE,
                current_price=Money(Decimal("40.00"), "MXN"),
                status=ProductStatus.ACTIVE,
            ),
        )
    else:
        existing.current_price = Decimal("40.00")
        existing.status = "active"
    db_session.commit()
    package = _post(client, token, "2 canasta a 35", "ov-pack", "conv-pack")
    assert "por paquete" in package.json()["text"]
    package_done = _post(client, token, "mayoreo", "ov-pack-why", "conv-pack")
    assert package_done.json()["ui"][0]["data"]["line_total"]["amount"] == "70.00"
    assert package_done.json()["ui"][0]["data"]["catalog_unit_price"]["amount"] == "40.00"
    set_current_business_id(db_session, tenant.business_id)
    for normalized in ("canasta", "huevo", "caja"):
        extra = db_session.scalars(
            select(ProductRow).where(
                ProductRow.business_id == tenant.business_id,
                ProductRow.normalized_name == normalized,
            )
        ).all()
        for row in extra:
            db_session.execute(SaleItemRow.__table__.delete().where(SaleItemRow.product_id == row.id))
            db_session.delete(row)
    db_session.commit()
    cancel = _post(client, token, "900gr tomate a 15", "ov-can", "conv-can")
    assert cancel.json()["ui"] == []
    stopped = _post(client, token, "no", "ov-can-no", "conv-can")
    assert stopped.json()["text"] == "Listo, no registré ese producto."
    assert stopped.json()["ui"] == []
    replaced = _post(client, token, "900gr tomate a 30", "ov-rep", "conv-rep")
    assert "¿Por qué" in replaced.json()["text"]
    nxt = _post(client, token, "2 galletas A", "ov-rep-new", "conv-rep")
    assert nxt.json()["ui"][0]["data"]["product_name"] == GALLETA_A_NAME
    assert "catalog_unit_price" not in nxt.json()["ui"][0]["data"]
    closed = _post(client, token, "900gr tomate a 30", "ov-cls", "conv-cls")
    assert closed.json()["ui"] == []
    summary = _post(client, token, "totalizar", "ov-cls-tot", "conv-cls")
    assert summary.status_code == 200
    assert summary.json()["ui"] == [] or "Tomate" not in summary.json()["text"]


def test_price_change_restarts_and_equal_recheck_is_normal(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    try:
        asked = _post(client, token, "900gr tomate a 30", "ov-race", "conv-race")
        assert asked.json()["ui"] == []
        _set_price(db_session, tenant.business_id, TOMATE_PRODUCT_ID, "22.00")
        restarted = _post(client, token, "precio especial para cliente", "ov-race-why", "conv-race")
        assert restarted.json()["ui"] == []
        assert restarted.json()["text"] == "Tomate ahora está registrado a $22.00 por kg. ¿Por qué lo vendiste a $30.00?"
        _, items = _sales_for(db_session, tenant.business_id)
        assert items == []
        set_current_business_id(db_session, tenant.business_id)
        assert db_session.scalars(select(IdempotencyRecordRow).where(IdempotencyRecordRow.key == "ov-race-why")).all() == []
        _set_price(db_session, tenant.business_id, TOMATE_PRODUCT_ID, "30.00")
        equal = _post(client, token, "precio especial para cliente", "ov-race-eq", "conv-race")
        assert equal.json()["text"] == "Agregué 0.900 kg de Tomate · $27.00"
        assert "catalog_unit_price" not in equal.json()["ui"][0]["data"]
        set_current_business_id(db_session, tenant.business_id)
        db_session.expire_all()
        line = db_session.scalars(select(SaleItemRow).where(SaleItemRow.business_id == tenant.business_id)).one()
        assert line.catalog_unit_price_snapshot == Decimal("30.00")
        assert line.unit_price == Decimal("30.00")
        assert line.price_override_reason is None
        assert line.line_total == Decimal("27.00")
    finally:
        _set_price(db_session, tenant.business_id, TOMATE_PRODUCT_ID, "20.00")


def test_model_only_price_does_not_override_and_direct_call_locks(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    workflow = _workflow(db_session)
    context_tenant, _token = tenant, token
    ignored = workflow.execute(
        tenant=context_tenant,
        decision=AgentDecision(
            intent="add_sale_item",
            product_query="tomate",
            quantity="900",
            unit="gram",
            unit_price="30.00",
        ),
        conversation_id="conv-model-price",
        idempotency_key="ov-model",
        correlation_id="c",
        raw_message="900gr tomate",
    )
    db_session.commit()
    assert ignored.kind == "committed"
    assert ignored.payload["unit_price"]["amount"] == "20.00"
    assert ignored.payload["line_total"]["amount"] == "18.00"
    assert ignored.payload.get("catalog_unit_price") is None
    assert ignored.payload["price_override_reason"] is None
    missing = workflow.execute_tool(
        tenant=context_tenant,
        arguments={
            "source_type": "catalog",
            "product_id": str(TOMATE_PRODUCT_ID),
            "quantity": "900",
            "unit": "gram",
            "price_override": {"unit_price": {"amount": "30.00", "currency": "MXN"}, "reason": ""},
        },
        conversation_id="conv-model-price",
        idempotency_key="ov-direct-blank",
        correlation_id="c",
    )
    assert missing.kind == "clarify"
    assert missing.payload.get("sale_item_id") is None
    direct = workflow.execute_tool(
        tenant=context_tenant,
        arguments={
            "source_type": "catalog",
            "product_id": str(TOMATE_PRODUCT_ID),
            "quantity": "900",
            "unit": "gram",
            "price_override": {
                "unit_price": {"amount": "30.00", "currency": "MXN"},
                "reason": "mostrador",
            },
        },
        conversation_id="conv-model-price",
        idempotency_key="ov-direct",
        correlation_id="c",
    )
    db_session.commit()
    assert direct.payload["catalog_unit_price"]["amount"] == "20.00"
    assert direct.payload["unit_price"]["amount"] == "30.00"
    assert direct.payload["line_total"]["amount"] == "27.00"
    set_current_business_id(db_session, tenant.business_id)
    assert db_session.get(ProductRow, TOMATE_PRODUCT_ID).current_price == Decimal("20.00")


def test_in_transaction_catalog_read_sets_snapshot_price_and_total(db_session) -> None:
    tenant, _token = _seed_carrota(db_session)
    workflow = _workflow(db_session)
    catalog = workflow._catalog
    original = catalog.get

    def priced_get(*, tenant, product_id):  # noqa: ANN001
        product = original(tenant=tenant, product_id=product_id)
        return replace(product, current_price=Money(Decimal("25.00"), "MXN"))

    catalog.get = priced_get
    result = workflow.execute(
        tenant=tenant,
        decision=AgentDecision(
            intent="add_sale_item",
            product_query="tomate",
            quantity="900",
            unit="gram",
        ),
        conversation_id="conv-one-read",
        idempotency_key="ov-one-read",
        correlation_id="c",
        raw_message="900gr tomate",
    )
    db_session.commit()
    assert result.payload["catalog_unit_price_snapshot"]["amount"] == "25.00"
    assert result.payload["unit_price"]["amount"] == "25.00"
    assert result.payload["line_total"]["amount"] == "22.50"
    assert result.payload["price_override_reason"] is None


def test_mixed_total_payment_and_closed_day(client: TestClient, db_session) -> None:
    tenant, token = _seed_carrota(db_session)
    _post(client, token, "900gr zanahoria", "mix-z", "conv-mix-ov")
    _post(client, token, "900gr tomate a 30", "mix-ask", "conv-mix-ov")
    tomato = _post(client, token, "precio especial para cliente", "mix-why", "conv-mix-ov")
    assert tomato.json()["ui"][0]["data"]["line_total"]["amount"] == "27.00"
    bags = _post(client, token, "2 bolsas de hielo a 18", "mix-b", "conv-mix-ov")
    assert bags.json()["ui"][0]["data"]["line_total"]["amount"] == "36.00"
    assert "catalog_unit_price" not in bags.json()["ui"][0]["data"]
    summary = _post(client, token, "totalizar", "mix-tot", "conv-mix-ov")
    data = summary.json()["ui"][0]["data"]
    assert data["total"]["amount"] == "85.50"
    names = {item["product_name"]: item for item in data["items"]}
    assert names[ZANAHORIA_NAME].get("catalog_unit_price") is None
    assert names[TOMATE_NAME]["catalog_unit_price"]["amount"] == "20.00"
    assert "catalog_unit_price" not in names["bolsas de hielo"]
    cash = _post(client, token, "efectivo", "mix-cash", "conv-mix-ov")
    assert cash.json()["ui"][0]["component"] == "sale_confirmed"
    assert cash.json()["ui"][0]["data"]["total"]["amount"] == "85.50"
    confirmed_items = {item["product_name"]: item for item in cash.json()["ui"][0]["data"]["items"]}
    assert confirmed_items[TOMATE_NAME]["catalog_unit_price"]["amount"] == "20.00"
    card_add = _post(client, token, "900gr zanahoria", "card-z", "conv-card-ov")
    assert card_add.status_code == 200
    _post(client, token, "totalizar", "card-tot", "conv-card-ov")
    card = _post(client, token, "tarjeta", "card-pay", "conv-card-ov")
    assert card.json()["ui"][0]["data"]["payment"]["method"] == "card"
    _post(client, token, "900gr zanahoria", "xfer-z", "conv-xfer-ov")
    _post(client, token, "totalizar", "xfer-tot", "conv-xfer-ov")
    transfer = _post(client, token, "transferencia", "xfer-pay", "conv-xfer-ov")
    assert transfer.json()["ui"][0]["data"]["payment"]["method"] == "transfer"
    confirmation, _requested = _ready(client, token, "ov-closed")
    closed = _confirm(client, token, "ov-closed", confirmation)
    assert closed.status_code == 200, closed.text
    _post(client, token, "900gr tomate a 30", "closed-ask", "conv-closed-ov")
    _post(client, token, "precio especial para cliente", "closed-why", "conv-closed-ov")
    _post(client, token, "totalizar", "closed-tot", "conv-closed-ov")
    refused = _post(client, token, "efectivo", "closed-pay", "conv-closed-ov")
    assert refused.json()["text"] == "La jornada de hoy ya está cerrada. No puedo registrar otra venta en ese día."
