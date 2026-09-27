"""Edge ingestion: POST /events (camera pipeline -> cloud DB), key-guarded."""

from app.config import settings


def _payload(**over):
    base = {
        "external_id": "EMP001",
        "camera_label": "gate-in-1",
        "similarity": 0.88,
    }
    base.update(over)
    return base


def test_events_requires_edge_key(client):
    r = client.post("/events", json=_payload())
    assert r.status_code == 401


def test_events_rejects_wrong_key(client):
    r = client.post("/events", json=_payload(), headers={"X-Edge-Key": "wrong"})
    assert r.status_code == 401


def test_events_stored_with_correct_key(client):
    r = client.post(
        "/events", json=_payload(), headers={"X-Edge-Key": settings.edge_api_key}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "stored"


def test_events_direction_derived_from_camera_label(client, emp_headers):
    # No explicit direction: server should derive 'entry' from gate-in-1.
    client.post(
        "/events",
        json=_payload(camera_label="gate-in-1", direction=None),
        headers={"X-Edge-Key": settings.edge_api_key},
    )
    r = client.get("/attendance/me", headers=emp_headers)
    latest = r.json()[0]
    assert latest["direction"] == "entry"
    assert latest["source"] == "camera"


def test_events_unknown_person_marked_visitor(client):
    r = client.post(
        "/events",
        json=_payload(external_id="NOBODY"),
        headers={"X-Edge-Key": settings.edge_api_key},
    )
    assert r.status_code == 200
