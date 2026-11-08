"""Visitor analytics endpoints (chief-only).

All endpoints in this router are gated by `require_chief` — a dependency that
returns the current user only when their role is 'chief', and raises 403
otherwise. That keeps the permission check in one place and makes any future
extension (e.g. a per-person 'can view visitors' column) a one-line swap.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app import storage
from app.auth.deps import require_supervisor
from app.db.database import get_db
from app.db.models import AttendanceEvent, Person
from app.schemas import VisitorDay, VisitorSummary
from app.services import attendance_service as svc
from app.services import visitors as visitors_service

router = APIRouter(prefix="/supervisor/visitors", tags=["visitors"])


def require_chief(current: Person = Depends(require_supervisor)) -> Person:
    """Only the chief manager may see visitor analytics.

    Phase 3 gate. If the ability is later extended to select supervisors,
    this is the one place to change (add a flag on Person, or a config list).
    """
    if current.role != "chief":
        raise HTTPException(
            status_code=403,
            detail="Only the chief manager can view visitor analytics.",
        )
    return current


def _default_month() -> tuple[date, date]:
    today = svc.today_local()
    return svc.month_range(today.year, today.month)


def _range(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    if from_date is None or to_date is None:
        return _default_month()
    return from_date, to_date


@router.get("/summary", response_model=VisitorSummary)
def visitor_summary(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    _: Person = Depends(require_chief),
    db: Session = Depends(get_db),
):
    """Totals for the top KPI cards (total / entries / exits)."""
    from_date, to_date = _range(from_date, to_date)
    data = visitors_service.summary(db, from_date, to_date)
    return VisitorSummary(**data)


@router.get("/by-day", response_model=list[VisitorDay])
def visitor_by_day(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    _: Person = Depends(require_chief),
    db: Session = Depends(get_db),
):
    """Day-grouped visitor events for the Visitor Details matrix.

    Each day entry includes its own totals (shown in the collapsed header) and
    the raw event list (rendered when the day is expanded).
    """
    from_date, to_date = _range(from_date, to_date)
    return visitors_service.by_day(db, from_date, to_date)


@router.get("/events/{event_id}/crop")
def visitor_event_crop(
    event_id: int,
    _: Person = Depends(require_chief),
    db: Session = Depends(get_db),
):
    """Serve the face crop for ONE visitor event (chief-only).

    Separate from /supervisor/events/{id}/crop (employee events) so the
    two permission models stay cleanly separated: employee crops are
    dept-scoped, visitor crops are chief-only.
    """
    ev = db.get(AttendanceEvent, event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if not ev.is_visitor or ev.source != "camera":
        raise HTTPException(status_code=404, detail="Not a visitor event")
    if not ev.crop_path:
        raise HTTPException(status_code=404, detail="No crop saved for this event")
    data = storage.load_camera_crop(ev.crop_path)
    if data is None:
        raise HTTPException(status_code=404, detail="Crop no longer available")
    return Response(content=data, media_type="image/jpeg")