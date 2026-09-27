"""Department scoping (supervisor) vs. chief-manager global view, and field
attendance notifications for the employee + their supervisor's EA."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import settings
from app.db.models import AttendanceEvent, Notification, Person, Station

IST = ZoneInfo(settings.display_timezone)
UTC = ZoneInfo("UTC")


def _utc(d: date, hh: int, mm: int) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=IST).astimezone(UTC).replace(tzinfo=None)


def _pending_field(db, external_id) -> int:
    p = db.query(Person).filter_by(external_id=external_id).one()
    st = db.query(Station).first()
    ev = AttendanceEvent(
        person_id=p.id, camera_label="field-x", direction="entry", source="field",
        event_time=_utc(date.today(), 9, 15), review_status="pending",
        nearest_station_id=st.id if st else None,
    )
    db.add(ev); db.commit()
    return ev.id


# ── Department scoping ───────────────────────────────────────────────────────
def test_overview_scoped_to_supervisor_department(client, sup_headers):
    rows = client.get("/supervisor/attendance/overview", headers=sup_headers).json()
    ids = {r["external_id"] for r in rows}
    # Operations employees only; the Signals employee EMP003 is excluded.
    assert "EMP001" in ids and "EMP002" in ids
    assert "EMP003" not in ids


def test_employee_summary_other_department_forbidden(client, sup_headers):
    # EMP003 is in Signals; the Operations supervisor can't view them.
    r = client.get("/supervisor/employee/EMP003/summary", headers=sup_headers)
    assert r.status_code == 403


def test_supervisor_cannot_widen_scope_with_param(client, sup_headers, db_session):
    from app.db.models import Department
    signals = db_session.query(Department).filter_by(name="Signals").one().id
    # Even asking for Signals explicitly, a supervisor still only gets their dept.
    rows = client.get(f"/supervisor/attendance/overview?department_id={signals}", headers=sup_headers).json()
    assert all(r["external_id"] != "EMP003" for r in rows)


# ── Chief manager sees everything ────────────────────────────────────────────
def test_chief_sees_all_departments_and_supervisors(client, chief_headers):
    rows = client.get("/supervisor/attendance/overview", headers=chief_headers).json()
    ids = {r["external_id"] for r in rows}
    # Both departments' employees AND supervisors are visible to the chief.
    assert {"EMP001", "EMP003"} <= ids
    assert {"SUP001", "SUP002"} <= ids


def test_chief_by_department_spans_all(client, chief_headers):
    rows = client.get("/supervisor/analytics/by-department", headers=chief_headers).json()
    names = {d["name"] for d in rows}
    assert {"Operations", "Signals"} <= names


def test_chief_can_view_any_employee_summary(client, chief_headers):
    r = client.get("/supervisor/employee/EMP003/summary", headers=chief_headers)
    assert r.status_code == 200


def test_chief_field_approvals_span_all_departments(client, chief_headers, db_session):
    _pending_field(db_session, "EMP001")   # Operations
    _pending_field(db_session, "EMP003")   # Signals
    rows = client.get("/supervisor/field/approvals", headers=chief_headers).json()
    ids = {r["external_id"] for r in rows}
    assert {"EMP001", "EMP003"} <= ids


# ── Field notifications (employee + EA) ──────────────────────────────────────
def test_pending_field_notifies_employee_and_ea(client, emp_headers, ea_headers, db_session, monkeypatch):
    # Enable field for EMP001 and mock face/geo so the scan lands 'pending'.
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    emp1.field_scan_enabled = True
    db_session.commit()

    import numpy as np
    from app.services import field as field_svc
    vec = np.ones(512, dtype=np.float32); vec /= np.linalg.norm(vec)
    monkeypatch.setattr(field_svc, "_enrolled_blob", lambda db, pid: vec.tobytes())
    monkeypatch.setattr(field_svc, "decode_image_bytes", lambda b: object())
    monkeypatch.setattr(field_svc, "embed_largest_face", lambda img: (vec, 0.99))
    monkeypatch.setattr(field_svc, "verify", lambda emb, blob: (True, 0.99))

    # No GPS → uncertain location → pending.
    r = client.post("/attendance/field", headers=emp_headers,
                    data={"direction": "entry"},
                    files={"selfie": ("s.jpg", b"x", "image/jpeg")})
    assert r.status_code == 200, r.text
    assert r.json()["review_status"] == "pending"

    # Employee sees a 'pending' notification.
    emp_notifs = client.get("/notifications", headers=emp_headers).json()
    assert any(n["type"] == "field_pending" for n in emp_notifs)
    # The EA (EA001, assists EMP001's supervisor SUP001) is also notified.
    ea_notifs = client.get("/notifications", headers=ea_headers).json()
    assert any(n["type"] == "field_pending" for n in ea_notifs)


def test_field_decision_notifies_employee(client, emp_headers, sup_headers, db_session):
    event_id = _pending_field(db_session, "EMP001")
    ok = client.post(f"/supervisor/field/approvals/{event_id}/approve", headers=sup_headers, json={})
    assert ok.status_code == 200
    notifs = client.get("/notifications", headers=emp_headers).json()
    assert any(n["type"] == "field_approved" for n in notifs)


def test_notifications_require_auth(client):
    assert client.get("/notifications").status_code == 401
