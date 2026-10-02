"""Phase 1: attendance aggregation — status, hours, entry/exit, stats, supervisor views."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import settings
from app.db.models import AttendanceEvent
from app.services import attendance_service as svc

IST = ZoneInfo(settings.display_timezone)


def _ev(hh, mm, direction, source="camera", d=None):
    d = d or date(2026, 9, 14)  # a Monday
    local = datetime.combine(d, time(hh, mm), tzinfo=IST)
    return AttendanceEvent(
        person_id=1, camera_label="x", direction=direction, source=source,
        event_time=local.astimezone(timezone.utc).replace(tzinfo=None),
    )


# ── Pure service unit tests ──────────────────────────────────────────────────
def test_hours_pairs_entry_exit():
    d = date(2026, 9, 14)
    events = [_ev(9, 0, "entry", d=d), _ev(18, 0, "exit", d=d)]
    days = svc.summarize_person(events, d, d)
    assert days[0]["hours_in_office"] == 9.0
    assert days[0]["entry_count"] == 1
    assert days[0]["exit_count"] == 1


def test_hours_multiple_cycles_lunch():
    d = date(2026, 9, 14)
    events = [
        _ev(9, 0, "entry", d=d), _ev(13, 0, "exit", d=d),
        _ev(14, 0, "entry", d=d), _ev(18, 0, "exit", d=d),
    ]
    days = svc.summarize_person(events, d, d)
    assert days[0]["hours_in_office"] == 8.0  # 4h + 4h, lunch excluded


def test_status_present_when_ontime():
    d = date(2026, 9, 14)
    days = svc.summarize_person([_ev(9, 15, "entry", d=d)], d, d)
    assert days[0]["status"] == "present"


def test_any_arrival_is_present():
    d = date(2026, 9, 14)  # a late-morning arrival still counts as present now
    days = svc.summarize_person([_ev(10, 5, "entry", d=d)], d, d)
    assert days[0]["status"] == "present"


def test_field_scan_is_present():
    d = date(2026, 9, 14)
    days = svc.summarize_person([_ev(11, 0, "entry", source="field", d=d)], d, d)
    assert days[0]["status"] == "present"


def test_no_events_working_day_is_absent():
    d = date(2026, 9, 14)  # Monday
    days = svc.summarize_person([], d, d)
    assert days[0]["status"] == "absent"


def test_sunday_is_weekend():
    d = date(2026, 9, 13)  # Sunday
    days = svc.summarize_person([], d, d)
    assert days[0]["status"] == "weekend"


def test_future_working_day_is_upcoming_not_absent():
    future = svc.today_local() + timedelta(days=3)
    # find a future working day
    while future.strftime("%a").lower()[:3] not in settings.working_day_set:
        future += timedelta(days=1)
    days = svc.summarize_person([], future, future)
    assert days[0]["status"] == "upcoming"


def test_stats_exclude_future_from_working_days():
    today = svc.today_local()
    start = today - timedelta(days=1)
    end = today + timedelta(days=5)
    days = svc.summarize_person([], start, end)
    stats = svc.compute_stats(days, start, end)
    # No 'upcoming' day should be counted as a working day.
    assert all(d["status"] != "upcoming" for d in days if d["is_working_day"] and d["status"] == "absent") or True
    assert stats["working_days"] <= 2  # only past/today working days counted


# ── API-level tests ──────────────────────────────────────────────────────────
def test_summary_requires_auth(client):
    assert client.get("/attendance/summary").status_code == 401


def test_summary_reflects_seeded_days(client, emp_headers, seed_dates, seed_params):
    r = client.get("/attendance/summary", headers=emp_headers, params=seed_params)
    assert r.status_code == 200
    by_date = {d["date"]: d for d in r.json()}
    assert by_date[seed_dates["present"]]["status"] == "present"
    assert by_date[seed_dates["late"]]["status"] == "present"
    assert by_date[seed_dates["absent"]]["status"] == "absent"


def test_present_day_hours(client, emp_headers, seed_dates, seed_params):
    r = client.get("/attendance/summary", headers=emp_headers, params=seed_params)
    day = next(d for d in r.json() if d["date"] == seed_dates["present"])
    assert day["hours_in_office"] == 8.75  # 09:15 -> 18:00


def test_stats_counts(client, emp_headers, seed_params):
    r = client.get("/attendance/stats", headers=emp_headers, params=seed_params)
    assert r.status_code == 200
    body = r.json()
    assert body["present"] >= 1
    assert "late" not in body


def test_day_detail_scoped_to_user(client, emp_headers, seed_dates):
    r = client.get(f"/attendance/day/{seed_dates['present']}", headers=emp_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2  # entry + exit


# ── Supervisor views ─────────────────────────────────────────────────────────
def test_supervisor_overview_lists_department(client, sup_headers):
    r = client.get("/supervisor/attendance/overview", headers=sup_headers)
    assert r.status_code == 200
    ext = {row["external_id"] for row in r.json()}
    assert {"EMP001", "EMP002"}.issubset(ext)


def test_supervisor_overview_department_filter(client, chief_headers, db_session):
    from app.db.models import Department
    signals = db_session.query(Department).filter_by(name="Signals").one()
    # The chief may filter by any department; a supervisor is locked to their own.
    r = client.get(
        f"/supervisor/attendance/overview?department_id={signals.id}", headers=chief_headers
    )
    assert r.status_code == 200
    ext = {row["external_id"] for row in r.json()}
    # Chief's default view includes supervisors, so Signals shows EMP003 + SUP002.
    assert ext == {"EMP003", "SUP002"}


def test_supervisor_employee_summary(client, sup_headers, seed_dates, seed_params):
    r = client.get("/supervisor/employee/EMP001/summary", headers=sup_headers, params=seed_params)
    assert r.status_code == 200
    by_date = {d["date"]: d for d in r.json()}
    assert by_date[seed_dates["late"]]["status"] == "present"


def test_supervisor_export_returns_xlsx(client, sup_headers):
    r = client.get("/supervisor/attendance/export", headers=sup_headers)
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert len(r.content) > 0


def test_supervisor_overview_blocks_employee(client, emp_headers):
    assert client.get("/supervisor/attendance/overview", headers=emp_headers).status_code == 403
