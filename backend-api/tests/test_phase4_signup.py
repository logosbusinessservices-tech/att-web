"""Phase 4: self sign-up + supervisor approval, pending-account gating, avatar."""

import cv2
import io
import numpy as np
import pytest

from app.db.models import Department, Person
from app.services import enrollment as enroll_service


@pytest.fixture
def enroll_face(monkeypatch):
    """Mock the face embedder so a plain test image 'enrolls' successfully."""
    vec = np.ones(512, dtype=np.float32)
    vec /= np.linalg.norm(vec)
    monkeypatch.setattr(enroll_service, "embed_largest_face", lambda img: (vec, 0.9))


def _dept_id(db, name):
    return db.query(Department).filter_by(name=name).one().id


def _signup(client, phone, department_id, display_name="New Person", **extra):
    code = client.post("/auth/signup/otp", json={"phone": phone}).json()["debug_code"]
    return client.post("/auth/signup", json={
        "phone": phone, "code": code, "display_name": display_name,
        "department_id": department_id, **extra,
    })


# ── Sign-up creation ─────────────────────────────────────────────────────────
def test_signup_creates_pending_account(client, db_session):
    ops = _dept_id(db_session, "Operations")
    r = _signup(client, "+91 90000 22222", ops)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending"

    p = db_session.query(Person).filter_by(phone="+91 90000 22222").one()
    assert p.status == "pending"
    assert p.is_active is False
    assert p.password_hash is None
    assert p.external_id.startswith("SIGNUP-")


def test_signup_requires_valid_otp(client, db_session):
    ops = _dept_id(db_session, "Operations")
    client.post("/auth/signup/otp", json={"phone": "+91 90000 33333"})
    r = client.post("/auth/signup", json={
        "phone": "+91 90000 33333", "code": "000000",
        "display_name": "Bad Code", "department_id": ops,
    })
    assert r.status_code in (400, 429)


def test_signup_blocks_existing_phone(client):
    # EMP001 already owns 9000000001 in the seed.
    r = client.post("/auth/signup/otp", json={"phone": "9000000001"})
    assert r.status_code == 409


def test_pending_cannot_login_or_get_otp(client, db_session):
    ops = _dept_id(db_session, "Operations")
    _signup(client, "+91 90000 44444", ops)
    # No password -> password login impossible; OTP request sends no real code.
    otp = client.post("/auth/otp/request", json={"phone": "+91 90000 44444"})
    assert otp.status_code == 200
    assert otp.json().get("debug_code") is None


# ── Approval (now handled by the Executive Assistant, globally) ──────────────
def _pending_id(client, headers, phone_tail):
    for s in client.get("/assistant/signups", headers=headers).json():
        if (s["phone"] or "").endswith(phone_tail):
            return s["id"]
    return None


def test_assistant_approves_and_account_activates(client, ea_headers, db_session):
    ops = _dept_id(db_session, "Operations")
    _signup(client, "+91 90000 55555", ops)
    sid = _pending_id(client, ea_headers, "55555")
    assert sid is not None

    r = client.post(f"/assistant/signups/{sid}/approve", headers=ea_headers,
                    json={"external_id": "EMP200", "field_scan_enabled": True})
    assert r.status_code == 200, r.text
    assert r.json()["external_id"] == "EMP200"

    # Default password == employee code, and login now works.
    tok = client.post("/auth/login", data={"username": "EMP200", "password": "EMP200"})
    assert tok.status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {tok.json()['access_token']}"}).json()
    assert me["must_change_password"] is True
    assert me["field_scan_enabled"] is True
    assert me["needs_attendance_photos"] is True
    assert me["has_face_enrolled"] is False


def test_approve_rejects_duplicate_code(client, ea_headers, db_session):
    ops = _dept_id(db_session, "Operations")
    _signup(client, "+91 90000 66666", ops)
    sid = _pending_id(client, ea_headers, "66666")
    r = client.post(f"/assistant/signups/{sid}/approve", headers=ea_headers,
                    json={"external_id": "EMP001"})
    assert r.status_code == 409


