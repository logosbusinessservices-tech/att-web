"""Supervisor analytics endpoints powering the interactive dashboards.

Role-guarded. Optional department_id filter mirrors the overview table. All
figures come from the same day summarizer, so charts and tables always agree.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_supervisor
from app.db.database import get_db
from app.db.models import AttendanceEvent, Person
from app.schemas import (
    AnalyticsSummary,
    DeptStat,
    DimensionStat,
    LowAttendanceRow,
    SourceSplit,
    TrendPoint,
)
from app.services import analytics
from app.services import attendance_service as svc

router = APIRouter(prefix="/supervisor/analytics", tags=["analytics"])


def _range(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    if from_date is None or to_date is None:
        today = svc.today_local()
        return svc.month_range(today.year, today.month)
    return from_date, to_date


def _is_chief(current: Person) -> bool:
    return current.role == "chief"


def _dept_scope(current: Person, requested: int | None) -> int | None:
    """Chief sees any/all departments; a supervisor is locked to their own."""
    return requested if _is_chief(current) else current.department_id


def _mgmt_types(current: Person, types: str | None) -> str | None:
    if types is None and _is_chief(current):
        return "office,field,supervisor"
    return types


@router.get("/summary", response_model=AnalyticsSummary)
def analytics_summary(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    department_id: int | None = Query(default=None),
    types: str | None = Query(default=None),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    from_date, to_date = _range(from_date, to_date)
    department_id = _dept_scope(current, department_id)
    types = _mgmt_types(current, types)
    data = analytics.summary(db, from_date, to_date, department_id, types)

    # Pending field approvals in scope (own department, or all for the chief).
    q = (
        select(AttendanceEvent.id)
        .join(Person, AttendanceEvent.person_id == Person.id)
        .where(
            AttendanceEvent.source == "field",
            AttendanceEvent.review_status == "pending",
        )
    )
    if not _is_chief(current):
        if current.department_id is None:
            return AnalyticsSummary(**data, pending_field_approvals=0)
        q = q.where(Person.department_id == current.department_id)
    pending = len(db.execute(q).all())
    return AnalyticsSummary(**data, pending_field_approvals=pending)


@router.get("/trend", response_model=list[TrendPoint])
def analytics_trend(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    department_id: int | None = Query(default=None),
    granularity: str = Query(default="day"),
    types: str | None = Query(default=None),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    if granularity not in ("day", "week", "month"):
        granularity = "day"
    from_date, to_date = _range(from_date, to_date)
    department_id = _dept_scope(current, department_id)
    types = _mgmt_types(current, types)
    return analytics.trend(db, from_date, to_date, department_id, granularity, types)


@router.get("/by-department", response_model=list[DeptStat])
def analytics_by_department(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    types: str | None = Query(default=None),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    from_date, to_date = _range(from_date, to_date)
    # Non-chief managers only see their own department's row.
    department_id = None if _is_chief(current) else current.department_id
    types = _mgmt_types(current, types)
    return analytics.by_department(db, from_date, to_date, types, department_id)


@router.get("/by-attribute", response_model=list[DimensionStat])
def analytics_by_attribute(
    attribute: str = Query(..., description="designation | employment_type"),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    department_id: int | None = Query(default=None),
    types: str | None = Query(default=None),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Attendance grouped by designation or employment type (Other = one bucket)."""
    if attribute not in ("designation", "employment_type"):
        raise HTTPException(status_code=400, detail="Invalid attribute")
    from_date, to_date = _range(from_date, to_date)
    department_id = _dept_scope(current, department_id)
    types = _mgmt_types(current, types)
    return analytics.by_attribute(db, from_date, to_date, attribute, types, department_id)


@router.get("/source-split", response_model=SourceSplit)
def analytics_source_split(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    department_id: int | None = Query(default=None),
    types: str | None = Query(default=None),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    from_date, to_date = _range(from_date, to_date)
    department_id = _dept_scope(current, department_id)
    types = _mgmt_types(current, types)
    return SourceSplit(**analytics.source_split(db, from_date, to_date, department_id, types))


@router.get("/lowest-attendance", response_model=list[LowAttendanceRow])
def analytics_lowest(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    department_id: int | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    types: str | None = Query(default=None),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    from_date, to_date = _range(from_date, to_date)
    department_id = _dept_scope(current, department_id)
    types = _mgmt_types(current, types)
    return analytics.lowest_attendance(db, from_date, to_date, department_id, limit, types)
