"""Analytics aggregations for the supervisor dashboards.

Reuses the same per-day summarizer as everything else (so numbers always match
the tables), then rolls days up into KPIs, time-series trends, per-department
comparisons, and a camera/field source split. All presence-based (no "late").

Filter model (Phase 1 refactor):
  - `roles`:   which PEOPLE to include (employee | supervisor). Defaults to
               "employee" for a department supervisor; chief sees both.
  - `sources`: which CAPTURE TYPES count toward presence (camera | field |
               manual). A person is "present" on a day if AT LEAST ONE of their
               events on that day has a matching source. Defaults to all three.

Backward compatibility:
  The old `types` parameter (field | office | supervisor) is still accepted.
  It maps to roles only — "field" and "office" both become "employee". The new
  `sources` filter is independent and not derivable from `types`.
"""

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AttendanceEvent, Department, Designation, EmploymentType, Person
from app.services import attendance_service as svc
from app.services import corrections


# ── Filter normalization ────────────────────────────────────────────────────
_ALL_SOURCES = {"camera", "field", "manual"}
_VALID_ROLES = {"employee", "supervisor"}


def _roles_set(roles: str | None, types: str | None = None) -> set[str] | None:
    """Parse the roles filter. Back-compat: if `roles` is empty but legacy
    `types` was sent, translate it (field/office -> employee, supervisor stays).

    Returns None when nothing was specified (callers apply their own default).
    """
    # Prefer the new `roles` param when present.
    if roles:
        s = {r.strip().lower() for r in roles.split(",") if r.strip()}
        s = s & _VALID_ROLES
        return s or None
    # Legacy translation.
    if types:
        s = set()
        for t in types.split(","):
            t = t.strip().lower()
            if t in ("field", "office", "employee"):
                s.add("employee")
            elif t == "supervisor":
                s.add("supervisor")
        return s or None
    return None


def _sources_set(sources: str | None) -> set[str]:
    """Parse the capture-type filter. Empty / missing / all-unknown means ALL
    sources count (the sensible default — "don't filter by source")."""
    if not sources:
        return set(_ALL_SOURCES)
    s = {x.strip().lower() for x in sources.split(",") if x.strip()}
    s = s & _ALL_SOURCES
    # Auto-revert when nothing valid was picked (prevents an "all-zero" dashboard
    # from a stale URL or an empty UI state).
    return s if s else set(_ALL_SOURCES)


def _person_matches_roles(p: Person, roles: set[str]) -> bool:
    """A person is in scope if their role is one of the selected roles."""
    return p.role in roles


# ── People list ─────────────────────────────────────────────────────────────
def _people(
    db: Session,
    department_id: int | None,
    types: str | None = None,          # legacy, kept for signature compat
    roles: str | None = None,          # NEW
) -> list[Person]:
    """Return active persons scoped to a department, filtered by role.

    IMPORTANT: this function no longer filters by `field_scan_enabled`. The
    source filter (camera/field/manual) is applied downstream against the
    person's actual events on each day, not against their permissions.
    """
    q = select(Person).where(Person.is_active.is_(True))
    if department_id is not None:
        q = q.where(Person.department_id == department_id)
    people = db.execute(q.order_by(Person.display_name)).scalars().all()
    rset = _roles_set(roles, types)
    if rset is None:
        # Default (no role filter): employees only, preserving prior behaviour
        # of the attendance screens.
        return [p for p in people if p.role == "employee"]
    return [p for p in people if _person_matches_roles(p, rset)]


# ── Per-person per-day summaries, filtered by capture type ──────────────────
def _day_matches_sources(day: dict, sources: set[str]) -> bool:
    """A day "counts" under a source filter if at least one of its events was
    captured through one of the selected sources.

    Days with zero events (absent/weekend/upcoming) pass through unchanged — the
    source filter only narrows the "present" side.
    """
    if sources == _ALL_SOURCES:
        return True
    if not day.get("sources"):
        return True
    return any(s in sources for s in day["sources"])


