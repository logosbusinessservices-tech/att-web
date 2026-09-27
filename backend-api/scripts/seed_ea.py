"""Seed a full, coherent world for testing EVERY feature, including EA mode.

Creates (idempotent — safe to re-run):
  • Departments: Operations, Signals   • Stations with geofences
  • Supervisors:  SUP001 (Operations), SUP002 (Signals)
  • Executive Assistants: EA001 (assists SUP001), EA002 (assists SUP002)
  • Employees EMP001..EMP010 with a month of attendance (present/late/absent),
    some with enrolled faces + field (face+GPS) scans (a few left 'pending')
  • A couple of pending self sign-ups (one older than 3 days → shows dark red)
  • Sample disputes, and one attendance-edit task already delegated to EA001

Login: every account's password is its own code (e.g. SUP001/SUP001,
EA001/EA001, EMP001/EMP001); no forced password change, so you can log straight in.

DEV ONLY. Usage:
    backend-api/.venv/Scripts/python.exe -m scripts.seed_ea
"""

import random
import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import delete, select

from app.auth.security import hash_password
from app.config import settings
from app.db.database import SessionLocal
from app.db.init_db import init_db
from app.db.models import (
    AttendanceEvent,
    DelegatedTask,
    Department,
    Dispute,
    FaceEmbedding,
    Person,
    Station,
)
from app.services import attendance_service as svc

IST = ZoneInfo(settings.display_timezone)
UTC = ZoneInfo("UTC")
random.seed(11)

ENTRY_CAMS = ["gate-in-1", "gate-in-2"]
EXIT_CAMS = ["gate-out-1", "gate-out-2"]


def _utc(day, hh, mm):
    return datetime.combine(day, time(hh, mm), tzinfo=IST).astimezone(UTC).replace(tzinfo=None)


def _rand_embedding() -> bytes:
    v = np.random.RandomState(random.randint(0, 10_000)).randn(512).astype("float32")
    v /= (np.linalg.norm(v) or 1.0)
    return v.tobytes()


def _add_cam(db, person, when_utc, direction):
    cam = random.choice(ENTRY_CAMS if direction == "entry" else EXIT_CAMS)
    db.add(AttendanceEvent(
        person_id=person.id, is_visitor=False,
        similarity=round(random.uniform(0.82, 0.93), 2),
        camera_label=cam, direction=direction, source="camera",
        event_time=when_utc, review_status="approved",
    ))


def _add_field(db, person, station, day, hh, mm, direction, *, approved):
    db.add(AttendanceEvent(
        person_id=person.id, is_visitor=False, similarity=round(random.uniform(0.5, 0.8), 2),
        camera_label=f"field-{station.name}", direction=direction, source="field",
        event_time=_utc(day, hh, mm),
        latitude=station.center_lat, longitude=station.center_lon,
        location_verified=approved,
        review_status="approved" if approved else "pending",
        gps_accuracy_m=round(random.uniform(8, 40), 1),
        distance_m=round(random.uniform(20, 400), 1),
        nearest_station_id=station.id,
    ))


def _clear_month_events(db, person, start, today):
    for e in db.execute(
        select(AttendanceEvent).where(AttendanceEvent.person_id == person.id)
    ).scalars().all():
        d = svc._to_local(e.event_time).date()
        if start <= d <= today:
            db.delete(e)
    db.flush()


def _gen_month(db, person, station, field_enabled, start, today):
    reliability = random.uniform(0.78, 0.97)
    d = start
    while d <= today:
        weekday = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][d.weekday()]
        if weekday not in settings.working_day_set:
            d += timedelta(days=1); continue
        if random.random() > reliability:            # absent
            d += timedelta(days=1); continue

        if field_enabled and station and random.random() < 0.25:
            approved = random.random() < 0.8
            _add_field(db, person, station, d, 9, random.randint(5, 40), "entry", approved=approved)
            _add_field(db, person, station, d, 17, random.randint(30, 59), "exit", approved=approved)
        else:
            late = random.random() > 0.85
            ah, am = (10, random.randint(0, 30)) if late else (9, random.randint(5, 40))
            _add_cam(db, person, _utc(d, ah, am), "entry")
            if random.random() < 0.7:
                _add_cam(db, person, _utc(d, 13, random.randint(0, 20)), "exit")
                _add_cam(db, person, _utc(d, 13, random.randint(40, 59)), "entry")
            _add_cam(db, person, _utc(d, 18, random.randint(0, 40)), "exit")
        d += timedelta(days=1)


