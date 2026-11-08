"""Phase 3 visitor analytics: chief-only KPIs, day matrix, crop endpoint."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app import storage
from app.config import settings
from app.db.models import AttendanceEvent

IST = ZoneInfo(settings.display_timezone)


def _utc(d: date, hh: int, mm: int) -> datetime:
    local = datetime.combine(d, time(hh, mm), tzinfo=IST)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _recent_working_day(offset: int) -> date:
    d = date.today() - timedelta(days=offset)
    while d.weekday() == 6:
        d -= timedelta(days=1)
    return d


def _add_visitor(db, d, hh, mm, *, direction="entry", camera="gate-in-1",
                 crop_path=None, similarity=0.25):
    """Insert one visitor event and return it."""
    ev = AttendanceEvent(
        person_id=None,
        is_visitor=True,
        camera_label=camera,
        direction=direction,
        source="camera",
        event_time=_utc(d, hh, mm),
        similarity=similarity,
        crop_path=crop_path,
    )
    db.add(ev)
    db.commit()
    return ev


# ── Permission: only chief can access ANY visitor endpoint ─────────────────
def test_visitor_summary_requires_auth(client):
    assert client.get("/supervisor/visitors/summary").status_code == 401


def test_visitor_summary_forbidden_for_employee(client, emp_headers):
    assert client.get("/supervisor/visitors/summary", headers=emp_headers).status_code == 403


def test_visitor_summary_forbidden_for_supervisor(client, sup_headers):
    """Regular supervisors cannot see visitors in Phase 3."""
    assert client.get("/supervisor/visitors/summary", headers=sup_headers).status_code == 403


def test_visitor_summary_forbidden_for_assistant(client, ea_headers):
    assert client.get("/supervisor/visitors/summary", headers=ea_headers).status_code == 403


def test_visitor_summary_allowed_for_chief(client, chief_headers):
    assert client.get("/supervisor/visitors/summary", headers=chief_headers).status_code == 200


def test_visitor_by_day_forbidden_for_supervisor(client, sup_headers):
    assert client.get("/supervisor/visitors/by-day", headers=sup_headers).status_code == 403


def test_visitor_crop_forbidden_for_supervisor(client, sup_headers, db_session):
    d = _recent_working_day(1)
    ev = _add_visitor(db_session, d, 10, 0, crop_path="gate-1/crops/x.jpg")
    assert client.get(f"/supervisor/visitors/events/{ev.id}/crop",
                      headers=sup_headers).status_code == 403


# ── Summary: counts total / entries / exits ─────────────────────────────────
def test_visitor_summary_empty(client, chief_headers):
    """No visitors seeded -> all zeroes."""
    r = client.get("/supervisor/visitors/summary", headers=chief_headers)
    assert r.status_code == 200
    body = r.json()
    assert body == {"total_events": 0, "entries": 0, "exits": 0}


def test_visitor_summary_counts_directions(client, chief_headers, db_session):
    d = _recent_working_day(1)
    _add_visitor(db_session, d, 9, 0, direction="entry")
    _add_visitor(db_session, d, 9, 15, direction="entry")
    _add_visitor(db_session, d, 18, 0, direction="exit")
    params = {"from_date": d.isoformat(), "to_date": d.isoformat()}

    r = client.get("/supervisor/visitors/summary", headers=chief_headers, params=params)
    assert r.status_code == 200
    body = r.json()
    assert body["total_events"] == 3
    assert body["entries"] == 2
    assert body["exits"] == 1


def test_visitor_summary_respects_date_range(client, chief_headers, db_session):
    d1 = _recent_working_day(1)
    d_outside = _recent_working_day(30)
    _add_visitor(db_session, d1, 9, 0, direction="entry")
    _add_visitor(db_session, d_outside, 9, 0, direction="entry")

    r = client.get(
        "/supervisor/visitors/summary",
        headers=chief_headers,
        params={"from_date": d1.isoformat(), "to_date": d1.isoformat()},
    )
    assert r.json()["total_events"] == 1


def test_visitor_summary_ignores_employee_events(client, chief_headers, db_session):
    """Seeded employee camera events must not count as visitors."""
    d = _recent_working_day(1)
    # Don't add any visitor rows — only the seeded EMP001 camera events exist.
    r = client.get(
        "/supervisor/visitors/summary",
        headers=chief_headers,
        params={"from_date": d.isoformat(), "to_date": d.isoformat()},
    )
    assert r.json()["total_events"] == 0


def test_visitor_summary_handles_null_direction(client, chief_headers, db_session):
    """An event with no direction counts toward total but neither entry nor exit."""
    d = _recent_working_day(1)
    _add_visitor(db_session, d, 10, 0, direction=None)

    r = client.get(
        "/supervisor/visitors/summary",
        headers=chief_headers,
        params={"from_date": d.isoformat(), "to_date": d.isoformat()},
    )
    body = r.json()
    assert body["total_events"] == 1
    assert body["entries"] == 0
    assert body["exits"] == 0


# ── By-day: grouped structure, totals per day, raw events inside ────────────
def test_visitor_by_day_groups_by_day(client, chief_headers, db_session):
    d1 = _recent_working_day(1)
    d2 = _recent_working_day(2)
    _add_visitor(db_session, d1, 9, 0, direction="entry")
    _add_visitor(db_session, d1, 10, 0, direction="entry")
    _add_visitor(db_session, d2, 11, 0, direction="exit")

    r = client.get(
        "/supervisor/visitors/by-day",
        headers=chief_headers,
        params={"from_date": d2.isoformat(), "to_date": d1.isoformat()},
    )
    assert r.status_code == 200
    days = r.json()
    assert len(days) == 2
    # Sorted newest-first.
    assert days[0]["date"] == d1.isoformat()
    assert days[1]["date"] == d2.isoformat()
    assert days[0]["total_events"] == 2
    assert days[0]["entries"] == 2
    assert days[0]["exits"] == 0
    assert days[1]["total_events"] == 1
    assert days[1]["entries"] == 0
    assert days[1]["exits"] == 1


def test_visitor_by_day_includes_raw_events(client, chief_headers, db_session):
    d = _recent_working_day(1)
    _add_visitor(db_session, d, 9, 0, camera="gate-in-1", direction="entry")
    _add_visitor(db_session, d, 18, 0, camera="gate-out-2", direction="exit")

    r = client.get(
        "/supervisor/visitors/by-day",
        headers=chief_headers,
        params={"from_date": d.isoformat(), "to_date": d.isoformat()},
    )
    day = r.json()[0]
    assert len(day["events"]) == 2
    # Each event carries the drill-down fields the UI needs.
    e = day["events"][0]
    assert {"id", "camera_label", "direction", "similarity",
            "event_time", "crop_path"} <= set(e)


def test_visitor_by_day_events_sorted_newest_first(client, chief_headers, db_session):
    d = _recent_working_day(1)
    early = _add_visitor(db_session, d, 9, 0)
    late = _add_visitor(db_session, d, 18, 0)

    r = client.get(
        "/supervisor/visitors/by-day",
        headers=chief_headers,
        params={"from_date": d.isoformat(), "to_date": d.isoformat()},
    )
    events = r.json()[0]["events"]
    assert events[0]["id"] == late.id
    assert events[1]["id"] == early.id


def test_visitor_by_day_empty_for_no_visitors(client, chief_headers):
    r = client.get("/supervisor/visitors/by-day", headers=chief_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_visitor_by_day_exposes_crop_path(client, chief_headers, db_session):
    """The chief-only endpoint IS allowed to expose crop_path (vs the
    privacy-protected employee endpoint which hides it in AttendanceEventOut)."""
    d = _recent_working_day(1)
    _add_visitor(db_session, d, 9, 0,
                 crop_path="gate-1/crops/2026-10-30/gate-in-1/visitor.jpg")

    r = client.get(
        "/supervisor/visitors/by-day",
        headers=chief_headers,
        params={"from_date": d.isoformat(), "to_date": d.isoformat()},
    )
    e = r.json()[0]["events"][0]
    assert e["crop_path"] == "gate-1/crops/2026-10-30/gate-in-1/visitor.jpg"


# ── Crop endpoint ───────────────────────────────────────────────────────────
def test_visitor_crop_serves_bytes(client, chief_headers, db_session, monkeypatch):
    d = _recent_working_day(1)
    ev = _add_visitor(db_session, d, 9, 0, crop_path="gate-1/crops/x.jpg")
    sample = b"\xff\xd8\xff\xe0JFIF_visitor"
    monkeypatch.setattr(storage, "load_camera_crop", lambda path: sample)

    r = client.get(f"/supervisor/visitors/events/{ev.id}/crop", headers=chief_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/jpeg")
    assert r.content == sample


def test_visitor_crop_404_for_employee_event(client, chief_headers, db_session):
    """Trying to fetch an employee event's crop through the visitor endpoint -> 404."""
    emp_ev = db_session.query(AttendanceEvent).filter_by(source="camera").filter(
        AttendanceEvent.is_visitor.is_(False)
    ).first()
    assert emp_ev is not None
    r = client.get(f"/supervisor/visitors/events/{emp_ev.id}/crop", headers=chief_headers)
    assert r.status_code == 404


