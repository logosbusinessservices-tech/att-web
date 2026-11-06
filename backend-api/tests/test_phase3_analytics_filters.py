"""Phase 1 analytics-filter refactor: roles (person) + sources (event capture).

Covers the two new filters and the backward-compatibility of the legacy `types`
param. The headline fix: a person with `field_scan_enabled=True` must STILL be
counted as present on a day when the camera caught them, which the old filter
model silently hid.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import settings
from app.db.models import AttendanceEvent, Person
from app.services import analytics

IST = ZoneInfo(settings.display_timezone)


# ── Small helpers ───────────────────────────────────────────────────────────
def _utc(d: date, hh: int, mm: int) -> datetime:
    """IST wall-clock -> naive-UTC datetime (how the pipeline stores events)."""
    local = datetime.combine(d, time(hh, mm), tzinfo=IST)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _recent_working_day(offset: int) -> date:
    d = date.today() - timedelta(days=offset)
    while d.weekday() == 6:
        d -= timedelta(days=1)
    return d


def _add_field_event(db, person_id, d, hh, mm, direction="entry"):
    """Add a field-source event for a person on a given day."""
    ev = AttendanceEvent(
        person_id=person_id, camera_label=f"field-{d.isoformat()}",
        direction=direction, source="field", event_time=_utc(d, hh, mm),
    )
    db.add(ev)
    db.commit()
    return ev


def _add_manual_event(db, person_id, d, hh, mm, direction="entry"):
    ev = AttendanceEvent(
        person_id=person_id, camera_label="manual",
        direction=direction, source="manual", event_time=_utc(d, hh, mm),
    )
    db.add(ev)
    db.commit()
    return ev


# ── _roles_set: new param + legacy translation ──────────────────────────────
def test_roles_set_parses_new_param():
    assert analytics._roles_set("employee") == {"employee"}
    assert analytics._roles_set("supervisor") == {"supervisor"}
    assert analytics._roles_set("employee,supervisor") == {"employee", "supervisor"}


def test_roles_set_ignores_unknown_values():
    # Garbage values are dropped; nothing valid -> None (callers apply default).
    assert analytics._roles_set("junk") is None
    assert analytics._roles_set("employee,junk") == {"employee"}


def test_roles_set_legacy_field_maps_to_employee():
    # The BUG FIX: old "field" filter used to exclude people without
    # field_scan_enabled. It now just means "employees".
    assert analytics._roles_set(None, types="field") == {"employee"}


def test_roles_set_legacy_office_maps_to_employee():
    assert analytics._roles_set(None, types="office") == {"employee"}


def test_roles_set_legacy_supervisor_still_supervisor():
    assert analytics._roles_set(None, types="supervisor") == {"supervisor"}


def test_roles_set_legacy_combo():
    assert analytics._roles_set(None, types="field,supervisor") == {"employee", "supervisor"}
    assert analytics._roles_set(None, types="field,office,supervisor") == {"employee", "supervisor"}


def test_roles_set_empty_returns_none():
    assert analytics._roles_set(None) is None
    assert analytics._roles_set("") is None
    assert analytics._roles_set(None, types="") is None


def test_roles_set_new_param_wins_over_legacy():
    # When both are sent, the explicit new param is authoritative.
    assert analytics._roles_set("supervisor", types="field") == {"supervisor"}


# ── _sources_set: auto-revert behaviour ─────────────────────────────────────
def test_sources_set_defaults_to_all_three():
    all_three = {"camera", "field", "manual"}
    assert analytics._sources_set(None) == all_three
    assert analytics._sources_set("") == all_three


def test_sources_set_parses_single():
    assert analytics._sources_set("camera") == {"camera"}
    assert analytics._sources_set("field") == {"field"}
    assert analytics._sources_set("manual") == {"manual"}


def test_sources_set_parses_subset():
    assert analytics._sources_set("camera,field") == {"camera", "field"}


def test_sources_set_auto_reverts_when_all_invalid():
    # Edge-case rule: if nothing valid was picked, auto-revert to all three.
    # This matches the UI (unchecking everything flips back to all checked).
    all_three = {"camera", "field", "manual"}
    assert analytics._sources_set("junk") == all_three
    assert analytics._sources_set("nothing,nada") == all_three


def test_sources_set_drops_unknown_values():
    assert analytics._sources_set("camera,junk") == {"camera"}


# ── _people: no longer filters by field_scan_enabled ────────────────────────
def test_people_default_returns_employees_only(db_session):
    people = analytics._people(db_session, department_id=None)
    roles = {p.role for p in people}
    assert roles == {"employee"}


def test_people_with_roles_supervisor(db_session):
    people = analytics._people(db_session, department_id=None, roles="supervisor")
    roles = {p.role for p in people}
    assert roles == {"supervisor"}


def test_people_with_roles_both(db_session):
    people = analytics._people(db_session, department_id=None,
                               roles="employee,supervisor")
    roles = {p.role for p in people}
    assert {"employee", "supervisor"}.issubset(roles)


def test_people_legacy_field_includes_everyone_with_field_enabled_or_not(db_session):
    """THE BUG FIX regression test.

    Old behaviour: types=field -> only people with field_scan_enabled=True.
    New behaviour: types=field -> all employees (field is now a CAPTURE filter,
    not a person filter).
    """
    # Flip just one person's field_scan_enabled on.
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    emp1.field_scan_enabled = True
    db_session.commit()

    people = analytics._people(db_session, department_id=None, types="field")
    ids = {p.external_id for p in people}
    # Both EMP001 (field_scan on) AND EMP002 (field_scan off) are included.
    # Under the old code this test would have returned only {'EMP001'}.
    assert {"EMP001", "EMP002"}.issubset(ids)


def test_people_legacy_office_same_as_employee(db_session):
    """types=office and types=field should return the SAME people now —
    both simply mean 'employees'. The old code treated them as opposites."""
    office = {p.external_id for p in analytics._people(db_session, department_id=None, types="office")}
    field = {p.external_id for p in analytics._people(db_session, department_id=None, types="field")}
    assert office == field


# ── _person_days: capture-type filter downgrades days ───────────────────────
def test_person_days_all_sources_keeps_present(db_session, seed_dates):
    """With all sources selected the seeded camera day stays present."""
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    present_day = date.fromisoformat(seed_dates["present"])
    days = analytics._person_days(
        db_session, emp1, present_day, present_day,
        sources={"camera", "field", "manual"},
    )
    assert days[0]["status"] == "present"


def test_person_days_camera_only_keeps_camera_day(db_session, seed_dates):
    """Seeded day was captured by camera; camera filter keeps it present."""
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    present_day = date.fromisoformat(seed_dates["present"])
    days = analytics._person_days(
        db_session, emp1, present_day, present_day,
        sources={"camera"},
    )
    assert days[0]["status"] == "present"
    assert days[0]["hours_in_office"] > 0


def test_person_days_field_only_downgrades_camera_day(db_session, seed_dates):
    """With Field-only filter, a camera-only day becomes absent and 0 hours."""
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    present_day = date.fromisoformat(seed_dates["present"])
    days = analytics._person_days(
        db_session, emp1, present_day, present_day,
        sources={"field"},
    )
    assert days[0]["status"] == "absent"
    assert days[0]["hours_in_office"] == 0.0


def test_person_days_field_event_shows_under_field_filter(db_session, seed_dates):
    """Add a field event — Field-only filter should now count that day."""
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    # Pick a fresh working day that has NO seeded camera events.
    d = _recent_working_day(10)
    _add_field_event(db_session, emp1.id, d, 10, 0)

    days = analytics._person_days(
        db_session, emp1, d, d, sources={"field"},
    )
    assert days[0]["status"] == "present"


def test_person_days_mixed_sources_keeps_present_with_either(db_session):
    """Same day has BOTH a field event and a camera event.
    Filtering by either source should show the day as present."""
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    d = _recent_working_day(11)
    # Field at 9am.
    _add_field_event(db_session, emp1.id, d, 9, 0)
    # Camera at 6pm (same day).
    cam = AttendanceEvent(
        person_id=emp1.id, camera_label="gate-out-1", direction="exit",
        source="camera", event_time=_utc(d, 18, 0),
    )
    db_session.add(cam)
    db_session.commit()

    for picked in ({"camera"}, {"field"}, {"camera", "field"}):
        days = analytics._person_days(db_session, emp1, d, d, sources=picked)
        assert days[0]["status"] == "present", f"filter {picked}"


def test_person_days_weekend_untouched_by_filter(db_session):
    """Weekend days stay weekend regardless of capture filter."""
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    # Sundays are weekends in the default config.
    sunday = date.today()
    while sunday.weekday() != 6:
        sunday -= timedelta(days=1)
    days = analytics._person_days(
        db_session, emp1, sunday, sunday, sources={"camera"},
    )
    assert days[0]["status"] == "weekend"


def test_person_days_absent_day_stays_absent(db_session, seed_dates):
    """An already-absent day stays absent (not re-labeled) under any filter."""
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    absent_day = date.fromisoformat(seed_dates["absent"])
    for picked in ({"camera"}, {"field"}, {"manual"}):
        days = analytics._person_days(
            db_session, emp1, absent_day, absent_day, sources=picked,
        )
        assert days[0]["status"] == "absent"


# ── Endpoint-level: new params, backward compat, regression ─────────────────
def test_summary_with_roles_supervisor(client, sup_headers, seed_params):
    r = client.get(
        "/supervisor/analytics/summary",
        headers=sup_headers,
        params={**seed_params, "roles": "supervisor"},
    )
    assert r.status_code == 200
    # SUP001 is the only supervisor in Operations.
    assert r.json()["active_employees"] == 1


def test_summary_with_roles_both(client, sup_headers, seed_params):
    r = client.get(
        "/supervisor/analytics/summary",
        headers=sup_headers,
        params={**seed_params, "roles": "employee,supervisor"},
    )
    # EMP001 + EMP002 + SUP001 in Operations.
    assert r.json()["active_employees"] == 3


def test_summary_sources_camera_only(client, sup_headers, seed_params):
    """Seeded events are all camera, so Camera-only filter keeps present count."""
    r = client.get(
        "/supervisor/analytics/summary",
        headers=sup_headers,
        params={**seed_params, "sources": "camera"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["present"] >= 1


def test_summary_sources_field_only_hides_camera_days(client, sup_headers, seed_params):
    """Seeded days are all camera -> Field-only filter shows them as absent."""
    r = client.get(
        "/supervisor/analytics/summary",
        headers=sup_headers,
        params={**seed_params, "sources": "field"},
    )
    assert r.status_code == 200
    # No field events seeded -> present should drop to zero.
    assert r.json()["present"] == 0


def test_summary_empty_sources_auto_reverts(client, sup_headers, seed_params):
    """Empty sources param behaves like all three selected."""
    r_empty = client.get(
        "/supervisor/analytics/summary",
        headers=sup_headers,
        params={**seed_params, "sources": ""},
    )
    r_default = client.get(
        "/supervisor/analytics/summary",
        headers=sup_headers,
        params=seed_params,
    )
    assert r_empty.json()["present"] == r_default.json()["present"]


def test_summary_legacy_types_field_backward_compat(client, sup_headers, seed_params):
    """Old URL ?types=field still works: it now means 'employees'.

    Before the fix this returned only field_scan_enabled employees; it should
    now behave like the default employee list.
    """
    r = client.get(
        "/supervisor/analytics/summary",
        headers=sup_headers,
        params={**seed_params, "types": "field"},
    )
    assert r.status_code == 200
    # EMP001 + EMP002, same as the default view.
    assert r.json()["active_employees"] == 2


def test_summary_legacy_types_office_matches_field(client, sup_headers, seed_params):
    """types=office and types=field must return identical counts post-fix."""
    r_office = client.get(
        "/supervisor/analytics/summary", headers=sup_headers,
        params={**seed_params, "types": "office"},
    )
    r_field = client.get(
        "/supervisor/analytics/summary", headers=sup_headers,
        params={**seed_params, "types": "field"},
    )
    assert r_office.json()["active_employees"] == r_field.json()["active_employees"]
    assert r_office.json()["present"] == r_field.json()["present"]


def test_regression_field_enabled_employee_still_visible_under_camera(
    client, sup_headers, db_session, seed_params,
):
    """THE REGRESSION TEST.

    Scenario that produced the bug: an employee has field_scan_enabled=True
    because we let them log attendance from home while cameras were broken.
    After the cameras were fixed, their camera-captured attendance disappeared
    from the dashboard because the UI filtered them out as a "field employee".
    They should now appear under the Camera capture filter as well.
    """
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    emp1.field_scan_enabled = True
    db_session.commit()

    r = client.get(
        "/supervisor/analytics/summary",
        headers=sup_headers,
        params={**seed_params, "sources": "camera"},
    )
    assert r.status_code == 200
    body = r.json()
    # Before the fix this came back as 0 (everyone with field_scan was excluded).
    # After the fix EMP001's seeded camera day shows up.
    assert body["present"] >= 1
    # And active_employees is still the full employee list for Operations.
    assert body["active_employees"] == 2


def test_source_split_respects_capture_filter(client, sup_headers, seed_params):
    """When the filter is Camera-only, the pie should show zeros for others."""
    r = client.get(
        "/supervisor/analytics/source-split",
        headers=sup_headers,
        params={**seed_params, "sources": "camera"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["camera"] >= 4         # seeded crossings
    assert body["field"] == 0          # filtered out
    assert body["manual"] == 0


def test_source_split_includes_all_when_default(client, sup_headers, db_session, seed_params):
    """Default (no filter) should include manual and field events too."""
    emp1 = db_session.query(Person).filter_by(external_id="EMP001").one()
    # Put the manual event INSIDE the seed_params window so it's counted.
    d = date.fromisoformat(seed_params["from_date"])
    _add_manual_event(db_session, emp1.id, d, 10, 0)

    r = client.get(
        "/supervisor/analytics/source-split",
        headers=sup_headers,
        params=seed_params,
    )
    body = r.json()
    assert body["manual"] >= 1


def test_overview_with_roles_and_sources(client, sup_headers, seed_params):
    """The /supervisor/attendance/overview endpoint accepts the new filters."""
    r = client.get(
        "/supervisor/attendance/overview",
        headers=sup_headers,
        params={**seed_params, "roles": "employee", "sources": "camera"},
    )
    assert r.status_code == 200
    rows = r.json()
    # EMP001's seeded camera days should be visible.
    row = next(x for x in rows if x["external_id"] == "EMP001")
    assert row["present"] >= 1


def test_overview_sources_field_only_zeroes_camera_days(client, sup_headers, seed_params):
    """Sanity: Field-only filter should hide EMP001's camera-only days."""
    r = client.get(
        "/supervisor/attendance/overview",
        headers=sup_headers,
        params={**seed_params, "sources": "field"},
    )
    rows = r.json()
    row = next(x for x in rows if x["external_id"] == "EMP001")
    assert row["present"] == 0
    assert row["total_hours"] == 0.0


