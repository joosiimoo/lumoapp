from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.operations import (
    OUTCOME_TYPE_DAILY_CLOSE_READY,
    OUTCOME_VERSION,
    CashCount,
    CashCountSource,
    CashStatus,
    ClosingSnapshot,
    DaySummaryTotals,
    OperationalDay,
    OperationalDayStatus,
    OutcomeRun,
    OutcomeRunStatus,
    ResolutionActorType,
    ResolutionCode,
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
    WorkItemType,
)
from app.domain.sales import PaymentStatus, SaleSessionStatus
from app.domain.shared.errors import TenantScopeViolationError, ValidationAppError
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.models import (
    CashCountRow,
    ClosingSnapshotRow,
    OperationalDayRow,
    OutcomeRunRow,
    PaymentRow,
    SaleSessionRow,
    WorkItemRow,
)
from app.infrastructure.persistence.rls import set_current_business_id


class OperationsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_open_day(
        self,
        *,
        tenant: TenantContext,
        business_date: date,
        timezone_name: str,
        day_id: UUID,
        opened_at: datetime,
    ) -> tuple[OperationalDay, bool]:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        stmt = (
            insert(OperationalDayRow)
            .values(
                id=day_id,
                business_id=tenant.business_id,
                business_date=business_date,
                status=OperationalDayStatus.OPEN.value,
                timezone=timezone_name,
                created_at=opened_at,
                updated_at=opened_at,
            )
            .on_conflict_do_nothing(constraint="uq_operational_days_business_date")
            .returning(OperationalDayRow.id)
        )
        inserted_id = self._session.execute(stmt).scalar_one_or_none()
        if inserted_id is not None:
            row = self._session.get(OperationalDayRow, inserted_id)
            assert row is not None
            return _to_day(row), True
        existing = self._session.scalar(
            select(OperationalDayRow).where(
                OperationalDayRow.business_id == tenant.business_id,
                OperationalDayRow.business_date == business_date,
            )
        )
        if existing is None:
            raise ValidationAppError("operational day could not be ensured")
        return _to_day(existing), False

    def lock_day_for_update(
        self,
        *,
        tenant: TenantContext,
        business_date: date,
    ) -> OperationalDay | None:
        """Serialize cash-count writes on the day row. Never inserts."""
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.scalar(
            select(OperationalDayRow)
            .where(
                OperationalDayRow.business_id == tenant.business_id,
                OperationalDayRow.business_date == business_date,
            )
            .with_for_update()
        )
        return _to_day(row) if row is not None else None

    def get_by_date(self, *, tenant: TenantContext, business_date: date) -> OperationalDay | None:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.scalar(
            select(OperationalDayRow).where(
                OperationalDayRow.business_id == tenant.business_id,
                OperationalDayRow.business_date == business_date,
            )
        )
        return _to_day(row) if row is not None else None

    def summarize_day(
        self,
        *,
        tenant: TenantContext,
        operational_day_id: UUID,
        currency: str,
    ) -> DaySummaryTotals:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        currencies = self._session.scalars(
            select(PaymentRow.currency)
            .join(SaleSessionRow, SaleSessionRow.id == PaymentRow.sale_session_id)
            .where(
                SaleSessionRow.business_id == tenant.business_id,
                SaleSessionRow.operational_day_id == operational_day_id,
                SaleSessionRow.status == SaleSessionStatus.CONFIRMED.value,
                PaymentRow.status == PaymentStatus.RECORDED.value,
            )
            .distinct()
        ).all()
        if any(code != currency for code in currencies):
            raise ValidationAppError("payment currency does not match the business")
        cash = func.coalesce(func.sum(PaymentRow.amount).filter(PaymentRow.method == "cash"), 0)
        card = func.coalesce(func.sum(PaymentRow.amount).filter(PaymentRow.method == "card"), 0)
        transfer = func.coalesce(func.sum(PaymentRow.amount).filter(PaymentRow.method == "transfer"), 0)
        row = self._session.execute(
            select(
                func.count(func.distinct(SaleSessionRow.id)),
                func.coalesce(func.sum(PaymentRow.amount), 0),
                cash,
                card,
                transfer,
            )
            .select_from(SaleSessionRow)
            .join(PaymentRow, PaymentRow.sale_session_id == SaleSessionRow.id)
            .where(
                SaleSessionRow.business_id == tenant.business_id,
                SaleSessionRow.operational_day_id == operational_day_id,
                SaleSessionRow.status == SaleSessionStatus.CONFIRMED.value,
                PaymentRow.business_id == tenant.business_id,
                PaymentRow.status == PaymentStatus.RECORDED.value,
            )
        ).one()
        return DaySummaryTotals(
            sale_count=int(row[0] or 0),
            gross_sales_total=_money(row[1], currency),
            cash_total=_money(row[2], currency),
            card_total=_money(row[3], currency),
            transfer_total=_money(row[4], currency),
            currency=currency,
        )

    def expected_cash(
        self,
        *,
        tenant: TenantContext,
        operational_day_id: UUID,
        currency: str,
    ) -> str:
        """Expected cash is that day's `cash_total`; one aggregation, no second SQL path."""
        totals = self.summarize_day(
            tenant=tenant,
            operational_day_id=operational_day_id,
            currency=currency,
        )
        return totals.cash_total

    def get_current_cash_count(
        self,
        *,
        tenant: TenantContext,
        operational_day_id: UUID,
    ) -> CashCount | None:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.scalar(
            select(CashCountRow).where(
                CashCountRow.business_id == tenant.business_id,
                CashCountRow.operational_day_id == operational_day_id,
                CashCountRow.superseded_by_id.is_(None),
            )
        )
        return _to_cash_count(row) if row is not None else None

    def mark_superseded(
        self,
        *,
        tenant: TenantContext,
        previous_id: UUID,
        new_id: UUID,
        updated_at: datetime,
    ) -> None:
        """Retire the current count before the replacement row exists.

        Issued as an explicit UPDATE and flushed so PostgreSQL sees it before the INSERT of
        `new_id`: the previous row leaves `uq_cash_counts_current` first, so the immediate partial
        unique index never holds two current rows. The forward reference is valid at COMMIT through
        the deferred fk_cash_counts_superseded_by.
        """
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        result = self._session.execute(
            update(CashCountRow)
            .where(
                CashCountRow.id == previous_id,
                CashCountRow.business_id == tenant.business_id,
                CashCountRow.superseded_by_id.is_(None),
            )
            .values(superseded_by_id=new_id, updated_at=updated_at)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise ValidationAppError("cash count could not be superseded")
        self._session.flush()

    def insert_cash_count(self, *, tenant: TenantContext, cash_count: CashCount) -> CashCount:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        if cash_count.business_id != tenant.business_id:
            raise TenantScopeViolationError("cash count business does not match the tenant")
        row = CashCountRow(
            id=cash_count.id,
            business_id=tenant.business_id,
            operational_day_id=cash_count.operational_day_id,
            actor_id=cash_count.actor_id,
            amount=cash_count.amount,
            currency=cash_count.currency,
            source=CashCountSource(cash_count.source).value,
            counted_at=cash_count.counted_at,
            supersedes_cash_count_id=cash_count.supersedes_cash_count_id,
            superseded_by_id=None,
        )
        self._session.add(row)
        self._session.flush()
        return _to_cash_count(row)

    def get_snapshot_for_day(
        self,
        *,
        tenant: TenantContext,
        operational_day_id: UUID,
    ) -> ClosingSnapshot | None:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.scalar(
            select(ClosingSnapshotRow).where(
                ClosingSnapshotRow.business_id == tenant.business_id,
                ClosingSnapshotRow.operational_day_id == operational_day_id,
            )
        )
        return _to_snapshot(row) if row is not None else None

    def insert_snapshot(self, *, tenant: TenantContext, snapshot: ClosingSnapshot) -> ClosingSnapshot:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        if snapshot.business_id != tenant.business_id:
            raise TenantScopeViolationError("snapshot business does not match the tenant")
        row = ClosingSnapshotRow(
            id=snapshot.id,
            business_id=tenant.business_id,
            operational_day_id=snapshot.operational_day_id,
            cash_count_id=snapshot.cash_count_id,
            actor_id=snapshot.actor_id,
            business_date=snapshot.business_date,
            currency=snapshot.currency,
            sale_count=snapshot.sale_count,
            gross_sales_total=snapshot.gross_sales_total,
            cash_total=snapshot.cash_total,
            card_total=snapshot.card_total,
            transfer_total=snapshot.transfer_total,
            expected_cash=snapshot.expected_cash,
            counted_cash=snapshot.counted_cash,
            cash_difference=snapshot.cash_difference,
            cash_status=snapshot.cash_status.value,
            closed_at=snapshot.closed_at,
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
        )
        self._session.add(row)
        self._session.flush()
        return _to_snapshot(row)

    def close_open_day(
        self,
        *,
        tenant: TenantContext,
        operational_day_id: UUID,
        closed_at: datetime,
    ) -> None:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        result = self._session.execute(
            update(OperationalDayRow)
            .where(
                OperationalDayRow.id == operational_day_id,
                OperationalDayRow.business_id == tenant.business_id,
                OperationalDayRow.status == OperationalDayStatus.OPEN.value,
            )
            .values(status=OperationalDayStatus.CLOSED.value, updated_at=closed_at)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise ValidationAppError("operational day could not be closed")
        self._session.expire_all()

    def list_work_items(
        self,
        *,
        tenant: TenantContext,
        operational_day_id: UUID,
    ) -> list[WorkItem]:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        rows = self._session.scalars(
            select(WorkItemRow)
            .where(
                WorkItemRow.business_id == tenant.business_id,
                WorkItemRow.operational_day_id == operational_day_id,
            )
            .order_by(WorkItemRow.created_at, WorkItemRow.id)
        ).all()
        return [_to_work_item(row) for row in rows]

    def list_open_work_items(
        self,
        *,
        tenant: TenantContext,
        operational_day_id: UUID,
    ) -> list[WorkItem]:
        return [
            item
            for item in self.list_work_items(tenant=tenant, operational_day_id=operational_day_id)
            if item.status is WorkItemStatus.OPEN
        ]

    def insert_work_item(self, *, tenant: TenantContext, work_item: WorkItem) -> WorkItem:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        if work_item.business_id != tenant.business_id:
            raise TenantScopeViolationError("work item business does not match the tenant")
        if work_item.status is not WorkItemStatus.OPEN:
            raise ValidationAppError("a new work item must be open")
        row = WorkItemRow(
            id=work_item.id,
            business_id=tenant.business_id,
            operational_day_id=work_item.operational_day_id,
            type=work_item.type.value,
            status=WorkItemStatus.OPEN.value,
            priority=work_item.priority.value,
            responsible_party=work_item.responsible_party,
            reason_code=work_item.reason_code,
            source=work_item.source,
            evidence=dict(work_item.evidence),
            created_at=work_item.created_at,
            updated_at=work_item.updated_at,
            resolved_at=None,
            resolution_actor_type=None,
            resolved_by_actor_id=None,
            resolution_code=None,
            outcome_run_id=work_item.outcome_run_id,
        )
        self._session.add(row)
        self._session.flush()
        return _to_work_item(row)

    def refresh_work_item_evidence(
        self,
        *,
        tenant: TenantContext,
        work_item_id: UUID,
        reason_code: str,
        evidence: dict,
        updated_at: datetime,
    ) -> WorkItem:
        """Update evidence on an open row. A matching row is left untouched."""
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.scalar(
            select(WorkItemRow).where(
                WorkItemRow.id == work_item_id,
                WorkItemRow.business_id == tenant.business_id,
            )
        )
        if row is None or row.status != WorkItemStatus.OPEN.value:
            raise ValidationAppError("open work item could not be refreshed")
        if row.reason_code == reason_code and dict(row.evidence) == evidence:
            return _to_work_item(row)
        row.reason_code = reason_code
        row.evidence = evidence
        row.updated_at = updated_at
        self._session.flush()
        return _to_work_item(row)

    def resolve_work_item(
        self,
        *,
        tenant: TenantContext,
        work_item_id: UUID,
        resolved_at: datetime,
        resolution_actor_type: ResolutionActorType,
        resolved_by_actor_id: UUID | None,
        resolution_code: ResolutionCode,
    ) -> WorkItem:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        if resolution_actor_type is ResolutionActorType.BUSINESS and resolved_by_actor_id is None:
            raise ValidationAppError("a business resolution requires an actor")
        if resolution_actor_type is ResolutionActorType.SYSTEM and resolved_by_actor_id is not None:
            raise ValidationAppError("a system resolution must not store an actor")
        result = self._session.execute(
            update(WorkItemRow)
            .where(
                WorkItemRow.id == work_item_id,
                WorkItemRow.business_id == tenant.business_id,
                WorkItemRow.status == WorkItemStatus.OPEN.value,
            )
            .values(
                status=WorkItemStatus.RESOLVED.value,
                resolved_at=resolved_at,
                resolution_actor_type=resolution_actor_type.value,
                resolved_by_actor_id=resolved_by_actor_id,
                resolution_code=resolution_code.value,
                updated_at=resolved_at,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise ValidationAppError("open work item could not be resolved")
        self._session.expire_all()
        row = self._session.scalar(
            select(WorkItemRow).where(
                WorkItemRow.id == work_item_id,
                WorkItemRow.business_id == tenant.business_id,
            )
        )
        if row is None:
            raise ValidationAppError("resolved work item could not be read")
        return _to_work_item(row)

    def get_daily_close_outcome(
        self,
        *,
        tenant: TenantContext,
        operational_day_id: UUID,
    ) -> OutcomeRun | None:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.scalar(
            select(OutcomeRunRow).where(
                OutcomeRunRow.business_id == tenant.business_id,
                OutcomeRunRow.operational_day_id == operational_day_id,
                OutcomeRunRow.outcome_type == OUTCOME_TYPE_DAILY_CLOSE_READY,
                OutcomeRunRow.outcome_version == OUTCOME_VERSION,
            )
        )
        return _to_outcome(row) if row is not None else None

    def insert_daily_close_outcome(self, *, tenant: TenantContext, outcome: OutcomeRun) -> OutcomeRun:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        if outcome.business_id != tenant.business_id:
            raise TenantScopeViolationError("outcome business does not match the tenant")
        row = OutcomeRunRow(
            id=outcome.id,
            business_id=tenant.business_id,
            operational_day_id=outcome.operational_day_id,
            outcome_type=outcome.outcome_type,
            outcome_version=outcome.outcome_version,
            status=outcome.status.value,
            owner_type=outcome.owner_type,
            reason_code=outcome.reason_code,
            evidence=dict(outcome.evidence),
            created_at=outcome.created_at,
            updated_at=outcome.updated_at,
            ready_at=outcome.ready_at,
            completed_at=outcome.completed_at,
            closing_snapshot_id=outcome.closing_snapshot_id,
        )
        self._session.add(row)
        self._session.flush()
        return _to_outcome(row)

    def update_daily_close_outcome_evidence(
        self,
        *,
        tenant: TenantContext,
        outcome_run_id: UUID,
        evidence: dict,
        updated_at: datetime,
    ) -> OutcomeRun:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = self._require_outcome(tenant, outcome_run_id)
        if dict(row.evidence) == evidence:
            return _to_outcome(row)
        row.evidence = evidence
        row.updated_at = updated_at
        self._session.flush()
        return _to_outcome(row)

    def update_daily_close_outcome_status(
        self,
        *,
        tenant: TenantContext,
        outcome_run_id: UUID,
        status: OutcomeRunStatus,
        reason_code: str,
        evidence: dict,
        ready_at: datetime | None,
        completed_at: datetime | None,
        closing_snapshot_id: UUID | None,
        updated_at: datetime,
    ) -> OutcomeRun:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = self._require_outcome(tenant, outcome_run_id)
        unchanged = (
            row.status == status.value
            and row.reason_code == reason_code
            and dict(row.evidence) == evidence
            and row.ready_at == ready_at
            and row.completed_at == completed_at
            and row.closing_snapshot_id == closing_snapshot_id
        )
        if unchanged:
            return _to_outcome(row)
        row.status = status.value
        row.reason_code = reason_code
        row.evidence = evidence
        row.ready_at = ready_at
        row.completed_at = completed_at
        row.closing_snapshot_id = closing_snapshot_id
        row.updated_at = updated_at
        self._session.flush()
        return _to_outcome(row)

    def link_null_work_items(
        self,
        *,
        tenant: TenantContext,
        operational_day_id: UUID,
        outcome_run_id: UUID,
    ) -> int:
        """Stamp outcome_run_id on rows that are still null. Nothing else changes."""
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        result = self._session.execute(
            update(WorkItemRow)
            .where(
                WorkItemRow.business_id == tenant.business_id,
                WorkItemRow.operational_day_id == operational_day_id,
                WorkItemRow.outcome_run_id.is_(None),
            )
            .values(outcome_run_id=outcome_run_id)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount:
            self._session.expire_all()
        return result.rowcount or 0

    def _require_outcome(self, tenant: TenantContext, outcome_run_id: UUID) -> OutcomeRunRow:
        row = self._session.scalar(
            select(OutcomeRunRow).where(
                OutcomeRunRow.id == outcome_run_id,
                OutcomeRunRow.business_id == tenant.business_id,
            )
        )
        if row is None:
            raise ValidationAppError("outcome run could not be updated")
        return row


def _money(amount: Decimal | int | str, currency: str) -> str:
    if isinstance(amount, float):
        raise TypeError("money amounts must not use float")
    if not isinstance(amount, (Decimal, str)):
        amount = Decimal(str(amount))
    return Money(amount, currency).to_json()["amount"]


def _to_cash_count(row: CashCountRow) -> CashCount:
    return CashCount(
        id=row.id,
        business_id=row.business_id,
        operational_day_id=row.operational_day_id,
        actor_id=row.actor_id,
        amount=row.amount,
        currency=row.currency,
        source=CashCountSource(row.source),
        counted_at=row.counted_at,
        supersedes_cash_count_id=row.supersedes_cash_count_id,
        superseded_by_id=row.superseded_by_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_snapshot(row: ClosingSnapshotRow) -> ClosingSnapshot:
    return ClosingSnapshot(
        id=row.id,
        business_id=row.business_id,
        operational_day_id=row.operational_day_id,
        cash_count_id=row.cash_count_id,
        actor_id=row.actor_id,
        business_date=row.business_date,
        currency=row.currency,
        sale_count=row.sale_count,
        gross_sales_total=row.gross_sales_total,
        cash_total=row.cash_total,
        card_total=row.card_total,
        transfer_total=row.transfer_total,
        expected_cash=row.expected_cash,
        counted_cash=row.counted_cash,
        cash_difference=row.cash_difference,
        cash_status=CashStatus(row.cash_status),
        closed_at=row.closed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_work_item(row: WorkItemRow) -> WorkItem:
    actor_type = (
        ResolutionActorType(row.resolution_actor_type) if row.resolution_actor_type is not None else None
    )
    code = ResolutionCode(row.resolution_code) if row.resolution_code is not None else None
    return WorkItem(
        id=row.id,
        business_id=row.business_id,
        operational_day_id=row.operational_day_id,
        type=WorkItemType(row.type),
        status=WorkItemStatus(row.status),
        priority=WorkItemPriority(row.priority),
        responsible_party=row.responsible_party,
        reason_code=row.reason_code,
        source=row.source,
        evidence=dict(row.evidence),
        created_at=row.created_at,
        updated_at=row.updated_at,
        resolved_at=row.resolved_at,
        resolution_actor_type=actor_type,
        resolved_by_actor_id=row.resolved_by_actor_id,
        resolution_code=code,
        outcome_run_id=row.outcome_run_id,
    )


def _to_outcome(row: OutcomeRunRow) -> OutcomeRun:
    return OutcomeRun(
        id=row.id,
        business_id=row.business_id,
        operational_day_id=row.operational_day_id,
        outcome_type=row.outcome_type,
        outcome_version=row.outcome_version,
        status=OutcomeRunStatus(row.status),
        owner_type=row.owner_type,
        reason_code=row.reason_code,
        evidence=dict(row.evidence),
        created_at=row.created_at,
        updated_at=row.updated_at,
        ready_at=row.ready_at,
        completed_at=row.completed_at,
        closing_snapshot_id=row.closing_snapshot_id,
    )


def _to_day(row: OperationalDayRow) -> OperationalDay:
    return OperationalDay(
        id=row.id,
        business_id=row.business_id,
        business_date=row.business_date,
        status=OperationalDayStatus(row.status),
        timezone=row.timezone,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _require_tenant(tenant: TenantContext) -> TenantContext:
    if tenant is None:  # type: ignore[truthy-bool]
        raise ValidationAppError("tenant is required")
    if tenant.business_id is None:
        raise TenantScopeViolationError("business is required")
    return tenant
