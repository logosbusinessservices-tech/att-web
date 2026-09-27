"""Shared pytest fixtures.

Every test runs against an ISOLATED, fresh SQLite database in a temp folder, so
tests never touch the dev attendance.db. We override the app's `get_db`
dependency to use this throwaway engine, seed a small fixed dataset, and hand
back a TestClient plus helper login tokens.
"""

import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.security import hash_password
from app.config import settings
from app.db.database import Base, get_db
from app.db.models import (
    AttendanceEvent,
    Department,
    Person,
    Station,
)
from app.main import app

IST = ZoneInfo(settings.display_timezone)
UTC = ZoneInfo("UTC")


def _utc(d: date, hh: int, mm: int) -> datetime:
    """IST wall-clock on `d` -> naive-UTC datetime (the pipeline storage form)."""
    local = datetime.combine(d, time(hh, mm), tzinfo=IST)
    return local.astimezone(UTC).replace(tzinfo=None)


def _recent_working_day(offset_from_today: int) -> date:
    """A working day roughly `offset_from_today` days ago (skips Sundays)."""
    d = date.today() - timedelta(days=offset_from_today)
    while d.weekday() == 6:  # Sunday not a working day
        d -= timedelta(days=1)
    return d


@pytest.fixture()
def db_session(tmp_path):
    """A fresh SQLite DB per test, wired into the app via dependency override."""
    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file}", connect_args={"check_same_thread": False}, future=True
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    def _override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    session = TestingSession()
    try:
        _seed(session)
        yield session
    finally:
        session.close()
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _seed(db):
    """Fixed, predictable dataset the tests assert against."""
    dept = Department(name="Operations")
    other = Department(name="Signals")
    db.add_all([dept, other])
    db.flush()

    station = Station(name="Central Station", center_lat=28.6431, center_lon=77.2197, radius_m=250.0)
    db.add(station)
    db.flush()

    pw = hash_password("pass123")
    emp1 = Person(
        external_id="EMP001", display_name="Test Employee", role="employee",
        department_id=dept.id, home_station_id=station.id, password_hash=pw,
        email="test.employee@rail.gov.in", phone="+91 90000 00001", blood_group="O+",
    )
    emp2 = Person(
        external_id="EMP002", display_name="Asha Rao", role="employee",
        department_id=dept.id, home_station_id=station.id, password_hash=pw, blood_group="B+",
    )
    # Employee in a DIFFERENT department, to test dept-scoped authority.
    emp3 = Person(
        external_id="EMP003", display_name="Signals Person", role="employee",
        department_id=other.id, password_hash=pw,
    )
    sup = Person(
        external_id="SUP001", display_name="Test Supervisor", role="supervisor",
        department_id=dept.id, home_station_id=station.id, password_hash=pw, blood_group="A+",
    )
    db.add_all([emp1, emp2, emp3, sup])
    db.flush()

    # Executive Assistant for SUP001 (tracked staff; manager = their supervisor).
    ea = Person(
        external_id="EA001", display_name="Test Assistant", role="assistant",
        department_id=dept.id, home_station_id=station.id, password_hash=pw,
        manager_id=sup.id, blood_group="O+",
    )
    # A second supervisor with no EA, to test the "no EA to delegate to" guard.
    sup2 = Person(
        external_id="SUP002", display_name="Other Supervisor", role="supervisor",
        department_id=other.id, password_hash=pw,
    )
    db.add_all([ea, sup2])
    db.flush()

    # Chief manager: no department; sees every department incl. supervisors.
    chief = Person(
        external_id="SUPCPM", display_name="Chief Manager", role="chief",
        department_id=None, password_hash=pw,
    )
    db.add(chief)
    db.flush()

    # Operations employees report to SUP001 (drives the EA notification routing).
    emp1.manager_id = sup.id
    emp2.manager_id = sup.id
    db.flush()

    # ── Deterministic attendance for EMP001 ──
    # d_present: on-time (09:15 in, 18:00 out) -> present, ~8.75h
    d_present = _recent_working_day(2)
    # d_late: arrives 10:05 -> present (arrival time no longer affects status)
    d_late = _recent_working_day(4)
    # d_absent: no events -> absent
    d_absent = _recent_working_day(6)

    db.add_all([
        AttendanceEvent(person_id=emp1.id, camera_label="gate-in-1", direction="entry",
                        source="camera", event_time=_utc(d_present, 9, 15)),
        AttendanceEvent(person_id=emp1.id, camera_label="gate-out-1", direction="exit",
                        source="camera", event_time=_utc(d_present, 18, 0)),
        AttendanceEvent(person_id=emp1.id, camera_label="gate-in-2", direction="entry",
                        source="camera", event_time=_utc(d_late, 10, 5)),
        AttendanceEvent(person_id=emp1.id, camera_label="gate-out-2", direction="exit",
                        source="camera", event_time=_utc(d_late, 17, 30)),
    ])
    db.commit()

    # Stash the key dates on the module for tests to import.
    _seed.dates = {
        "present": d_present.isoformat(),
        "late": d_late.isoformat(),
        "absent": d_absent.isoformat(),
    }


@pytest.fixture()
def client(db_session):
    return TestClient(app)


def _token(client, username, password="pass123"):
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
def emp_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'EMP001')}"}


@pytest.fixture()
def emp2_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'EMP002')}"}


@pytest.fixture()
def emp3_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'EMP003')}"}


@pytest.fixture()
def sup_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'SUP001')}"}


@pytest.fixture()
def sup2_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'SUP002')}"}


@pytest.fixture()
def ea_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'EA001')}"}


@pytest.fixture()
def chief_headers(client):
    return {"Authorization": f"Bearer {_token(client, 'SUPCPM')}"}


@pytest.fixture()
def seed_dates(db_session):
    return _seed.dates
