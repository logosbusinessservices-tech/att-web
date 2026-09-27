"""Generate a realistic month of entry/exit attendance for demo/testing.

Creates a department, ensures a couple of employees, and produces camera events
(with direction) across the current month: normal days, a few late arrivals, a
couple of absents, lunch out/in cycles, weekends skipped. Lets us visually verify
hours, entry/exit counts, and late/absent logic before real data flows in.

DEV ONLY. Usage:
    backend-api/.venv/Scripts/python.exe -m scripts.seed_demo
"""

import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from app.config import settings
from app.db.database import SessionLocal
from app.db.init_db import init_db
from app.db.models import AttendanceEvent, Department, Dispute, Person, Station
from app.services import attendance_service as svc

IST = ZoneInfo(settings.display_timezone)
UTC = ZoneInfo("UTC")
random.seed(42)

ENTRY_CAMS = ["gate-in-1", "gate-in-2"]
EXIT_CAMS = ["gate-out-1", "gate-out-2"]


def _utc(day, hh, mm):
    """Build a UTC datetime from an IST wall-clock time on `day`."""
    local = datetime.combine(day, time(hh, mm), tzinfo=IST)
    return local.astimezone(UTC).replace(tzinfo=None)  # store naive-UTC like the pipeline


def _add(db, person_id, when_utc, direction):
    cam = random.choice(ENTRY_CAMS if direction == "entry" else EXIT_CAMS)
    db.add(AttendanceEvent(
        person_id=person_id,
        is_visitor=False,
        similarity=round(random.uniform(0.82, 0.93), 2),
        camera_label=cam,
        direction=direction,
        source="camera",
        event_time=when_utc,
    ))


def _gen_month_for(db, person_id):
    today = svc.today_local()
    start, _ = svc.month_range(today.year, today.month)
    d = start
    while d <= today:
        weekday = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][d.weekday()]
        if weekday not in settings.working_day_set:
            d += timedelta(days=1)
            continue

        roll = random.random()
        if roll < 0.12:              # ~12% absent
            d += timedelta(days=1)
            continue

        late = roll > 0.85           # ~15% late arrival (after 09:40)
        arrive_h, arrive_m = (10, random.randint(0, 30)) if late else (9, random.randint(10, 38))
        _add(db, person_id, _utc(d, arrive_h, arrive_m), "entry")

        # Lunch out/in on most days.
        if random.random() < 0.7:
            _add(db, person_id, _utc(d, 13, random.randint(0, 20)), "exit")
            _add(db, person_id, _utc(d, 13, random.randint(40, 59)), "entry")

        # Leave for the day.
        _add(db, person_id, _utc(d, 18, random.randint(0, 40)), "exit")
        d += timedelta(days=1)


def main():
    init_db()
    db = SessionLocal()
    try:
        # Department
        dept = db.execute(
            select(Department).where(Department.name == "Operations")
        ).scalar_one_or_none()
        if dept is None:
            dept = Department(name="Operations")
            db.add(dept)
            db.flush()

        # Station (with a geofence, used later in Phase 3).
        station = db.execute(
            select(Station).where(Station.name == "Central Station")
        ).scalar_one_or_none()
        if station is None:
            station = Station(
                name="Central Station",
                center_lat=28.6431, center_lon=77.2197, radius_m=250.0,
            )
            db.add(station)
            db.flush()

        # Ensure two demo employees exist and belong to the department.
        profiles = {
            "EMP001": {"name": "Test Employee", "email": "test.employee@rail.gov.in",
                       "phone": "+91 90000 00001", "blood": "O+"},
            "EMP002": {"name": "Asha Rao", "email": "asha.rao@rail.gov.in",
                       "phone": "+91 90000 00002", "blood": "B+"},
        }
        for ext, info in profiles.items():
            p = db.execute(select(Person).where(Person.external_id == ext)).scalar_one_or_none()
            if p is None:
                p = Person(external_id=ext, display_name=info["name"], role="employee")
                db.add(p)
                db.flush()
            p.department_id = dept.id
            p.home_station_id = station.id
            p.email = info["email"]
            p.phone = info["phone"]
            p.blood_group = info["blood"]

            # Clear this month's events for a clean re-run.
            today = svc.today_local()
            m_start, m_end = svc.month_range(today.year, today.month)
            existing = db.execute(
                select(AttendanceEvent).where(AttendanceEvent.person_id == p.id)
            ).scalars().all()
            for e in existing:
                if m_start <= svc._to_local(e.event_time).date() <= m_end:
                    db.delete(e)
            db.flush()
            _gen_month_for(db, p.id)

        # Give the supervisor a profile too, if present.
        sup = db.execute(select(Person).where(Person.external_id == "SUP001")).scalar_one_or_none()
        if sup is not None:
            sup.department_id = dept.id
            sup.home_station_id = station.id
            sup.email = "supervisor@rail.gov.in"
            sup.phone = "+91 90000 00009"
            sup.blood_group = "A+"

        # A couple of sample disputes for the approvals/disputes screens.
        emp1 = db.execute(select(Person).where(Person.external_id == "EMP001")).scalar_one_or_none()
        if emp1 is not None:
            db.execute(delete(Dispute).where(Dispute.person_id == emp1.id))
            today = svc.today_local()
            d1 = (today - timedelta(days=3)).isoformat()
            d2 = (today - timedelta(days=6)).isoformat()
            db.add(Dispute(
                person_id=emp1.id, for_date=d1, status="open",
                message="I entered through gate-2 around 09:15 but the camera missed me.",
            ))
            db.add(Dispute(
                person_id=emp1.id, for_date=d2, status="rejected",
                message="Was late due to traffic.",
                resolution_note="No official-duty record; late stands.",
                resolved_by=sup.id if sup else None,
            ))

        db.commit()
        print("Seeded department 'Operations' and a month of events for EMP001, EMP002.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
