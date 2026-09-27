"""Executive Assistant delegation: field approvals + attendance edits, recall, scope."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import settings
from app.db.models import AttendanceEvent, Person, Station

IST = ZoneInfo(settings.display_timezone)
UTC = ZoneInfo("UTC")


def _utc(d: date, hh: int, mm: int) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=IST).astimezone(UTC).replace(tzinfo=None)


def _recent_working_day(offset: int) -> date:
    d = date.today() - timedelta(days=offset)
    while d.weekday() == 6:
        d -= timedelta(days=1)
    return d


def _make_pending_field(db, external_id="EMP001") -> int:
    """A pending field scan for an Operations employee (SUP001's department)."""
    p = db.query(Person).filter_by(external_id=external_id).one()
    st = db.query(Station).first()
    ev = AttendanceEvent(
        person_id=p.id, camera_label=f"field-{st.name}", direction="entry",
        source="field", event_time=_utc(_recent_working_day(1), 9, 20),
        review_status="pending", location_verified=False,
        latitude=st.center_lat, longitude=st.center_lon,
        gps_accuracy_m=30.0, distance_m=300.0, nearest_station_id=st.id,
        similarity=0.6,
    )
    db.add(ev)
    db.commit()
    return ev.id


# ── Field-approval delegation ────────────────────────────────────────────────
def test_delegate_field_flows_to_ea_and_completes(client, sup_headers, ea_headers, db_session):
    event_id = _make_pending_field(db_session)

    # Supervisor delegates the scan.
    r = client.post("/supervisor/field/approvals/delegate", headers=sup_headers,
                    json={"event_ids": [event_id], "comment": "Please verify this one."})
    assert r.status_code == 200, r.text
    assert r.json()["delegated"] == 1

    # It's now marked delegated on the supervisor's own list.
    fa = client.get("/supervisor/field/approvals", headers=sup_headers).json()
    row = next(x for x in fa if x["event_id"] == event_id)
    assert row["delegated"] is True

    # The EA sees exactly this field task.
    tasks = client.get("/assistant/tasks?type=field_approval", headers=ea_headers).json()
    assert len(tasks) == 1
    task = tasks[0]
    assert task["field"]["event_id"] == event_id
    assert task["comment"] == "Please verify this one."

    # EA approves → task completed and drops off the queue.
    ok = client.post(f"/assistant/tasks/{task['id']}/field/approve", headers=ea_headers, json={})
    assert ok.status_code == 200
    assert client.get("/assistant/tasks?type=field_approval", headers=ea_headers).json() == []

    # And the underlying scan is approved.
    ev = db_session.get(AttendanceEvent, event_id)
    db_session.refresh(ev)
    assert ev.review_status == "approved"


def test_delegate_requires_an_ea(client, sup2_headers, db_session):
    # SUP002 (Signals) has no EA in the fixture → cannot delegate.
    p = db_session.query(Person).filter_by(external_id="EMP003").one()
    st = db_session.query(Station).first()
    ev = AttendanceEvent(
        person_id=p.id, camera_label="field-x", direction="entry", source="field",
        event_time=_utc(_recent_working_day(1), 9, 0), review_status="pending",
        nearest_station_id=st.id,
    )
    db_session.add(ev); db_session.commit()
    r = client.post("/supervisor/field/approvals/delegate", headers=sup2_headers,
                    json={"event_ids": [ev.id]})
    assert r.status_code == 400


def test_recall_removes_task_from_ea(client, sup_headers, ea_headers, db_session):
    event_id = _make_pending_field(db_session)
    client.post("/supervisor/field/approvals/delegate", headers=sup_headers,
                json={"event_ids": [event_id]})
    task = client.get("/assistant/tasks?type=field_approval", headers=ea_headers).json()[0]

    rc = client.post(f"/supervisor/tasks/{task['id']}/recall", headers=sup_headers)
    assert rc.status_code == 200
    # Gone from the EA queue; acting on it now fails.
    assert client.get("/assistant/tasks?type=field_approval", headers=ea_headers).json() == []
    late = client.post(f"/assistant/tasks/{task['id']}/field/approve", headers=ea_headers, json={})
    assert late.status_code == 409


# ── Attendance-edit delegation ───────────────────────────────────────────────
def test_delegate_attendance_requires_comment(client, sup_headers, seed_dates):
    r = client.post("/supervisor/attendance/delegate", headers=sup_headers,
                    json={"external_id": "EMP001", "for_date": seed_dates["present"], "comment": "  "})
    assert r.status_code == 400


def test_delegate_attendance_edit_and_mark_complete(client, sup_headers, ea_headers, seed_dates, db_session):
    day = seed_dates["present"]
    r = client.post("/supervisor/attendance/delegate", headers=sup_headers,
                    json={"external_id": "EMP001", "for_date": day, "comment": "Fix the exit time."})
    assert r.status_code == 200, r.text

    tasks = client.get("/assistant/tasks?type=attendance_edit", headers=ea_headers).json()
    assert len(tasks) == 1
    task = tasks[0]
    assert task["external_id"] == "EMP001"
    assert task["for_date"] == day
    assert task["day"] is not None

    # EA edits an in/out crossing on that day.
    d = client.get(f"/assistant/tasks/{task['id']}/day", headers=ea_headers).json()
    ev = next(e for e in d["events"] if e["direction"] in ("entry", "exit"))
    edited = client.patch(f"/assistant/tasks/{task['id']}/events/{ev['id']}",
                          headers=ea_headers, json={"time": "10:00"})
    assert edited.status_code == 200

    # Then marks the task complete → drops off the queue.
    done = client.post(f"/assistant/tasks/{task['id']}/complete", headers=ea_headers)
    assert done.status_code == 200
    assert client.get("/assistant/tasks?type=attendance_edit", headers=ea_headers).json() == []


def test_ea_cannot_edit_outside_delegated_day(client, sup_headers, ea_headers, seed_dates, db_session):
    # Delegate the 'present' day, then try to touch a crossing from the 'late' day.
    client.post("/supervisor/attendance/delegate", headers=sup_headers,
                json={"external_id": "EMP001", "for_date": seed_dates["present"], "comment": "x"})
    task = client.get("/assistant/tasks?type=attendance_edit", headers=ea_headers).json()[0]
    # A crossing that belongs to a different day.
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    other = db_session.query(AttendanceEvent).filter(
        AttendanceEvent.person_id == emp1.id,
        AttendanceEvent.event_time < _utc(date.fromisoformat(seed_dates["late"]), 23, 59),
        AttendanceEvent.event_time > _utc(date.fromisoformat(seed_dates["late"]), 0, 0),
    ).first()
    r = client.patch(f"/assistant/tasks/{task['id']}/events/{other.id}",
                     headers=ea_headers, json={"time": "09:00"})
    assert r.status_code == 404


# ── Access control ───────────────────────────────────────────────────────────
def test_tasks_require_assistant(client, emp_headers, sup_headers):
    assert client.get("/assistant/tasks", headers=emp_headers).status_code == 403
    assert client.get("/assistant/tasks", headers=sup_headers).status_code == 403


def test_assistant_profile_shows_supervisor(client, ea_headers):
    r = client.get("/assistant/profile", headers=ea_headers)
    assert r.status_code == 200
    assert r.json()["supervisor_external_id"] == "SUP001"
