"""Attendance aggregation: raw camera/field events -> meaningful per-day summaries.

All grouping and the "late" check happen in LOCAL time (settings.display_timezone,
i.e. IST), even though events are stored in UTC. A crossing at 20:30 UTC is
02:00 IST the next day, so we convert first, then group.

Hours-in-office and entry/exit counts use event DIRECTION (entry|exit), which the
edge relays per camera (2 entry + 2 exit cameras). We pair each entry with the
next exit chronologically, summing the intervals — so multiple in/out cycles in a
day are handled. Field scans are presence marks: they affect status/first-seen/
sources but never count as "late" and don't form hours pairs on their own.

Override seam: `effective_status` currently just returns the computed status;
Phase 2 will let a supervisor override win here without touching callers.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import settings
from app.db.models import AttendanceEvent

_TZ = ZoneInfo(settings.display_timezone)
_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _to_local(dt: datetime) -> datetime:
    """Convert a stored (UTC) datetime to local IST. Naive datetimes are assumed UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_TZ)


def _local_minutes(dt_local: datetime) -> int:
    """Minutes after local midnight."""
    return dt_local.hour * 60 + dt_local.minute


def _fmt_ist(dt: datetime) -> str:
    """Human 12-hour IST label for anomaly messages, e.g. '9:15 AM'."""
    s = _to_local(dt).strftime("%I:%M %p")
    return s[1:] if s.startswith("0") else s


def _daterange(from_date: date, to_date: date):
    d = from_date
    while d <= to_date:
        yield d
        d += timedelta(days=1)


def _empty_day(d: date) -> dict:
    weekday = _WEEKDAYS[d.weekday()]
    is_working = weekday in settings.working_day_set
    return {
        "date": d.isoformat(),
        "weekday": weekday,
        "is_working_day": is_working,
        "status": "weekend" if not is_working else "absent",
        "first_seen": None,
        "last_seen": None,
        "hours_in_office": 0.0,
        "entry_count": 0,
        "exit_count": 0,
        "sources": [],
        "event_count": 0,
        "adjusted": False,          # true if a supervisor correction touched this day
        "adjustment_reason": None,
        "events": [],               # the crossings behind the day (for inline display)
        "has_anomaly": False,
        "anomalies": [],
    }


def _compute_hours(events_sorted: list[AttendanceEvent]) -> float:
    """Sum entry->exit intervals (hours) using direction, across multiple cycles."""
    open_entry: datetime | None = None
    total = timedelta()
    for e in events_sorted:
        if e.direction == "entry":
            if open_entry is None:
                open_entry = e.event_time
            # consecutive entries (missed exit): keep the first, ignore dupes
        elif e.direction == "exit":
            if open_entry is not None:
                total += e.event_time - open_entry
                open_entry = None
            # exit with no open entry: ignore (missed entry)
    return round(total.total_seconds() / 3600.0, 2)


def _effective_events(events: list[AttendanceEvent]) -> list[AttendanceEvent]:
    """Apply append-only supervisor corrections.

    A manual event with `replaces_event_id` supersedes that original crossing:
    the original is dropped and the manual time/direction is used instead. If a
    crossing was corrected more than once, the latest correction wins.
    """
    # A rejected field scan never counts toward attendance.
    events = [e for e in events if getattr(e, "review_status", "approved") != "rejected"]

    latest_repl: dict[int, AttendanceEvent] = {}
    for e in events:
        rid = getattr(e, "replaces_event_id", None)
        if rid is None:
            continue
        cur = latest_repl.get(rid)
        if cur is None or (e.created_at or datetime.min) >= (cur.created_at or datetime.min):
            latest_repl[rid] = e
    superseded = set(latest_repl.keys())

    kept: list[AttendanceEvent] = []
    for e in events:
        if getattr(e, "voided", False):
            continue  # tombstone: an audit-friendly deletion
        if e.id is not None and e.id in superseded:
            continue  # original replaced by a correction
        rid = getattr(e, "replaces_event_id", None)
        if rid is not None and latest_repl.get(rid) is not e:
            continue  # a stale (older) correction of the same crossing
        kept.append(e)
    return kept


