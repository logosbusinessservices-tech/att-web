"""Phase 2 drill-down: raw events view + per-event camera crop endpoint.

Covers:
  - AttendanceEventOut now carries `crop_path` so the frontend knows which
    events have a saved face crop available.
  - GET /supervisor/events/{event_id}/crop serves the crop (dept-scoped), or
    404s cleanly for non-camera, cross-department, or purged events.
  - The employee_summary endpoint returns the data the drill-down UI needs,
    unchanged by Phase 1's capture filter (i.e., it still shows every event
    regardless of source).
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app import storage
from app.config import settings
from app.db.models import AttendanceEvent, Person

IST = ZoneInfo(settings.display_timezone)


def _utc(d: date, hh: int, mm: int) -> datetime:
    local = datetime.combine(d, time(hh, mm), tzinfo=IST)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _recent_working_day(offset: int) -> date:
    d = date.today() - timedelta(days=offset)
    while d.weekday() == 6:
        d -= timedelta(days=1)
    return d


def _seeded_camera_event(db, external_id="EMP001"):
    """Return the first seeded camera event for the given person."""
    p = db.query(Person).filter_by(external_id=external_id).one()
    return db.query(AttendanceEvent).filter(
        AttendanceEvent.person_id == p.id,
        AttendanceEvent.source == "camera",
    ).first()


# ── AttendanceEventOut schema: crop_path flows through ──────────────────────
def test_employee_summary_includes_crop_path_field(client, sup_headers, db_session, seed_params):
    """Each event in the day summary must carry a `crop_path` key (even when None).

    If this fails, the frontend thinks NO events have crops and will never
    show the thumbnail — defeating the whole point of the drill-down.
    """
    # Give one event a fake crop path so we can see it in the response.
    ev = _seeded_camera_event(db_session)
    ev.crop_path = "gate-1/crops/2026-10-30/gate-in-1/testcrop.jpg"
    db_session.commit()

    r = client.get(
        "/supervisor/employee/EMP001/summary",
        headers=sup_headers,
        params=seed_params,
    )
    assert r.status_code == 200
    days = r.json()
    # Find the event we just tagged.
    tagged = []
    for day in days:
        for e in day.get("events") or []:
            if e["id"] == ev.id:
                tagged.append(e)
    assert tagged, "Expected to find the tagged event in the summary"
    assert "crop_path" in tagged[0]
    assert tagged[0]["crop_path"] == "gate-1/crops/2026-10-30/gate-in-1/testcrop.jpg"


def test_employee_summary_event_without_crop_has_null(client, sup_headers, db_session, seed_params):
    """Events with no crop get crop_path=None (not missing) in the JSON."""
    r = client.get(
        "/supervisor/employee/EMP001/summary",
        headers=sup_headers,
        params=seed_params,
    )
    assert r.status_code == 200
    days = r.json()
    for day in days:
        for e in day.get("events") or []:
            assert "crop_path" in e
            # Seeded events don't set crop_path; default is None.
            assert e["crop_path"] in (None, "")


def test_employee_summary_returns_every_source(client, sup_headers, db_session, seed_params):
    """The drill-down endpoint ignores the capture filter — on purpose.

    If a person has a camera event AND a field event on the same day, both
    must appear. The whole point of drill-down is "show me the raw truth".
    """
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    d = _recent_working_day(3)
    # Add a field entry alongside the already-seeded camera days.
    db_session.add(AttendanceEvent(
        person_id=emp1.id, camera_label="field-test",
        direction="entry", source="field", event_time=_utc(d, 10, 0),
    ))
    db_session.commit()

    r = client.get(
        "/supervisor/employee/EMP001/summary",
        headers=sup_headers,
        params={"from_date": d.isoformat(), "to_date": d.isoformat()},
    )
    assert r.status_code == 200
    days = r.json()
    assert len(days) == 1
    sources = {e["source"] for e in days[0].get("events") or []}
    assert "field" in sources


# ── Crop endpoint: happy paths ──────────────────────────────────────────────
def test_crop_endpoint_serves_bytes(client, sup_headers, db_session, monkeypatch):
    """A camera event with a saved crop returns the bytes with image/jpeg."""
    ev = _seeded_camera_event(db_session)
    ev.crop_path = "gate-1/crops/2026-10-30/gate-in-1/abc_full.jpg"
    db_session.commit()

    # Pretend Azure handed us these bytes.
    sample = b"\xff\xd8\xff\xe0JFIF_fake_jpeg_bytes"
    monkeypatch.setattr(storage, "load_camera_crop", lambda path: sample)

    r = client.get(f"/supervisor/events/{ev.id}/crop", headers=sup_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/jpeg")
    assert r.content == sample


def test_crop_endpoint_404_when_crop_missing_from_storage(client, sup_headers, db_session, monkeypatch):
    """Azure returns None (crop was purged) -> clean 404, no crash."""
    ev = _seeded_camera_event(db_session)
    ev.crop_path = "gate-1/crops/2026-10-30/gate-in-1/missing.jpg"
    db_session.commit()
    monkeypatch.setattr(storage, "load_camera_crop", lambda path: None)

    r = client.get(f"/supervisor/events/{ev.id}/crop", headers=sup_headers)
    assert r.status_code == 404


# ── Crop endpoint: refusal cases ────────────────────────────────────────────
def test_crop_endpoint_404_when_event_has_no_crop_path(client, sup_headers, db_session):
    """Event exists but no crop was saved -> 404, not a 500."""
    ev = _seeded_camera_event(db_session)
    ev.crop_path = None
    db_session.commit()

    r = client.get(f"/supervisor/events/{ev.id}/crop", headers=sup_headers)
    assert r.status_code == 404


def test_crop_endpoint_404_for_field_event(client, sup_headers, db_session):
    """Only camera events have crops in the camera-audit container."""
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    d = _recent_working_day(2)
    field_ev = AttendanceEvent(
        person_id=emp1.id, camera_label="field-x",
        direction="entry", source="field", event_time=_utc(d, 10, 0),
        selfie_path="some/selfie.jpg",
    )
    db_session.add(field_ev)
    db_session.commit()

    r = client.get(f"/supervisor/events/{field_ev.id}/crop", headers=sup_headers)
    assert r.status_code == 404


def test_crop_endpoint_404_for_manual_event(client, sup_headers, db_session):
    """Manual events have no crop."""
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    d = _recent_working_day(2)
    manual_ev = AttendanceEvent(
        person_id=emp1.id, camera_label="manual",
        direction="entry", source="manual", event_time=_utc(d, 10, 0),
    )
    db_session.add(manual_ev)
    db_session.commit()

    r = client.get(f"/supervisor/events/{manual_ev.id}/crop", headers=sup_headers)
    assert r.status_code == 404


def test_crop_endpoint_404_for_unknown_event(client, sup_headers):
    """An event id that doesn't exist returns 404 without leaking info."""
    r = client.get("/supervisor/events/99999/crop", headers=sup_headers)
    assert r.status_code == 404