def _upsert(db, external_id, **fields):
    p = db.execute(select(Person).where(Person.external_id == external_id)).scalar_one_or_none()
    if p is None:
        p = Person(external_id=external_id, display_name=fields.get("display_name", external_id))
        db.add(p); db.flush()
    for k, v in fields.items():
        setattr(p, k, v)
    # Login just works: universal dev password, no forced change, active account.
    p.password_hash = hash_password("pass123")
    p.must_change_password = False
    p.is_active = True
    p.status = "active"
    db.flush()
    return p


def main():
    init_db()
    db = SessionLocal()
    try:
        today = svc.today_local()
        m_start, _ = svc.month_range(today.year, today.month)

        # ── Departments & stations ──
        def dept(name):
            d = db.execute(select(Department).where(Department.name == name)).scalar_one_or_none()
            if d is None:
                d = Department(name=name); db.add(d); db.flush()
            return d

        ops, signals = dept("Operations"), dept("Signals")

        def station(name, lat, lon):
            s = db.execute(select(Station).where(Station.name == name)).scalar_one_or_none()
            if s is None:
                s = Station(name=name, center_lat=lat, center_lon=lon, radius_m=250.0)
                db.add(s); db.flush()
            return s

        central = station("Central Station", 28.6431, 77.2197)
        signal_cabin = station("Signal Cabin", 28.6510, 77.2310)

        # ── Supervisors ──
        sup1 = _upsert(db, "SUP001", display_name="Ravi Menon", role="supervisor",
                       department_id=ops.id, home_station_id=central.id,
                       email="ravi.menon@rail.gov.in", phone="+91 90000 00009", blood_group="A+")
        sup2 = _upsert(db, "SUP002", display_name="Latha Iyer", role="supervisor",
                       department_id=signals.id, home_station_id=signal_cabin.id,
                       email="latha.iyer@rail.gov.in", phone="+91 90000 00008", blood_group="B+")

        # ── Chief manager: sees every department (incl. supervisors) ──
        _upsert(db, "SUPCPM", display_name="Chief Manager", role="chief",
                department_id=None, home_station_id=None,
                email="chief.manager@rail.gov.in", phone="+91 90000 00099", blood_group="A+")

        # ── Executive Assistants (tracked staff; manager = their supervisor) ──
        ea1 = _upsert(db, "EA001", display_name="Neha Kapoor", role="assistant",
                      department_id=ops.id, home_station_id=central.id, manager_id=sup1.id,
                      email="neha.kapoor@rail.gov.in", phone="+91 90000 00011", blood_group="O+")
        ea2 = _upsert(db, "EA002", display_name="Imran Sheikh", role="assistant",
                      department_id=signals.id, home_station_id=signal_cabin.id, manager_id=sup2.id,
                      email="imran.sheikh@rail.gov.in", phone="+91 90000 00012", blood_group="AB+")

        # ── Employees ──
        NAMES = ["Test Employee", "Asha Rao", "Vikram Nair", "Priya Das", "Karthik Reddy",
                 "Meera Gupta", "Rohan Sharma", "Ananya Patel", "Sai Kumar", "Divya Menon"]
        employees = []
        for n in range(1, 11):
            code = f"EMP{n:03d}"
            in_ops = n <= 6
            d = ops if in_ops else signals
            st = central if in_ops else signal_cabin
            sup = sup1 if in_ops else sup2
            field_enabled = (n % 3 == 0)
            p = _upsert(db, code, display_name=NAMES[n - 1], role="employee",
                        department_id=d.id, home_station_id=st.id, manager_id=sup.id,
                        field_scan_enabled=field_enabled,
                        email=f"{code.lower()}@rail.gov.in",
                        phone=f"+91 90000 {n:05d}",
                        blood_group=random.choice(["O+", "A+", "B+", "AB+", "O-"]))
            if not db.execute(select(FaceEmbedding).where(FaceEmbedding.person_id == p.id)).first():
                db.add(FaceEmbedding(person_id=p.id, embedding=_rand_embedding(), num_photos=3))
            _clear_month_events(db, p, m_start, today)
            _gen_month(db, p, st, field_enabled, m_start, today)
            employees.append((p, st))
        db.flush()

        # ── Also give EAs a little of their own attendance (they're staff too) ──
        for ea, st in ((ea1, central), (ea2, signal_cabin)):
            _clear_month_events(db, ea, m_start, today)
            _gen_month(db, ea, st, False, m_start, today)

        # ── Guaranteed pending field scans in Operations (for approvals/delegation) ──
        # Pick two Operations employees and log an uncertain-location scan today.
        for p, st in employees[:2]:
            _add_field(db, p, central, today, 9, random.randint(10, 30), "entry", approved=False)
        db.flush()

        # ── Pending self sign-ups (for EA onboarding) ──
        db.execute(delete(Person).where(Person.status == "pending"))
        db.flush()
        recent = Person(
            external_id=f"SIGNUP-{uuid.uuid4().hex[:12]}", display_name="Rida Mehta",
            role="employee", status="pending", is_active=False,
            department_id=ops.id, home_station_id=central.id,
            phone="+91 98765 43210", email="rida.mehta@rail.gov.in", blood_group="O+",
        )
        db.add(recent); db.flush()
        overdue = Person(
            external_id=f"SIGNUP-{uuid.uuid4().hex[:12]}", display_name="Karan Singh",
            role="employee", status="pending", is_active=False,
            department_id=signals.id, home_station_id=signal_cabin.id,
            phone="+91 99887 76655", email="karan.singh@rail.gov.in", blood_group="B+",
        )
        db.add(overdue); db.flush()
        # Backdate the second one so it shows the >3-day "delay" (dark red) state.
        overdue.created_at = datetime.now(UTC) - timedelta(days=5)
        db.flush()

        # ── Sample disputes for EMP001 ──
        emp1 = employees[0][0]
        db.execute(delete(Dispute).where(Dispute.person_id == emp1.id))
        db.add(Dispute(
            person_id=emp1.id, for_date=(today - timedelta(days=3)).isoformat(), status="open",
            message="I entered through gate-2 around 09:15 but the camera missed me.",
        ))
        db.flush()

        # ── One attendance-edit task already delegated SUP001 → EA001 ──
        db.execute(delete(DelegatedTask).where(DelegatedTask.status == "open"))
        db.flush()
        # Use a recent working day for EMP001 to fix.
        fix_day = today - timedelta(days=2)
        while fix_day.weekday() == 6:
            fix_day -= timedelta(days=1)
        db.add(DelegatedTask(
            task_type="attendance_edit", supervisor_id=sup1.id, assistant_id=ea1.id,
            comment="Please correct the missing exit for this day.",
            person_id=emp1.id, for_date=fix_day.isoformat(),
        ))

        db.commit()
        print(
            "Seeded EA world.\n"
            "  Chief manager: SUPCPM (sees every department + supervisors)\n"
            "  Supervisors: SUP001 (Operations), SUP002 (Signals)\n"
            "  Assistants:  EA001 (assists SUP001), EA002 (assists SUP002)\n"
            "  Employees:   EMP001..EMP010 with a month of attendance\n"
            "  Pending sign-ups: Rida Mehta (recent), Karan Singh (5 days → delayed)\n"
            "  Pending field scans + 1 delegated attendance task (SUP001 → EA001)\n"
            "  Every account's password is 'pass123' (e.g. SUP001 / pass123)."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
