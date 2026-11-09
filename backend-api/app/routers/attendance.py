"""Attendance routes (employee-facing).

Read-only. Turns raw camera/field events into per-day summaries: status
(present/late/absent), hours in office, entry/exit counts — all computed in IST.
Every query is scoped to the logged-in employee (never trusts the client).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db.database import get_db
from app.db.models import AttendanceEvent, Person
from app.schemas import AttendanceEventOut, AttendanceStats, DaySummary
from app.services import attendance_service as svc
from app.services import corrections


router = APIRouter(prefix="/attendance", tags=["attendance"])


def _load_events(db: Session, person_id: int) -> list[AttendanceEvent]:
    return db.execute(
        select(AttendanceEvent).where(AttendanceEvent.person_id == person_id)
    ).scalars().all()


def _default_month() -> tuple[date, date]:
    today = svc.today_local()
    return svc.month_range(today.year, today.month)


@router.get("/summary", response_model=list[DaySummary])
def summary(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per-day summaries for the logged-in employee. Defaults to current month (IST)."""
    if from_date is None or to_date is None:
        from_date, to_date = _default_month()
    if from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be <= to_date")
    events = _load_events(db, current.id)
    ov = corrections.latest_overrides(db, current.id, from_date, to_date)
    return svc.summarize_person(events, from_date, to_date, ov)


@router.get("/stats", response_model=AttendanceStats)
def stats(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rollup counts (present/late/absent/attendance%/total hours). Default: current month."""
    if from_date is None or to_date is None:
        from_date, to_date = _default_month()
    events = _load_events(db, current.id)
    ov = corrections.latest_overrides(db, current.id, from_date, to_date)
    days = svc.summarize_person(events, from_date, to_date, ov)
    return svc.compute_stats(days, from_date, to_date)


@router.get("/day/{day}", response_model=list[AttendanceEventOut])
def day_detail(
    day: date,
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Raw crossings behind a single day (drill-down), newest first, in IST-day terms."""
    events = _load_events(db, current.id)
    same_day = [e for e in events if svc._to_local(e.event_time).date() == day]
    same_day.sort(key=lambda e: e.event_time, reverse=True)
    return same_day


@router.get("/me", response_model=list[AttendanceEventOut])
def my_attendance(
    limit: int = 100,
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Raw attendance events for the logged-in employee, newest first (kept from Phase 0)."""
    rows = db.execute(
        select(AttendanceEvent)
        .where(AttendanceEvent.person_id == current.id)
        .order_by(AttendanceEvent.event_time.desc())
        .limit(limit)
    ).scalars().all()
    return rows

@router.get("/field/status")
def field_status(
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tell the Field Attendance page whether the next scan is entry or exit.

    Looks at the user's LAST attendance event today (any source — camera,
    field, or manual) and flips the direction:
      - last event was 'entry'  → next should be 'exit'
      - last event was 'exit'   → next should be 'entry'
      - no event today          → 'entry' (first scan of the day)

    This includes camera events too, so if someone was already captured
    walking into the office by the gate camera, their field app knows to
    offer an exit rather than a duplicate entry.
    """
    today = svc.today_local()
    events = _load_events(db, current.id)
    todays_events = [e for e in events if svc._to_local(e.event_time).date() == today]
    todays_events.sort(key=lambda e: e.event_time, reverse=True)

    last = todays_events[0] if todays_events else None
    if last is None or last.direction == "exit":
        next_direction = "entry"
    else:
        next_direction = "exit"

    return {
        "next_direction": next_direction,
        "open_entry": last is not None and last.direction == "entry",
    }