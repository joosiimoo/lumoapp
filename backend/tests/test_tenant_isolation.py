"""Cleanup may touch only a tenant this process created, and never the application database."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import create_engine, func, select, text

from app.infrastructure.persistence.models import (
    BusinessEventRow,
    CashCountRow,
    ClosingSnapshotRow,
    OperationalDayRow,
    OutcomeRunRow,
    SourceCoverageRecordRow,
    WorkItemRow,
)
from app.infrastructure.persistence.rls import set_current_business_id
from app.infrastructure.persistence.seed import CARROTA_BUSINESS_ID
from tests.conftest import DEFAULT_ADMIN_URL, make_settings, postgres_available
from tests.isolation import seed_catalog_tenant
from tests.sale_cleanup import clear_tenant_sale_mutations, discard_work_items
from tests.test_daily_close_confirmation import _confirm, _ready
from tests.test_daily_close_preparation import _cash_sale

pytestmark = pytest.mark.skipif(not postgres_available(make_settings()), reason="PostgreSQL is not available")


def test_cleanup_refuses_pilot_and_unregistered_tenants() -> None:
    with pytest.raises(RuntimeError, match="not a test-owned tenant"):
        clear_tenant_sale_mutations(None, CARROTA_BUSINESS_ID)
    with pytest.raises(RuntimeError, match="not a test-owned tenant"):
        clear_tenant_sale_mutations(None, UUID("018f0000-0000-7000-8000-000000000099"))


def test_global_purge_refuses_the_application_database() -> None:
    admin = create_engine(DEFAULT_ADMIN_URL)
    witness = create_engine("postgresql+psycopg://postgres:postgres@localhost:5432/lumo")
    try:
        with witness.connect() as connection:
            before = connection.execute(text("SELECT count(*) FROM operations.operational_days")).scalar_one()
        with pytest.raises(RuntimeError, match="refusing global operational purge"):
            discard_work_items(admin)
        with witness.connect() as connection:
            after = connection.execute(text("SELECT count(*) FROM operations.operational_days")).scalar_one()
        assert after == before
    finally:
        admin.dispose()
        witness.dispose()


def _count(db_session, business_id, model) -> int:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return db_session.scalar(select(func.count()).select_from(model).where(model.business_id == business_id))


def test_clearing_tenant_a_preserves_tenant_b(client, db_session) -> None:
    tenant_a, token_a = seed_catalog_tenant(db_session, name="Isolation A")
    tenant_b, token_b = seed_catalog_tenant(db_session, name="Isolation B")
    _cash_sale(client, token_a, "iso-a", "900gr zanahoria")
    confirmation, _requested = _ready(client, token_b, "iso-b")
    closed = _confirm(client, token_b, "iso-b", confirmation)
    assert closed.status_code == 200, closed.text
    preserved = (
        OperationalDayRow,
        BusinessEventRow,
        SourceCoverageRecordRow,
        CashCountRow,
        ClosingSnapshotRow,
        OutcomeRunRow,
        WorkItemRow,
    )
    before = {model: _count(db_session, tenant_b.business_id, model) for model in preserved}
    assert all(count >= 1 for count in before.values())
    clear_tenant_sale_mutations(db_session, tenant_a.business_id)
    for model in preserved:
        assert _count(db_session, tenant_a.business_id, model) == 0
        assert _count(db_session, tenant_b.business_id, model) == before[model]
