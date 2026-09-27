"""Phase 3: field attendance (face 1:1 + GPS geofence), approvals, permissions."""

import io

import numpy as np
import pytest

from app.config import settings
from app.db.models import AttendanceEvent, FaceEmbedding, Person
from app.services import field as field_service

# Conftest seeds "Central Station" at (28.6431, 77.2197) radius 250 m.
STATION_LAT, STATION_LON = 28.6431, 77.2197
FAR_LAT, FAR_LON = 28.7041, 77.1025  # ~13 km away


@pytest.fixture(autouse=True)
def _tmp_selfies(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "field_selfie_dir", str(tmp_path / "selfies"))


def _seed_embedding(db, external_id="EMP001"):
    p = db.query(Person).filter_by(external_id=external_id).one()
    vec = np.ones(512, dtype=np.float32)
    vec /= np.linalg.norm(vec)
    db.add(FaceEmbedding(person_id=p.id, embedding=vec.tobytes(), num_photos=3))
    db.commit()
    return vec


def _enable_field(db, external_id="EMP001"):
    p = db.query(Person).filter_by(external_id=external_id).one()
    p.field_scan_enabled = True
    db.commit()


@pytest.fixture()
def match_face(monkeypatch):
    """Make the face pipeline return a vector that MATCHES the seeded template."""
    vec = np.ones(512, dtype=np.float32)
    vec /= np.linalg.norm(vec)
    monkeypatch.setattr(field_service, "decode_image_bytes", lambda b: np.zeros((8, 8, 3)))
    monkeypatch.setattr(field_service, "embed_largest_face", lambda img: (vec, 0.9))


@pytest.fixture()
def mismatch_face(monkeypatch):
    """Return a vector that does NOT match the all-ones seeded template."""
    v = np.zeros(512, dtype=np.float32)
    v[0] = 1.0
    monkeypatch.setattr(field_service, "decode_image_bytes", lambda b: np.zeros((8, 8, 3)))
    monkeypatch.setattr(field_service, "embed_largest_face", lambda img: (v, 0.9))


def _post_field(client, headers, *, direction="entry", lat=STATION_LAT, lon=STATION_LON, acc=20.0, captured_at=None):
    data = {"direction": direction}
    if lat is not None:
        data["latitude"] = str(lat)
    if lon is not None:
        data["longitude"] = str(lon)
    if acc is not None:
        data["accuracy_m"] = str(acc)
    if captured_at is not None:
        data["captured_at"] = captured_at
    files = [("selfie", ("s.jpg", io.BytesIO(b"selfie-bytes"), "image/jpeg"))]
    return client.post("/attendance/field", headers=headers, data=data, files=files)


# ── Permission gate ──────────────────────────────────────────────────────────
def test_field_requires_permission(client, emp_headers, db_session, match_face):
    _seed_embedding(db_session)
    r = _post_field(client, emp_headers)
    assert r.status_code == 403


def test_field_requires_enrollment(client, emp_headers, db_session, match_face):
    _enable_field(db_session)  # enabled but NOT enrolled
    r = _post_field(client, emp_headers)
    assert r.status_code == 422
    assert "enroll" in r.json()["detail"].lower()