def test_reject_marks_rejected(client, ea_headers, db_session):
    ops = _dept_id(db_session, "Operations")
    _signup(client, "+91 90000 77777", ops)
    sid = _pending_id(client, ea_headers, "77777")
    r = client.post(f"/assistant/signups/{sid}/reject", headers=ea_headers,
                    json={"reason": "Not recognized"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    # It leaves the pending queue.
    assert _pending_id(client, ea_headers, "77777") is None


def test_approve_is_already_handled_guard(client, ea_headers, db_session):
    # Second approval of the same sign-up is a 409/404 (already handled).
    ops = _dept_id(db_session, "Operations")
    _signup(client, "+91 90000 44488", ops)
    sid = _pending_id(client, ea_headers, "44488")
    r1 = client.post(f"/assistant/signups/{sid}/approve", headers=ea_headers,
                     json={"external_id": "EMP250"})
    assert r1.status_code == 200
    r2 = client.post(f"/assistant/signups/{sid}/approve", headers=ea_headers,
                     json={"external_id": "EMP251"})
    assert r2.status_code in (404, 409)


def test_onboarding_is_global_not_department_scoped(client, ea_headers, db_session):
    # A Signals sign-up is visible to (and approvable by) any EA.
    signals = _dept_id(db_session, "Signals")
    _signup(client, "+91 90000 88888", signals)
    sid = _pending_id(client, ea_headers, "88888")
    assert sid is not None
    r = client.post(f"/assistant/signups/{sid}/approve", headers=ea_headers,
                    json={"external_id": "EMP300"})
    assert r.status_code == 200


def test_signups_require_assistant(client, emp_headers, sup_headers):
    # Neither employees nor supervisors can access the EA onboarding queue.
    assert client.get("/assistant/signups", headers=emp_headers).status_code == 403
    assert client.get("/assistant/signups", headers=sup_headers).status_code == 403


# ── Two-step onboarding (approve + photos, done independently, by the EA) ─────
def test_onboard_photos_after_approval(client, ea_headers, db_session, enroll_face):
    ops = _dept_id(db_session, "Operations")
    _signup(client, "+91 90000 13579", ops)
    sid = _pending_id(client, ea_headers, "13579")
    client.post(f"/assistant/signups/{sid}/approve", headers=ea_headers,
                json={"external_id": "EMP210"})
    # Approved but no photos yet → still on the worklist.
    assert _pending_id(client, ea_headers, "13579") is not None

    r = client.post(f"/assistant/signups/{sid}/photos", headers=ea_headers,
                    files=[("photos", ("a.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg"))])
    assert r.status_code == 200, r.text
    assert r.json()["is_approved"] is True
    assert r.json()["is_enrolled"] is True
    # Both steps done → drops off the worklist.
    assert _pending_id(client, ea_headers, "13579") is None


def test_onboard_photos_before_approval(client, ea_headers, db_session, enroll_face):
    ops = _dept_id(db_session, "Operations")
    _signup(client, "+91 90000 24601", ops)
    sid = _pending_id(client, ea_headers, "24601")
    r = client.post(f"/assistant/signups/{sid}/photos", headers=ea_headers,
                    files=[("photos", ("a.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg"))])
    assert r.status_code == 200
    assert r.json()["is_enrolled"] is True
    assert r.json()["is_approved"] is False
    # Still needs approval → remains on the worklist.
    assert _pending_id(client, ea_headers, "24601") is not None


def test_onboard_photos_is_global(client, ea_headers, db_session, enroll_face):
    # A Signals sign-up's photos can be onboarded by any EA (global onboarding).
    signals = _dept_id(db_session, "Signals")
    _signup(client, "+91 90000 33221", signals)
    p = db_session.query(Person).filter_by(phone="+91 90000 33221").one()
    r = client.post(f"/assistant/signups/{p.id}/photos", headers=ea_headers,
                    files=[("photos", ("a.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg"))])
    assert r.status_code == 200


# ── Pending accounts excluded from analytics ─────────────────────────────────
def test_pending_excluded_from_overview(client, sup_headers, db_session):
    ops = _dept_id(db_session, "Operations")
    _signup(client, "+91 90000 99999", ops, display_name="Ghost Applicant")
    rows = client.get("/supervisor/attendance/overview", headers=sup_headers).json()
    assert all(r["display_name"] != "Ghost Applicant" for r in rows)


# ── Avatar ───────────────────────────────────────────────────────────────────
def _jpeg_bytes():
    ok, buf = cv2.imencode(".jpg", np.zeros((16, 16, 3), dtype=np.uint8))
    assert ok
    return buf.tobytes()


def test_avatar_upload_and_fetch(client, emp_headers):
    r = client.post("/employees/avatar", headers=emp_headers,
                    files=[("photo", ("me.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg"))])
    assert r.status_code == 200, r.text
    assert r.json()["avatar_url"] == "/employees/EMP001/avatar"
    img = client.get("/employees/EMP001/avatar", headers=emp_headers)
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"


def test_avatar_rejects_non_image(client, emp_headers):
    r = client.post("/employees/avatar", headers=emp_headers,
                    files=[("photo", ("x.jpg", io.BytesIO(b"not-an-image"), "image/jpeg"))])
    assert r.status_code == 422


def test_avatar_not_visible_to_other_employees(client, emp_headers, emp2_headers):
    client.post("/employees/avatar", headers=emp_headers,
                files=[("photo", ("me.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg"))])
    # EMP002 (not a supervisor) can't fetch EMP001's photo.
    assert client.get("/employees/EMP001/avatar", headers=emp2_headers).status_code == 403


# ── Employee self-service profile edits ──────────────────────────────────────
def test_employee_fills_blank_field(client, emp2_headers):
    # EMP002 has no email seeded; the employee can add one themselves.
    r = client.patch("/employees/profile", headers=emp2_headers,
                     json={"email": "asha@rail.gov.in"})
    assert r.status_code == 200
    assert r.json()["email"] == "asha@rail.gov.in"


def test_employee_profile_phone_conflict_rejected(client, emp2_headers):
    # EMP001 already owns 9000000001 in the seed.
    r = client.patch("/employees/profile", headers=emp2_headers,
                     json={"phone": "+91 90000 00001"})
    assert r.status_code == 409


def test_employee_profile_phone_added(client, emp2_headers):
    r = client.patch("/employees/profile", headers=emp2_headers,
                     json={"phone": "+91 90000 24680"})
    assert r.status_code == 200
    assert r.json()["phone"] == "+91 90000 24680"