def _person_days(
    db: Session,
    person: Person,
    from_date: date,
    to_date: date,
    sources: set[str] | None = None,
) -> list[dict]:
    """Summarize one person's days, then "downgrade" days whose events don't
    match the capture filter: the present day becomes absent (its hours go to
    zero too, so they don't leak into totals).

    Weekend / upcoming days are never touched by this filter.
    """
    events = db.execute(
        select(AttendanceEvent).where(AttendanceEvent.person_id == person.id)
    ).scalars().all()
    ov = corrections.latest_overrides(db, person.id, from_date, to_date)
    days = svc.summarize_person(events, from_date, to_date, ov)
    if sources is None or sources == _ALL_SOURCES:
        return days
    filtered: list[dict] = []
    for d in days:
        if d["status"] == "present" and not _day_matches_sources(d, sources):
            # The day's events were all captured through a filtered-out source;
            # for this filter view, treat the day as absent with zero hours.
            d = {**d,
                 "status": "absent",
                 "hours_in_office": 0.0,
                 "entry_count": 0,
                 "exit_count": 0}
        filtered.append(d)
    return filtered


# ── Helpers ─────────────────────────────────────────────────────────────────
def _pct(present: int, absent: int) -> float:
    occurred = present + absent
    return round(100.0 * present / occurred, 1) if occurred else 0.0


# ── Rollups ─────────────────────────────────────────────────────────────────
def summary(
    db: Session,
    from_date: date,
    to_date: date,
    department_id: int | None,
    types: str | None = None,
    roles: str | None = None,
    sources: str | None = None,
) -> dict:
    srcs = _sources_set(sources)
    people = _people(db, department_id, types, roles)
    present = absent = 0
    hours = 0.0
    for p in people:
        for d in _person_days(db, p, from_date, to_date, srcs):
            if d["status"] == "present":
                present += 1
            elif d["status"] == "absent":
                absent += 1
            hours += d["hours_in_office"]
    return {
        "present": present,
        "absent": absent,
        "total_hours": round(hours, 2),
        "attendance_pct": _pct(present, absent),
        "active_employees": len(people),
    }


def _bucket(iso_date: str, granularity: str) -> str:
    y, m, dd = (int(x) for x in iso_date.split("-"))
    if granularity == "month":
        return f"{y:04d}-{m:02d}"
    if granularity == "week":
        iso = date(y, m, dd).isocalendar()
        return f"{iso[0]:04d}-W{iso[1]:02d}"
    return iso_date  # day


def trend(
    db: Session,
    from_date: date,
    to_date: date,
    department_id: int | None,
    granularity: str,
    types: str | None = None,
    roles: str | None = None,
    sources: str | None = None,
) -> list[dict]:
    srcs = _sources_set(sources)
    people = _people(db, department_id, types, roles)
    buckets: dict[str, dict] = defaultdict(lambda: {"present": 0, "absent": 0, "hours": 0.0})
    for p in people:
        for d in _person_days(db, p, from_date, to_date, srcs):
            if d["status"] not in ("present", "absent"):
                continue
            b = buckets[_bucket(d["date"], granularity)]
            if d["status"] == "present":
                b["present"] += 1
            else:
                b["absent"] += 1
            b["hours"] += d["hours_in_office"]
    out = []
    for key in sorted(buckets):
        b = buckets[key]
        out.append({
            "period": key,
            "present": b["present"],
            "absent": b["absent"],
            "hours": round(b["hours"], 2),
            "attendance_pct": _pct(b["present"], b["absent"]),
        })
    return out


def by_department(
    db: Session,
    from_date: date,
    to_date: date,
    types: str | None = None,
    department_id: int | None = None,
    roles: str | None = None,
    sources: str | None = None,
) -> list[dict]:
    srcs = _sources_set(sources)
    dept_names = {d.id: d.name for d in db.execute(select(Department)).scalars().all()}
    agg: dict[int | None, dict] = defaultdict(lambda: {"present": 0, "absent": 0, "hours": 0.0, "head": 0})
    for p in _people(db, department_id, types, roles):
        a = agg[p.department_id]
        a["head"] += 1
        for d in _person_days(db, p, from_date, to_date, srcs):
            if d["status"] == "present":
                a["present"] += 1
            elif d["status"] == "absent":
                a["absent"] += 1
            a["hours"] += d["hours_in_office"]
    out = []
    for did, a in agg.items():
        out.append({
            "department_id": did,
            "name": dept_names.get(did, "Unassigned"),
            "present": a["present"],
            "absent": a["absent"],
            "total_hours": round(a["hours"], 2),
            "attendance_pct": _pct(a["present"], a["absent"]),
            "headcount": a["head"],
        })
    out.sort(key=lambda x: x["name"] or "")
    return out


