"""Visitor analytics service.

Visitors are camera events with no matched employee (`is_visitor=True`,
`person_id` NULL). They have no department, no role, and no dedup beyond the
15-second pipeline cooldown — so if a visitor stands around for a while, they
may generate multiple events. Phase 3 shows them raw, grouped by day.

Access to any of this is restricted to the chief manager at the router layer;
this module does not enforce permissions, it only computes.
"""

from collections import defaultdict
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.db.models import AttendanceEvent
from app.services import attendance_service as svc


def _visitor_query(from_date: date, to_date: date):
    """Build the base SELECT for visitor events in the inclusive range.

    Event times are stored as naive UTC. The range is given in LOCAL (IST)
    dates. Converting every event's time to local to compare against those
    dates is expensive in SQL, so we over-fetch by a day either side and let
    the Python loop filter precisely. Volume is tiny (30-50/day * window).
    """
    # Give ourselves a full extra UTC day on each side to cover any IST/UTC
    # midnight-straddle without complex timezone SQL.
    return (
        select(AttendanceEvent)
        .where(AttendanceEvent.is_visitor.is_(True))
        .where(AttendanceEvent.event_time >= _naive_utc_floor(from_date) )
        .where(AttendanceEvent.event_time <= _naive_utc_ceiling(to_date))
    )


def _naive_utc_floor(d: date):
    """A naive UTC datetime guaranteed to be <= the start of `d` in IST."""
    from datetime import datetime, time, timedelta
    # IST is UTC+5:30; start of IST day at 00:00 is UTC-5:30 of the previous day.
    # Subtract a day to cover the straddle; the Python filter trims it back.
    return datetime.combine(d - timedelta(days=1), time(0, 0))


def _naive_utc_ceiling(d: date):
    """A naive UTC datetime guaranteed to be >= the end of `d` in IST."""
    from datetime import datetime, time, timedelta
    return datetime.combine(d + timedelta(days=1), time(23, 59, 59))


def _in_range(local_day: date, from_date: date, to_date: date) -> bool:
    return from_date <= local_day <= to_date


def summary(db: Session, from_date: date, to_date: date) -> dict:
    """Totals for the top KPI cards."""
    rows = db.execute(_visitor_query(from_date, to_date)).scalars().all()
    total = entries = exits = 0
    for e in rows:
        local = svc._to_local(e.event_time).date()
        if not _in_range(local, from_date, to_date):
            continue
        total += 1
        if e.direction == "entry":
            entries += 1
        elif e.direction == "exit":
            exits += 1
    return {
        "total_events": total,
        "entries": entries,
        "exits": exits,
    }


def by_day(db: Session, from_date: date, to_date: date) -> list[dict]:
    """Visitor events grouped by local day.

    Each day entry carries totals (for the collapsed header) and the raw
    event list (for the expanded view). The frontend decides when to render
    the raw rows, but the data comes in one shot either way — payload is
    small enough (one month ~= 1,500 rows) not to warrant lazy fetching.
    """
    rows = db.execute(
        _visitor_query(from_date, to_date).order_by(AttendanceEvent.event_time.desc())
    ).scalars().all()

    buckets: dict[date, list[AttendanceEvent]] = defaultdict(list)
    for e in rows:
        local = svc._to_local(e.event_time).date()
        if _in_range(local, from_date, to_date):
            buckets[local].append(e)

    out: list[dict] = []
    for d in sorted(buckets.keys(), reverse=True):
        day_events = buckets[d]
        day_events.sort(key=lambda ev: ev.event_time, reverse=True)
        entries = sum(1 for e in day_events if e.direction == "entry")
        exits = sum(1 for e in day_events if e.direction == "exit")
        out.append({
            "date": d.isoformat(),
            "total_events": len(day_events),
            "entries": entries,
            "exits": exits,
            "events": day_events,
        })
    return out