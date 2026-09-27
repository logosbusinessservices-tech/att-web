"""Onboarding: create employee (dept-scoped), enrollment validation, edge gallery."""

import base64
import io

import numpy as np

from app.config import settings
from app.db.models import FaceEmbedding, Person


def test_create_employee_in_supervisor_department(client, sup_headers, db_session):
    r = client.post("/supervisor/employees", headers=sup_headers, json={
        "external_id": "EMP100", "display_name": "New Hire",
        "phone": "+91 91234 56789", "blood_group": "O-",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["department_name"] == "Operations"  # forced to supervisor's dept
    assert body["enrolled"] is False
    # And they can now request an OTP with that phone.
    ok = client.post("/auth/otp/request", json={"phone": "9123456789"})
    assert ok.status_code == 200
    assert len(ok.json()["debug_code"]) == 6


def test_create_employee_rejects_duplicate_code(client, sup_headers):
    r = client.post("/supervisor/employees", headers=sup_headers, json={
        "external_id": "EMP001", "display_name": "Clash",
    })
    assert r.status_code == 409


def test_create_employee_blocked_for_non_supervisor(client, emp_headers):
    r = client.post("/supervisor/employees", headers=emp_headers, json={
        "external_id": "EMPX", "display_name": "Nope",
    })
    assert r.status_code == 403


def test_enroll_rejects_non_face_image(client, sup_headers):
    client.post("/supervisor/employees", headers=sup_headers, json={
        "external_id": "EMP101", "display_name": "Face Test",
    })
    # A plain gray square has no detectable face -> 422 with a helpful message.
    fake = io.BytesIO(b"not-an-image")
    r = client.post(
        "/supervisor/employees/EMP101/enroll",
        headers=sup_headers,
        files=[("photos", ("a.jpg", fake, "image/jpeg"))],
    )
    assert r.status_code == 422


def test_enroll_other_department_forbidden(client, sup_headers):
    # EMP003 is in the Signals dept; Operations supervisor cannot enroll them.
    fake = io.BytesIO(b"x")
    r = client.post(
        "/supervisor/employees/EMP003/enroll",
        headers=sup_headers,
        files=[("photos", ("a.jpg", fake, "image/jpeg"))],
    )
    assert r.status_code == 403


# ── Edge gallery sync ────────────────────────────────────────────────────────
def _seed_embedding(db, external_id):
    p = db.query(Person).filter_by(external_id=external_id).one()
    vec = np.ones(512, dtype=np.float32)
    vec /= np.linalg.norm(vec)
    db.add(FaceEmbedding(person_id=p.id, embedding=vec.tobytes(), num_photos=3))
    db.commit()


def test_edge_gallery_requires_key(client):
    assert client.get("/edge/gallery").status_code == 401


def test_edge_gallery_returns_embeddings(client, db_session):
    _seed_embedding(db_session, "EMP001")
    r = client.get("/edge/gallery", headers={"X-Edge-Key": settings.edge_api_key})
    assert r.status_code == 200
    items = r.json()
    assert any(it["external_id"] == "EMP001" for it in items)
    item = next(it for it in items if it["external_id"] == "EMP001")
    raw = base64.b64decode(item["embedding_b64"])
    assert len(raw) == 512 * 4  # 512 float32
    assert item["num_photos"] == 3


def test_edge_gallery_incremental_since(client, db_session):
    _seed_embedding(db_session, "EMP001")
    # A 'since' in the far future returns nothing new.
    r = client.get(
        "/edge/gallery?since=2999-01-01T00:00:00",
        headers={"X-Edge-Key": settings.edge_api_key},
    )
    assert r.status_code == 200
    assert r.json() == []
