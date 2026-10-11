"""Edge (NUC) contract: full gallery snapshot, key checks, idempotent event ingest."""

import numpy as np
import pytest

from app.config import settings
from app.db.models import AttendanceEvent, FaceEmbedding, Person

EDGE = {"X-Edge-Key": settings.edge_api_key}


def _vec(seed: int) -> bytes:
    v = np.random.default_rng(seed).standard_normal(512).astype(np.float32)
    return (v / np.linalg.norm(v)).tobytes()


def _enroll(db, external_id, seed=1, num_photos=3):
    p = db.query(Person).filter_by(external_id=external_id).one()
    db.add(FaceEmbedding(person_id=p.id, embedding=_vec(seed), num_photos=num_photos))
    db.commit()
    return p


def _snapshot(client, version=None):
    url = "/edge/gallery" + (f"?version={version}" if version else "")
    r = client.get(url, headers=EDGE)
    assert r.status_code == 200, r.text
    return r.json()


def _ids(snap):
    return {it["external_id"] for it in snap["items"]}


# ── Key check ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("headers", [{}, {"X-Edge-Key": "wrong"}, {"X-Edge-Key": settings.edge_api_key + "x"}])
def test_edge_endpoints_reject_bad_key(client, headers):
    assert client.get("/edge/gallery", headers=headers).status_code == 401
    assert client.get("/edge/display-messages", headers=headers).status_code == 401
    assert client.post("/events", json={"camera_label": "gate-in-2"}, headers=headers).status_code == 401


# ── Gallery snapshot ─────────────────────────────────────────────────────────
def test_snapshot_carries_model_info(client, db_session):
    _enroll(db_session, "EMP001")
    snap = _snapshot(client)
    assert snap["model_name"] == "buffalo_s"
    assert snap["model_sha256"] == "test-model-sha256"
    assert snap["embedding_dim"] == 512
    assert snap["count"] == 1 and _ids(snap) == {"EMP001"}
    assert snap["items"][0]["updated_at"].endswith(("Z", "+00:00"))


def test_snapshot_unchanged_when_version_matches(client, db_session):
    _enroll(db_session, "EMP001")
    first = _snapshot(client)
    again = _snapshot(client, first["version"])
    assert again["unchanged"] is True
    assert again["items"] == []
    assert again["version"] == first["version"]
    assert again["count"] == 1


def test_snapshot_excludes_pending_then_includes_after_approval(client, db_session):
    # Photos uploaded while the sign-up is still pending under a temporary code.
    pending = Person(external_id="SIGNUP-abc123", display_name="New Hire",
                     status="pending", is_active=False)
    db_session.add(pending)
    db_session.flush()
    db_session.add(FaceEmbedding(person_id=pending.id, embedding=_vec(7), num_photos=2))
    db_session.commit()
    before = _snapshot(client)
    assert "SIGNUP-abc123" not in _ids(before)

    # Approval assigns the real code but doesn't touch the face template.
    pending.external_id, pending.status, pending.is_active = "EMP500", "active", True
    db_session.commit()
    after = _snapshot(client, before["version"])
    assert after["unchanged"] is False
    assert "EMP500" in _ids(after)


def test_snapshot_drops_deactivated_person(client, db_session):
    p = _enroll(db_session, "EMP001")
    _enroll(db_session, "EMP002", seed=2)
    before = _snapshot(client)
    p.is_active = False
    db_session.commit()
    after = _snapshot(client, before["version"])
    assert _ids(after) == {"EMP002"}


def test_snapshot_version_changes_on_rename_and_reenroll(client, db_session):
    p = _enroll(db_session, "EMP001")
    v1 = _snapshot(client)["version"]
    p.display_name = "Renamed Person"
    db_session.commit()
    v2 = _snapshot(client)["version"]
    assert v2 != v1

    emb = db_session.query(FaceEmbedding).filter_by(person_id=p.id).one()
    emb.embedding = _vec(99)
    db_session.commit()
    assert _snapshot(client)["version"] != v2


# ── Event ingest ─────────────────────────────────────────────────────────────
def _event(**over):
    body = {"external_id": "EMP001", "camera_label": "gate-in-2", "direction": "entry",
            "similarity": 0.81, "event_uuid": "a" * 32}
    body.update(over)
    return body


def test_event_with_same_uuid_is_stored_once(client, db_session):
    first = client.post("/events", json=_event(), headers=EDGE)
    second = client.post("/events", json=_event(), headers=EDGE)
    assert first.json()["status"] == "stored"
    assert second.json() == {"id": first.json()["id"], "status": "duplicate"}
    assert db_session.query(AttendanceEvent).filter_by(event_uuid="a" * 32).count() == 1


def test_events_with_different_uuids_both_stored(client, db_session):
    client.post("/events", json=_event(event_uuid="1" * 32), headers=EDGE)
    client.post("/events", json=_event(event_uuid="2" * 32), headers=EDGE)
    assert db_session.query(AttendanceEvent).filter(
        AttendanceEvent.event_uuid.in_(["1" * 32, "2" * 32])).count() == 2


def test_event_without_uuid_still_accepted(client):
    r = client.post("/events", json=_event(event_uuid=None), headers=EDGE)
    assert r.status_code == 200 and r.json()["status"] == "stored"


def test_event_crop_ref_kept_internally_only(client, db_session, emp_headers):
    r = client.post("/events", json=_event(crop_ref="gate_2/2026-10-12/gate-in-2/x.jpg"), headers=EDGE)
    ev = db_session.get(AttendanceEvent, r.json()["id"])
    assert ev.crop_path == "gate_2/2026-10-12/gate-in-2/x.jpg"
    rows = client.get("/attendance/me", headers=emp_headers).json()
    assert all("crop_path" not in row and "crop_ref" not in row for row in rows)


def test_event_rejects_unknown_direction(client):
    r = client.post("/events", json=_event(direction="in"), headers=EDGE)
    assert r.status_code == 422
