"""Seed the production org baseline: the RVNL office location + CPM and EA accounts.

Idempotent. Run AFTER scripts.seed_reference (departments/designations/types).
The real employee roster is loaded separately from a local PII file — never here.

⚠️ Before go-live, edit the constants below with the real people. The office
coordinates are the verified RVNL Secunderabad East pin.

Passwords default to the employee code and must be changed on first login.

Usage:
    backend-api/.venv/Scripts/python.exe -m scripts.seed_prod_accounts
"""

from datetime import datetime, timezone

from sqlalchemy import select

from app.auth.security import hash_password
from app.db.database import SessionLocal
from app.db.init_db import init_db
from app.db.models import Department, Person, Station

# ── RVNL office (field-attendance geofence until the camera pipeline is live) ──
OFFICE = {
    "name": "RVNL Office - Lekha Bhavan, Secunderabad East",
    "lat": 17.436876067091966,
    "lon": 78.5067320570985,
    "radius_m": 150.0,  # office-sized geofence (tighter than the 1 km station default)
}

# ── Launch accounts (replace names as needed; codes are fixed per request) ─────
CPM = {"external_id": "SUPCPM", "name": "CPM (Chief Project Manager)"}
EA = {"external_id": "EA001", "name": "Executive Assistant (Super Admin)"}

# Two throwaway employees for smoke-testing field vs office flows.
TEST_EMPLOYEES = [
    {"external_id": "TESTEMP1", "name": "Test Employee (Field)", "field": True},
    {"external_id": "TESTEMP2", "name": "Test Employee (Office)", "field": False},
]

# Default department for the test employees (if the reference data is seeded).
TEST_DEPARTMENT = "CIVIL"


def _upsert_station(db) -> Station:
    st = db.execute(select(Station).where(Station.name == OFFICE["name"])).scalar_one_or_none()
    if st is None:
        st = Station(name=OFFICE["name"], center_lat=OFFICE["lat"],
                     center_lon=OFFICE["lon"], radius_m=OFFICE["radius_m"])
        db.add(st)
        print(f"  + station {OFFICE['name']}")
    else:
        st.center_lat, st.center_lon, st.radius_m = OFFICE["lat"], OFFICE["lon"], OFFICE["radius_m"]
        print(f"  ~ station {OFFICE['name']} (updated)")
    db.flush()
    return st


def _upsert_account(db, *, external_id: str, name: str, role: str, home_station_id: int,
                    field_scan_enabled: bool = False, department_id: int | None = None) -> None:
    p = db.execute(select(Person).where(Person.external_id == external_id)).scalar_one_or_none()
    if p is None:
        p = Person(external_id=external_id, display_name=name, role=role)
        db.add(p)
        print(f"  + {role} {external_id}")
    else:
        p.display_name, p.role = name, role
        print(f"  ~ {role} {external_id} (updated)")
    p.status = "active"
    p.is_active = True
    p.home_station_id = home_station_id
    p.field_scan_enabled = field_scan_enabled
    if department_id is not None:
        p.department_id = department_id
    # Default password == code; forced change on first login.
    if not p.password_hash:
        p.password_hash = hash_password(external_id)
        p.must_change_password = True
    if p.activated_at is None:
        p.activated_at = datetime.now(timezone.utc)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        office = _upsert_station(db)
        civil = db.execute(
            select(Department).where(Department.name == TEST_DEPARTMENT)
        ).scalar_one_or_none()
        dept_id = civil.id if civil else None
        # CPM is a chief (supervisor + analytics across ALL departments).
        _upsert_account(db, external_id=CPM["external_id"], name=CPM["name"],
                        role="chief", home_station_id=office.id)
        # EA super-admin (global onboarding + account administration).
        _upsert_account(db, external_id=EA["external_id"], name=EA["name"],
                        role="assistant", home_station_id=office.id)
        # Two test employees: one with field permission, one without.
        for t in TEST_EMPLOYEES:
            _upsert_account(db, external_id=t["external_id"], name=t["name"],
                            role="employee", home_station_id=office.id,
                            field_scan_enabled=t["field"], department_id=dept_id)
        db.commit()
        print("Production accounts + office seeded.")
        print(f"  CPM login: {CPM['external_id']} / {CPM['external_id']} (change on first login)")
        print(f"  EA  login: {EA['external_id']} / {EA['external_id']} (change on first login)")
        for t in TEST_EMPLOYEES:
            flag = "field+office" if t["field"] else "office only"
            print(f"  Test login: {t['external_id']} / {t['external_id']} ({flag})")
        if dept_id is None:
            print(f"  (note: department '{TEST_DEPARTMENT}' not found - run seed_reference first "
                  "to assign the test employees a department.)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