# ── Happy path: inside geofence + matching face -> approved ──────────────────
def test_field_checkin_inside_geofence_approved(client, emp_headers, db_session, match_face):
    _seed_embedding(db_session)
    _enable_field(db_session)
    r = _post_field(client, emp_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["review_status"] == "approved"
    assert body["inside_geofence"] is True
    assert body["direction"] == "entry"
    assert body["day"]["entry_count"] == 1


def test_field_face_mismatch_rejected(client, emp_headers, db_session, mismatch_face):
    _seed_embedding(db_session)
    _enable_field(db_session)
    r = _post_field(client, emp_headers)
    assert r.status_code == 422
    assert "match" in r.json()["detail"].lower()


# ── Uncertain location -> pending (supervisor approval) ──────────────────────
def test_field_out_of_geofence_pending(client, emp_headers, db_session, match_face):
    _seed_embedding(db_session)
    _enable_field(db_session)
    r = _post_field(client, emp_headers, lat=FAR_LAT, lon=FAR_LON, acc=20.0)
    assert r.status_code == 200
    body = r.json()
    assert body["review_status"] == "pending"
    assert body["inside_geofence"] is False
    assert "km from" in body["message"]


def test_field_no_gps_pending(client, emp_headers, db_session, match_face):
    _seed_embedding(db_session)
    _enable_field(db_session)
    r = _post_field(client, emp_headers, lat=None, lon=None, acc=None)
    assert r.status_code == 200
    assert r.json()["review_status"] == "pending"


def test_field_coarse_gps_pending(client, emp_headers, db_session, match_face):
    _seed_embedding(db_session)
    _enable_field(db_session)
    # At the station but accuracy worse than the gate -> uncertain.
    r = _post_field(client, emp_headers, acc=500.0)
    assert r.status_code == 200
    assert r.json()["review_status"] == "pending"


# ── Mandatory check-in / check-out pairing ───────────────────────────────────
def test_field_cannot_exit_without_entry(client, emp_headers, db_session, match_face):
    _seed_embedding(db_session)
    _enable_field(db_session)
    r = _post_field(client, emp_headers, direction="exit")
    assert r.status_code == 400
    assert "check in" in r.json()["detail"].lower()


def test_field_cannot_double_checkin(client, emp_headers, db_session, match_face):
    _seed_embedding(db_session)
    _enable_field(db_session)
    assert _post_field(client, emp_headers, direction="entry").status_code == 200
    r = _post_field(client, emp_headers, direction="entry")
    assert r.status_code == 400
    assert "checked in" in r.json()["detail"].lower()


def test_field_status_suggests_next_direction(client, emp_headers, db_session, match_face):
    _seed_embedding(db_session)
    _enable_field(db_session)
    assert client.get("/attendance/field/status", headers=emp_headers).json()["next_direction"] == "entry"
    _post_field(client, emp_headers, direction="entry")
    st = client.get("/attendance/field/status", headers=emp_headers).json()
    assert st["next_direction"] == "exit"
    assert st["open_entry"] is True


# ── Supervisor field approvals ───────────────────────────────────────────────
def test_supervisor_sees_pending_and_approves(client, emp_headers, sup_headers, db_session, match_face):
    _seed_embedding(db_session)
    _enable_field(db_session)
    _post_field(client, emp_headers, lat=FAR_LAT, lon=FAR_LON)  # -> pending

    pend = client.get("/supervisor/field/approvals", headers=sup_headers).json()
    assert len(pend) == 1
    eid = pend[0]["event_id"]
    assert pend[0]["external_id"] == "EMP001"
    assert pend[0]["distance_m"] > 1000

    ok = client.post(f"/supervisor/field/approvals/{eid}/approve", headers=sup_headers, json={})
    assert ok.status_code == 200
    # No longer pending.
    assert client.get("/supervisor/field/approvals", headers=sup_headers).json() == []


def test_supervisor_reject_excludes_from_attendance(client, emp_headers, sup_headers, db_session, match_face):
    _seed_embedding(db_session)
    _enable_field(db_session)
    _post_field(client, emp_headers, lat=FAR_LAT, lon=FAR_LON)  # pending entry
    eid = client.get("/supervisor/field/approvals", headers=sup_headers).json()[0]["event_id"]

    client.post(f"/supervisor/field/approvals/{eid}/reject", headers=sup_headers, json={"reason": "not on duty"})
    # Rejected scan should not count as a crossing.
    summ = client.get("/attendance/summary", headers=emp_headers).json()
    from app.services import attendance_service as svc
    today = svc.today_local().isoformat()
    day = next((d for d in summ if d["date"] == today), None)
    assert day is None or day["entry_count"] == 0


def test_field_approvals_dept_scoped(client, emp3_headers, sup_headers, db_session, match_face):
    # EMP003 is in another department; enable + pending scan for them.
    _seed_embedding(db_session, "EMP003")
    _enable_field(db_session, "EMP003")
    _post_field(client, emp3_headers, lat=FAR_LAT, lon=FAR_LON)
    # Operations supervisor should not see EMP003's pending scan.
    pend = client.get("/supervisor/field/approvals", headers=sup_headers).json()
    assert all(p["external_id"] != "EMP003" for p in pend)


# ── Employee settings / permissions ──────────────────────────────────────────
def test_supervisor_toggles_field_permission(client, sup_headers, emp_headers, db_session):
    r = client.patch("/supervisor/employees/EMP001/settings", headers=sup_headers,
                     json={"field_scan_enabled": True})
    assert r.status_code == 200
    assert r.json()["field_scan_enabled"] is True
    # Reflected in the employee's own profile.
    assert client.get("/auth/me", headers=emp_headers).json()["field_scan_enabled"] is True


def test_settings_dept_scoped(client, sup_headers):
    r = client.patch("/supervisor/employees/EMP003/settings", headers=sup_headers,
                     json={"field_scan_enabled": True})
    assert r.status_code == 403


def test_onboarding_can_enable_field_scan(client, sup_headers):
    r = client.post("/supervisor/employees", headers=sup_headers, json={
        "external_id": "EMP400", "display_name": "Field Hire",
        "phone": "+91 96666 00001", "field_scan_enabled": True,
    })
    assert r.status_code == 200
    s = client.get("/supervisor/employees/EMP400/settings", headers=sup_headers)
    assert s.json()["field_scan_enabled"] is True


# ── Offline capture replay: captured_at preserves the real time ──────────────
def test_field_captured_at_used_for_event_time(client, emp_headers, db_session, match_face):
    from datetime import datetime, timezone
    from app.services import attendance_service as svc
    _seed_embedding(db_session)
    _enable_field(db_session)
    # Simulate a scan captured earlier today, synced now.
    today = svc.today_local()
    captured = datetime(today.year, today.month, today.day, 4, 0, 0, tzinfo=timezone.utc)  # ~09:30 IST
    r = _post_field(client, emp_headers, captured_at=captured.isoformat())
    assert r.status_code == 200
    assert r.json()["day"]["date"] == today.isoformat()
    # The stored crossing carries the capture time, not the sync time.
    emp = db_session.query(Person).filter_by(external_id="EMP001").one()
    ev = db_session.query(AttendanceEvent).filter_by(person_id=emp.id, source="field").first()
    assert ev.event_time.hour == 4