def test_crop_endpoint_404_for_visitor_event(client, sup_headers, db_session):
    """Visitor events have no person_id -> 404 (visitor crops come in Phase 3)."""
    d = _recent_working_day(2)
    visitor_ev = AttendanceEvent(
        person_id=None, is_visitor=True, camera_label="gate-in-1",
        direction="entry", source="camera", event_time=_utc(d, 10, 0),
        crop_path="gate-1/crops/2026-10-30/gate-in-1/visitor.jpg",
    )
    db_session.add(visitor_ev)
    db_session.commit()

    r = client.get(f"/supervisor/events/{visitor_ev.id}/crop", headers=sup_headers)
    assert r.status_code == 404


# ── Crop endpoint: auth and dept-scoping ────────────────────────────────────
def test_crop_endpoint_requires_auth(client, db_session):
    """Unauthenticated calls are rejected."""
    ev = _seeded_camera_event(db_session)
    r = client.get(f"/supervisor/events/{ev.id}/crop")
    assert r.status_code == 401


def test_crop_endpoint_requires_supervisor_role(client, emp_headers, db_session):
    """Employees can't peek at other people's crops."""
    ev = _seeded_camera_event(db_session)
    r = client.get(f"/supervisor/events/{ev.id}/crop", headers=emp_headers)
    assert r.status_code == 403


def test_crop_endpoint_dept_scoped(client, sup2_headers, db_session, monkeypatch):
    """A supervisor in ANOTHER department can't fetch this crop."""
    ev = _seeded_camera_event(db_session)   # EMP001 is in Operations
    ev.crop_path = "gate-1/crops/anywhere/abc.jpg"
    db_session.commit()
    monkeypatch.setattr(storage, "load_camera_crop", lambda path: b"fake")

    # SUP002 is in Signals dept, not Operations.
    r = client.get(f"/supervisor/events/{ev.id}/crop", headers=sup2_headers)
    assert r.status_code == 403


def test_crop_endpoint_allows_chief(client, chief_headers, db_session, monkeypatch):
    """Chief manager sees every department's crops."""
    ev = _seeded_camera_event(db_session)
    ev.crop_path = "gate-1/crops/2026-10-30/gate-in-1/chief.jpg"
    db_session.commit()
    monkeypatch.setattr(storage, "load_camera_crop", lambda path: b"ok_bytes")

    r = client.get(f"/supervisor/events/{ev.id}/crop", headers=chief_headers)
    assert r.status_code == 200
    assert r.content == b"ok_bytes"


# ── storage.load_camera_crop smoke tests ────────────────────────────────────
def test_load_camera_crop_returns_none_for_empty_path():
    """Defensive: empty / None path -> None, no exception."""
    assert storage.load_camera_crop(None) is None
    assert storage.load_camera_crop("") is None


def test_load_camera_crop_returns_none_without_azure_configured():
    """In tests with no Azure connection and no local fallback, return None."""
    # The _isolated_storage fixture already blanks the connection string.
    assert storage.load_camera_crop("gate-1/crops/anywhere/missing.jpg") is None