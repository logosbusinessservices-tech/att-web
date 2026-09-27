"""Seed a larger, realistic dataset: ~30 employees across departments with a
month of camera attendance and some field (face+GPS) scans, for testing the
analytics dashboards.

Additive and idempotent-ish: employees use the EMP1xx code range so they don't
clash with the small demo set (EMP001..). Re-running clears just this month's
events for those employees before regenerating.

DEV ONLY. Usage:
    backend-api/.venv/Scripts/python.exe -m scripts.seed_bulk
"""

import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.auth.security import hash_password
from app.config import settings
from app.db.database import SessionLocal
from app.db.init_db import init_db
from app.db.models import AttendanceEvent, Department, FaceEmbedding, Person, Station

IST = ZoneInfo(settings.display_timezone)
UTC = ZoneInfo("UTC")
random.seed(7)

DEPARTMENTS = ["Operations", "Signals", "Engineering", "Commercial", "Security", "Medical"]
FIRST = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
         "Ananya", "Diya", "Aadhya", "Kiara", "Saanvi", "Pari", "Anika", "Navya", "Myra", "Sara",
         "Rahul", "Priya", "Neha", "Rohan", "Kavya", "Aditi", "Karthik", "Meera", "Nikhil", "Pooja"]
LAST = ["Sharma", "Reddy", "Rao", "Naidu", "Kumar", "Patel", "Iyer", "Nair", "Das", "Gupta"]
ENTRY_CAMS = ["gate-in-1", "gate-in-2"]
EXIT_CAMS = ["gate-out-1", "gate-out-2"]


def _utc(day, hh, mm):
    return datetime.combine(day, time(hh, mm), tzinfo=IST).astimezone(UTC).replace(tzinfo=None)


def _rand_embedding() -> bytes:
    import numpy as np
    v = np.random.RandomState(random.randint(0, 10_000)).randn(512).astype("float32")
    v /= (np.linalg.norm(v) or 1.0)
    return v.tobytes()


def main():
    init_db()
    db = SessionLocal()
    try:
        # Departments.
        dept_by_name = {}
        for name in DEPARTMENTS:
            d = db.execute(select(Department).where(Department.name == name)).scalar_one_or_none()
            if d is None:
                d = Department(name=name)
                db.add(d); db.flush()
            dept_by_name[name] = d

        stations = db.execute(select(Station)).scalars().all()

        # One supervisor per department (SUP1xx), then employees.
        supervisors = {}
        for i, name in enumerate(DEPARTMENTS, start=1):
            code = f"SUP1{i:02d}"
            p = db.execute(select(Person).where(Person.external_id == code)).scalar_one_or_none()
            if p is None:
                p = Person(external_id=code, display_name=f"{random.choice(FIRST)} {random.choice(LAST)}",
                           role="supervisor")
                db.add(p); db.flush()
            p.department_id = dept_by_name[name].id
            p.role = "supervisor"
            p.password_hash = hash_password("pass123")
            p.home_station_id = stations[i % len(stations)].id if stations else None
            supervisors[name] = p

        today = svc_today()
        m_start = today.replace(day=1)

        created = 0
        for n in range(1, 31):
            code = f"EMP1{n:02d}"
            dept_name = DEPARTMENTS[n % len(DEPARTMENTS)]
            dept = dept_by_name[dept_name]
            field_enabled = (n % 3 == 0)  # ~1/3 can do field attendance

            p = db.execute(select(Person).where(Person.external_id == code)).scalar_one_or_none()
            if p is None:
                p = Person(external_id=code, display_name=f"{FIRST[(n - 1) % len(FIRST)]} {random.choice(LAST)}",
                           role="employee")
                db.add(p); db.flush()
                created += 1
            p.role = "employee"
            p.department_id = dept.id
            p.manager_id = supervisors[dept_name].id
            p.field_scan_enabled = field_enabled
            p.home_station_id = stations[n % len(stations)].id if stations else None
            p.phone = f"+91 9{random.randint(100000000, 999999999)}"
            p.email = f"{code.lower()}@rail.gov.in"
            p.blood_group = random.choice(["O+", "A+", "B+", "AB+", "O-"])
            p.password_hash = hash_password(code)  # default password = code
            p.must_change_password = True
            if field_enabled and not db.execute(
                select(FaceEmbedding).where(FaceEmbedding.person_id == p.id)
            ).first():
                db.add(FaceEmbedding(person_id=p.id, embedding=_rand_embedding(), num_photos=3))

            # Clear this month's events, then regenerate.
            for e in db.execute(select(AttendanceEvent).where(AttendanceEvent.person_id == p.id)).scalars().all():
                if m_start <= _to_local_date(e.event_time) <= today:
                    db.delete(e)
            db.flush()
            _gen_month(db, p, field_enabled, stations, m_start, today)

        db.commit()
        print(f"Seeded {len(DEPARTMENTS)} departments, {len(supervisors)} supervisors, "
              f"30 employees ({created} new) with a month of attendance.")
    finally:
        db.close()


def _gen_month(db, person, field_enabled, stations, start, today):
    d = start
    # A per-person attendance propensity so analytics shows variation.
    reliability = random.uniform(0.75, 0.98)
    while d <= today:
        weekday = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][d.weekday()]
        if weekday not in settings.working_day_set:
            d += timedelta(days=1); continue
        if random.random() > reliability:  # absent
            d += timedelta(days=1); continue

        # ~1/4 of days for a field-enabled person are field days (no camera).
        if field_enabled and random.random() < 0.25 and stations:
            st = db.get(Station, person.home_station_id) or stations[0]
            approved = random.random() < 0.8
            _add_field(db, person, st, d, 9, random.randint(5, 40), "entry", approved)
            _add_field(db, person, st, d, 17, random.randint(30, 59), "exit", approved)
        else:
            _add_cam(db, person, _utc(d, 9, random.randint(5, 40)), "entry")
            if random.random() < 0.7:
                _add_cam(db, person, _utc(d, 13, random.randint(0, 20)), "exit")
                _add_cam(db, person, _utc(d, 13, random.randint(40, 59)), "entry")
            _add_cam(db, person, _utc(d, 18, random.randint(0, 40)), "exit")
        d += timedelta(days=1)


def _add_cam(db, person, when_utc, direction):
    cam = random.choice(ENTRY_CAMS if direction == "entry" else EXIT_CAMS)
    db.add(AttendanceEvent(person_id=person.id, is_visitor=False,
                           similarity=round(random.uniform(0.82, 0.93), 2),
                           camera_label=cam, direction=direction, source="camera",
                           event_time=when_utc, review_status="approved"))


def _add_field(db, person, station, day, hh, mm, direction, approved):
    db.add(AttendanceEvent(
        person_id=person.id, is_visitor=False, similarity=round(random.uniform(0.5, 0.8), 2),
        camera_label=f"field-{station.name}", direction=direction, source="field",
        event_time=_utc(day, hh, mm),
        latitude=station.center_lat, longitude=station.center_lon,
        location_verified=approved,
        review_status="approved" if approved else "pending",
        gps_accuracy_m=round(random.uniform(8, 40), 1), distance_m=round(random.uniform(20, 400), 1),
        nearest_station_id=station.id,
    ))


def svc_today():
    return datetime.now(IST).date()


def _to_local_date(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST).date()


if __name__ == "__main__":
    main()
