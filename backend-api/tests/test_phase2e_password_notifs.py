"""Phase 2e: default password on onboarding, change password (old pw / OTP),
supervisor notifications (password reminders + back-to-back camera errors)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import AttendanceEvent, Person


# ── Onboarding sets a default password + must-change flag ────────────────────
def test_onboarded_employee_default_password_is_code(client, sup_headers, db_session):
    r = client.post("/supervisor/employees", headers=sup_headers, json={
        "external_id": "EMP200", "display_name": "Fresh Hire",
        "phone": "+91 98888 00001", "email": "fresh@rail.gov.in",
    })
    assert r.status_code == 200
    # Can log in immediately with code == password.
    login = client.post("/auth/login", data={"username": "EMP200", "password": "EMP200"})
    assert login.status_code == 200
    # And the profile flags a forced change.
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.json()["must_change_password"] is True


# ── Change password via current password ─────────────────────────────────────
def test_change_password_with_old_password(client, emp_headers):
    r = client.post("/auth/password/change", headers=emp_headers,
                    json={"old_password": "pass123", "new_password": "brandnew1"})
    assert r.status_code == 200
    assert r.json()["must_change_password"] is False
    # Old password no longer works; new one does.
    assert client.post("/auth/login", data={"username": "EMP001", "password": "pass123"}).status_code == 401
    assert client.post("/auth/login", data={"username": "EMP001", "password": "brandnew1"}).status_code == 200


def test_change_password_wrong_old_password(client, emp_headers):
    r = client.post("/auth/password/change", headers=emp_headers,
                    json={"old_password": "wrong", "new_password": "brandnew1"})
    assert r.status_code == 400


def test_change_password_too_short(client, emp_headers):
    r = client.post("/auth/password/change", headers=emp_headers,
                    json={"old_password": "pass123", "new_password": "abc"})
    assert r.status_code == 400


def test_change_password_requires_proof(client, emp_headers):
    r = client.post("/auth/password/change", headers=emp_headers,
                    json={"new_password": "brandnew1"})
    assert r.status_code == 400


# ── Change password via mobile OTP (2FA) ─────────────────────────────────────
def test_change_password_with_mobile_otp(client, emp_headers):
    ack = client.post("/auth/password/otp", headers=emp_headers, json={})
    assert ack.status_code == 200
    code = ack.json()["debug_code"]
    r = client.post("/auth/password/change", headers=emp_headers,
                    json={"otp_code": code, "new_password": "viaotp123"})
    assert r.status_code == 200
    assert client.post("/auth/login", data={"username": "EMP001", "password": "viaotp123"}).status_code == 200


def test_change_password_otp_no_phone_on_file(client, emp2_headers):
    # EMP002 has no phone seeded, so mobile 2FA can't be used.
    r = client.post("/auth/password/otp", headers=emp2_headers, json={})
    assert r.status_code == 400


def test_change_password_wrong_otp(client, emp_headers):
    client.post("/auth/password/otp", headers=emp_headers, json={})
    r = client.post("/auth/password/change", headers=emp_headers,
                    json={"otp_code": "000000", "new_password": "nope12345"})
    assert r.status_code == 400


# ── Supervisor notifications ─────────────────────────────────────────────────
def test_notifications_password_reminder(client, sup_headers, db_session):
    # Onboard, then backdate created_at beyond the reminder window.
    client.post("/supervisor/employees", headers=sup_headers, json={
        "external_id": "EMP300", "display_name": "Slow Changer", "phone": "+91 97777 00001",
    })
    p = db_session.execute(select(Person).where(Person.external_id == "EMP300")).scalar_one()
    p.created_at = datetime.now(timezone.utc) - timedelta(days=5)
    db_session.commit()

    r = client.get("/supervisor/notifications", headers=sup_headers)
    assert r.status_code == 200
    reminders = [n for n in r.json() if n["type"] == "password_reminder" and n["external_id"] == "EMP300"]
    assert len(reminders) == 1


def test_notifications_camera_error_back_to_back(client, sup_headers, db_session):
    emp1 = db_session.execute(select(Person).where(Person.external_id == "EMP001")).scalar_one()
    # Two entries in a row (no exit between) on a recent day -> camera_error.
    day = datetime.now(timezone.utc) - timedelta(days=1)
    base = day.replace(hour=3, minute=30, second=0, microsecond=0)  # ~09:00 IST
    db_session.add_all([
        AttendanceEvent(person_id=emp1.id, camera_label="gate-in-1", direction="entry",
                        source="camera", event_time=base),
        AttendanceEvent(person_id=emp1.id, camera_label="gate-in-1", direction="entry",
                        source="camera", event_time=base + timedelta(hours=2)),
    ])
    db_session.commit()

    r = client.get("/supervisor/notifications", headers=sup_headers)
    assert r.status_code == 200
    cam = [n for n in r.json() if n["type"] == "camera_error" and n["external_id"] == "EMP001"]
    assert len(cam) >= 1


def test_notifications_requires_supervisor(client, emp_headers):
    r = client.get("/supervisor/notifications", headers=emp_headers)
    assert r.status_code == 403
