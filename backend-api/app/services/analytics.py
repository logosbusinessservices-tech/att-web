"""Analytics aggregations for the supervisor dashboards.

Reuses the same per-day summarizer as everything else (so numbers always match
the tables), then rolls days up into KPIs, time-series trends, per-department
comparisons, and a camera/field source split. All presence-based (no "late").
"""

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AttendanceEvent, Department, Designation, EmploymentType, Person
from app.services import attendance_service as svc
from app.services import corrections


def _types_set(types: str | None) -> set[str] | None:
    if not types:
        return None
    s = {t.strip().lower() for t in types.split(",") if t.strip()}
    return s or None


def _person_in_types(p: Person, tset: set[str]) -> bool:
    if "supervisor" in tset and p.role == "supervisor":
        return True
    if "field" in tset and p.field_scan_enabled:
        return True
    if "office" in tset and p.role == "employee" and not p.field_scan_enabled:
        return True
    return False


def _people(db: Session, department_id: int | None, types: str | None = None) -> list[Person]:
    q = select(Person).where(Person.is_active.is_(True))
    if department_id is not None:
        q = q.where(Person.department_id == department_id)
    people = db.execute(q.order_by(Person.display_name)).scalars().all()
    tset = _types_set(types)
    if tset is None:
        # Default (no type filter): employees only, preserving prior behaviour.
        return [p for p in people if p.role == "employee"]
    return [p for p in people if _person_in_types(p, tset)]


def _person_days(db: Session, person: Person, from_date: date, to_date: date) -> list[dict]:
    events = db.execute(
        select(AttendanceEvent).where(AttendanceEvent.person_id == person.id)
    ).scalars().all()
    ov = corrections.latest_overrides(db, person.id, from_date, to_date)
    return svc.summarize_person(events, from_date, to_date, ov)


def _pct(present: int, absent: int) -> float:
    occurred = present + absent
    return round(100.0 * present / occurred, 1) if occurred else 0.0


def summary(db: Session, from_date: date, to_date: date, department_id: int | None, types: str | None = None) -> dict:
    people = _people(db, department_id, types)
    present = absent = 0
    hours = 0.0
    for p in people:
        for d in _person_days(db, p, from_date, to_date):
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


def trend(db: Session, from_date: date, to_date: date, department_id: int | None, granularity: str, types: str | None = None) -> list[dict]:
    people = _people(db, department_id, types)
    buckets: dict[str, dict] = defaultdict(lambda: {"present": 0, "absent": 0, "hours": 0.0})
    for p in people:
        for d in _person_days(db, p, from_date, to_date):
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


def by_department(db: Session, from_date: date, to_date: date, types: str | None = None,
                  department_id: int | None = None) -> list[dict]:
    dept_names = {d.id: d.name for d in db.execute(select(Department)).scalars().all()}
    agg: dict[int | None, dict] = defaultdict(lambda: {"present": 0, "absent": 0, "hours": 0.0, "head": 0})
    for p in _people(db, department_id, types):
        a = agg[p.department_id]
        a["head"] += 1
        for d in _person_days(db, p, from_date, to_date):
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


def by_attribute(db: Session, from_date: date, to_date: date, attribute: str,
                 types: str | None = None, department_id: int | None = None) -> list[dict]:
    """Attendance rollup grouped by designation or employment type.

    Persons on the 'Other' row group under a single 'Other' bucket; persons with
    no value fall under 'Unassigned'. (The per-person custom text is still kept
    on the account for drill-down; this view is the clean roll-up.)
    """
    if attribute == "designation":
        names = {r.id: r.name for r in db.execute(select(Designation)).scalars().all()}
        attr = "designation_id"
    else:
        names = {r.id: r.name for r in db.execute(select(EmploymentType)).scalars().all()}
        attr = "employment_type_id"
    agg: dict[str, dict] = defaultdict(lambda: {"present": 0, "absent": 0, "hours": 0.0, "head": 0})
    for p in _people(db, department_id, types):
        key = names.get(getattr(p, attr), "Unassigned")
        a = agg[key]
        a["head"] += 1
        for d in _person_days(db, p, from_date, to_date):
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


def source_split(db: Session, from_date: date, to_date: date, department_id: int | None, types: str | None = None) -> dict:
    ids = [p.id for p in _people(db, department_id, types)]
    counts = {"camera": 0, "field": 0, "manual": 0}
    if not ids:
        return counts
    evs = db.execute(
        select(AttendanceEvent).where(AttendanceEvent.person_id.in_(ids))
    ).scalars().all()
    for e in evs:
        local = svc._to_local(e.event_time).date()
        if from_date <= local <= to_date and getattr(e, "review_status", "approved") != "rejected":
            counts[e.source] = counts.get(e.source, 0) + 1
    return counts


def lowest_attendance(db: Session, from_date: date, to_date: date, department_id: int | None, limit: int = 10, types: str | None = None) -> list[dict]:
    """Employees ranked by lowest attendance % (needs-follow-up leaderboard)."""
    rows = []
    for p in _people(db, department_id, types):
        present = absent = 0
        for d in _person_days(db, p, from_date, to_date):
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