def detect_anomalies(events_sorted: list[AttendanceEvent]) -> list[dict]:
    """Find impossible entry/exit sequences a supervisor should look at.

    Walks the day treating each entry as "going inside" and each exit as "going
    outside". Flags: two entries with no exit between (missed checkout), an exit
    with no matching entry (missed check-in), and an entry never closed by an exit.
    Field scans (direction None) are presence marks and are ignored here.
    """
    anomalies: list[dict] = []
    open_entry: AttendanceEvent | None = None
    for e in events_sorted:
        if e.direction == "entry":
            if open_entry is not None:
                anomalies.append({
                    "type": "missing_exit",
                    "at": e.event_time,
                    "message": (
                        f"Two entries in a row — entered {_fmt_ist(open_entry.event_time)} "
                        f"then {_fmt_ist(e.event_time)} with no exit between. A checkout is missing."
                    ),
                })
            open_entry = e
        elif e.direction == "exit":
            if open_entry is None:
                anomalies.append({
                    "type": "missing_entry",
                    "at": e.event_time,
                    "message": (
                        f"Exit at {_fmt_ist(e.event_time)} has no matching entry before it. "
                        f"A check-in is missing."
                    ),
                })
            else:
                open_entry = None
    if open_entry is not None:
        anomalies.append({
            "type": "unclosed_entry",
            "at": open_entry.event_time,
            "message": f"Entry at {_fmt_ist(open_entry.event_time)} was never closed by an exit.",
        })
    return anomalies


def _summarize_one_day(d: date, events: list[AttendanceEvent], today: date) -> dict:
    day = _empty_day(d)

    # Future days are neither present nor absent yet.
    if d > today:
        day["status"] = "upcoming" if day["is_working_day"] else "weekend"
        return day

    if not events:
        return day

    events_sorted = sorted(events, key=lambda e: e.event_time)
    first, last = events_sorted[0], events_sorted[-1]

    day["first_seen"] = first.event_time
    day["last_seen"] = last.event_time
    day["event_count"] = len(events_sorted)
    day["entry_count"] = sum(1 for e in events_sorted if e.direction == "entry")
    day["exit_count"] = sum(1 for e in events_sorted if e.direction == "exit")
    day["hours_in_office"] = _compute_hours(events_sorted)
    day["sources"] = sorted({e.source for e in events_sorted})
    day["events"] = events_sorted
    if "manual" in day["sources"]:
        day["adjusted"] = True

    anomalies = detect_anomalies(events_sorted)
    if d >= today:  # today may still be "inside" — an open entry isn't an error yet
        anomalies = [a for a in anomalies if a["type"] != "unclosed_entry"]
    day["anomalies"] = anomalies
    day["has_anomaly"] = bool(anomalies)

    # ── Status ──
    # Presence-based only: any crossing on a working day = present. We count hours,
    # not arrival time, so there is no "late" status.
    if not day["is_working_day"]:
        day["status"] = "weekend"
        return day
    day["status"] = "present"
    return day


def _apply_override(day: dict, override: dict | None) -> dict:
    """Layer a supervisor override on top of the computed day (Phase 2).

    The override may force the displayed status; it always marks the day adjusted.
    Raw events (and thus hours/counts) are untouched here — hours are corrected
    separately by injecting manual events upstream.
    """
    if override is None:
        return day
    day["adjusted"] = True
    if override.get("reason"):
        day["adjustment_reason"] = override["reason"]
    if override.get("new_status"):
        day["status"] = override["new_status"]
    return day


def effective_status(day: dict) -> str:
    """Authoritative status for rollups (override already baked into day[\"status\"])."""
    return day["status"]


def summarize_person(
    events: list[AttendanceEvent],
    from_date: date,
    to_date: date,
    overrides: dict[str, dict] | None = None,
) -> list[dict]:
    """One summary per day in [from_date, to_date] for a single person.

    Absent/weekend days (no events) are included so the calendar is complete.
    `overrides` maps ISO-date -> {"new_status", "reason"} (Phase 2 supervisor
    corrections). Returned newest-first.
    """
    by_day: dict[date, list[AttendanceEvent]] = defaultdict(list)
    for e in _effective_events(events):
        local_day = _to_local(e.event_time).date()
        if from_date <= local_day <= to_date:
            by_day[local_day].append(e)

    today = today_local()
    overrides = overrides or {}
    summaries = []
    for d in _daterange(from_date, to_date):
        day = _summarize_one_day(d, by_day.get(d, []), today)
        day = _apply_override(day, overrides.get(d.isoformat()))
        summaries.append(day)
    summaries.sort(key=lambda s: s["date"], reverse=True)
    return summaries


def compute_stats(day_summaries: list[dict], from_date: date, to_date: date) -> dict:
    """Rollup counts for the header cards."""
    present = sum(1 for d in day_summaries if effective_status(d) == "present")
    absent = sum(1 for d in day_summaries if effective_status(d) == "absent")
    # Working days that have actually occurred (exclude future 'upcoming' days).
    working = sum(
        1 for d in day_summaries if d["is_working_day"] and d["status"] != "upcoming"
    )
    total_hours = round(sum(d["hours_in_office"] for d in day_summaries), 2)
    # Present% = present / working days.
    pct = round(100.0 * present / working, 1) if working else 0.0
    return {
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "present": present,
        "absent": absent,
        "working_days": working,
        "attendance_pct": pct,
        "total_hours": total_hours,
    }


def month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) - timedelta(days=1) if month == 12 else date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def today_local() -> date:
    return datetime.now(_TZ).date()