def by_attribute(
    db: Session,
    from_date: date,
    to_date: date,
    attribute: str,
    types: str | None = None,
    department_id: int | None = None,
    roles: str | None = None,
    sources: str | None = None,
) -> list[dict]:
    """Attendance rollup grouped by designation or employment type.

    Persons on the 'Other' row group under a single 'Other' bucket; persons with
    no value fall under 'Unassigned'. (The per-person custom text is still kept
    on the account for drill-down; this view is the clean roll-up.)
    """
    srcs = _sources_set(sources)
    if attribute == "designation":
        names = {r.id: r.name for r in db.execute(select(Designation)).scalars().all()}
        attr = "designation_id"
    else:
        names = {r.id: r.name for r in db.execute(select(EmploymentType)).scalars().all()}
        attr = "employment_type_id"
    agg: dict[str, dict] = defaultdict(lambda: {"present": 0, "absent": 0, "hours": 0.0, "head": 0})
    for p in _people(db, department_id, types, roles):
        key = names.get(getattr(p, attr), "Unassigned")
        a = agg[key]
        a["head"] += 1
        for d in _person_days(db, p, from_date, to_date, srcs):
            if d["status"] == "present":
                a["present"] += 1
            elif d["status"] == "absent":
                a["absent"] += 1
            a["hours"] += d["hours_in_office"]
    out = [
        {
            "key": key,
            "present": a["present"],
            "absent": a["absent"],
            "total_hours": round(a["hours"], 2),
            "attendance_pct": _pct(a["present"], a["absent"]),
            "headcount": a["head"],
        }
        for key, a in agg.items()
    ]
    out.sort(key=lambda x: x["key"] or "")
    return out


def source_split(
    db: Session,
    from_date: date,
    to_date: date,
    department_id: int | None,
    types: str | None = None,
    roles: str | None = None,
    sources: str | None = None,
) -> dict:
    """Raw event counts by source, respecting the capture-type filter.

    When all capture types are selected (the default), every source appears.
    When the user narrows to, say, Camera only, the Field and Manual counts
    report 0 so the pie chart reflects the current view instead of contradicting
    the KPIs above it.
    """
    srcs = _sources_set(sources)
    ids = [p.id for p in _people(db, department_id, types, roles)]
    counts = {"camera": 0, "field": 0, "manual": 0}
    if not ids:
        return counts
    evs = db.execute(
        select(AttendanceEvent).where(AttendanceEvent.person_id.in_(ids))
    ).scalars().all()
    for e in evs:
        local = svc._to_local(e.event_time).date()
        if not (from_date <= local <= to_date):
            continue
        if getattr(e, "review_status", "approved") == "rejected":
            continue
        if e.source not in srcs:
            continue
        counts[e.source] = counts.get(e.source, 0) + 1
    return counts


def lowest_attendance(
    db: Session,
    from_date: date,
    to_date: date,
    department_id: int | None,
    limit: int = 10,
    types: str | None = None,
    roles: str | None = None,
    sources: str | None = None,
) -> list[dict]:
    """Employees ranked by lowest attendance % (needs-follow-up leaderboard)."""
    srcs = _sources_set(sources)
    rows = []
    for p in _people(db, department_id, types, roles):
        present = absent = 0
        for d in _person_days(db, p, from_date, to_date, srcs):
            if d["status"] == "present":
                present += 1
            elif d["status"] == "absent":
                absent += 1
        if present + absent == 0:
            continue
        rows.append({
            "external_id": p.external_id,
            "display_name": p.display_name,
            "attendance_pct": _pct(present, absent),
            "present": present,
            "absent": absent,
        })
    rows.sort(key=lambda x: x["attendance_pct"])
    return rows[:limit]