def test_visitor_crop_404_without_crop_path(client, chief_headers, db_session):
    d = _recent_working_day(1)
    ev = _add_visitor(db_session, d, 9, 0, crop_path=None)
    r = client.get(f"/supervisor/visitors/events/{ev.id}/crop", headers=chief_headers)
    assert r.status_code == 404


def test_visitor_crop_404_when_blob_missing(client, chief_headers, db_session, monkeypatch):
    d = _recent_working_day(1)
    ev = _add_visitor(db_session, d, 9, 0, crop_path="gate-1/crops/missing.jpg")
    monkeypatch.setattr(storage, "load_camera_crop", lambda path: None)

    r = client.get(f"/supervisor/visitors/events/{ev.id}/crop", headers=chief_headers)
    assert r.status_code == 404


def test_visitor_crop_404_for_unknown_event(client, chief_headers):
    assert client.get("/supervisor/visitors/events/99999/crop",
                      headers=chief_headers).status_code == 404


# ── Boundary: visitor endpoints only match real visitor rows ────────────────
def test_visitor_summary_ignores_field_source_visitors(client, chief_headers, db_session):
    """Field scans can't create visitors, but defensively: even if a row has
    is_visitor=True AND source=field, the crop endpoint still refuses it."""
    d = _recent_working_day(1)
    ev = AttendanceEvent(
        person_id=None, is_visitor=True, camera_label="field-somewhere",
        direction="entry", source="field", event_time=_utc(d, 9, 0),
        crop_path="gate-1/crops/x.jpg",
    )
    db_session.add(ev)
    db_session.commit()

    # The summary endpoint counts anything is_visitor=True (defensive).
    r = client.get(
        "/supervisor/visitors/summary",
        headers=chief_headers,
        params={"from_date": d.isoformat(), "to_date": d.isoformat()},
    )
    assert r.json()["total_events"] == 1
    # But the crop endpoint refuses non-camera rows.
    r2 = client.get(f"/supervisor/visitors/events/{ev.id}/crop", headers=chief_headers)
    assert r2.status_code == 404