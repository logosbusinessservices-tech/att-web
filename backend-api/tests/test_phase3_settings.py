"""Onboarding with department/manager selection + fully editable employee settings."""

from app.db.models import Department, Person


def _ops(db):
    return db.query(Department).filter_by(name="Operations").one()


def _signals(db):
    return db.query(Department).filter_by(name="Signals").one()


def test_list_supervisors(client, sup_headers, db_session):
    r = client.get("/supervisor/supervisors", headers=sup_headers)
    assert r.status_code == 200
    codes = {s["external_id"] for s in r.json()}
    assert "SUP001" in codes
    assert all("id" in s for s in r.json())


def test_onboard_with_department_and_manager(client, sup_headers, db_session):
    sup = db_session.query(Person).filter_by(external_id="SUP001").one()
    r = client.post("/supervisor/employees", headers=sup_headers, json={
        "external_id": "EMP500", "display_name": "Dept Hire",
        "department_id": _ops(db_session).id, "manager_id": sup.id,
    })
    assert r.status_code == 200
    assert r.json()["department_name"] == "Operations"
    s = client.get("/supervisor/employees/EMP500/settings", headers=sup_headers).json()
    assert s["manager_name"] == sup.display_name


def test_onboard_manager_must_be_supervisor(client, sup_headers, db_session):
    emp = db_session.query(Person).filter_by(external_id="EMP002").one()
    r = client.post("/supervisor/employees", headers=sup_headers, json={
        "external_id": "EMP501", "display_name": "Bad Mgr", "manager_id": emp.id,
    })
    assert r.status_code == 400


def test_full_settings_edit(client, sup_headers, db_session):
    sup = db_session.query(Person).filter_by(external_id="SUP001").one()
    r = client.patch("/supervisor/employees/EMP001/settings", headers=sup_headers, json={
        "display_name": "Renamed Person",
        "phone": "+91 90000 12345",
        "email": "renamed@rail.gov.in",
        "blood_group": "AB+",
        "manager_id": sup.id,
        "field_scan_enabled": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "Renamed Person"
    assert body["email"] == "renamed@rail.gov.in"
    assert body["blood_group"] == "AB+"
    assert body["field_scan_enabled"] is True
    assert body["manager_name"] == sup.display_name


def test_settings_move_department(client, sup_headers, db_session):
    r = client.patch("/supervisor/employees/EMP001/settings", headers=sup_headers, json={
        "department_id": _signals(db_session).id,
    })
    assert r.status_code == 200
    assert r.json()["department_name"] == "Signals"


def test_settings_invalid_role_rejected(client, sup_headers):
    r = client.patch("/supervisor/employees/EMP001/settings", headers=sup_headers,
                     json={"role": "admin"})
    assert r.status_code == 400