def test_overview_legacy_types_still_works(client, sup_headers, seed_params):
    """The old `?types=supervisor` param on overview still filters correctly."""
    r = client.get(
        "/supervisor/attendance/overview",
        headers=sup_headers,
        params={**seed_params, "types": "supervisor"},
    )
    assert r.status_code == 200
    assert all(row["external_id"].startswith("SUP") for row in r.json())


# ── Chief default behaviour unchanged ───────────────────────────────────────
def test_chief_default_still_includes_supervisors(client, chief_headers, seed_params):
    """Chief's default view (no roles param) still includes both roles."""
    r = client.get(
        "/supervisor/analytics/summary",
        headers=chief_headers,
        params=seed_params,
    )
    assert r.status_code == 200
    # Org has 3 employees + 3 supervisors + 1 chief + 1 assistant.
    # Chief default sees employees + supervisors across all departments.
    # Exact number depends on seed; just verify > the employee-only count.
    r_emp_only = client.get(
        "/supervisor/analytics/summary",
        headers=chief_headers,
        params={**seed_params, "roles": "employee"},
    )
    assert r.json()["active_employees"] > r_emp_only.json()["active_employees"]


def test_chief_explicit_roles_overrides_default(client, chief_headers, seed_params):
    """Chief explicitly picking 'employee' should drop supervisors from view."""
    r = client.get(
        "/supervisor/analytics/summary",
        headers=chief_headers,
        params={**seed_params, "roles": "employee"},
    )
    # EMP001 + EMP002 + EMP003 = 3 employees org-wide.
    assert r.json()["active_employees"] == 3