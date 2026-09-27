"""New Phase-2 behaviour: inline events, targeted (entry/exit) disputes, and the
entry/exit sequence validator + anomaly detection."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import settings
from app.db.models import AttendanceEvent
from app.services import attendance_service as svc

IST = ZoneInfo(settings.display_timezone)


def _ev(hh, mm, direction, d, source="camera"):
    local = datetime.combine(d, time(hh, mm), tzinfo=IST)
    return AttendanceEvent(
        id=None, person_id=1, camera_label="x", direction=direction, source=source,
        event_time=local.astimezone(timezone.utc).replace(tzinfo=None),
    )


# ── Anomaly detector (pure) ──────────────────────────────────────────────────
def test_double_exit_flagged():
    d = date(2026, 9, 14)
    seq = [_ev(9, 0, "entry", d), _ev(14, 0, "exit", d), _ev(17, 0, "exit", d)]
    a = svc.detect_anomalies(seq)
    assert any(x["type"] == "missing_entry" for x in a)


def test_double_entry_flagged():
    d = date(2026, 9, 14)
    seq = [_ev(9, 0, "entry", d), _ev(10, 0, "entry", d), _ev(18, 0, "exit", d)]
    a = svc.detect_anomalies(seq)
    assert any(x["type"] == "missing_exit" for x in a)


def test_clean_sequence_no_anomaly():
    d = date(2026, 9, 14)
    seq = [_ev(9, 0, "entry", d), _ev(13, 0, "exit", d), _ev(14, 0, "entry", d), _ev(18, 0, "exit", d)]
    assert svc.detect_anomalies(seq) == []


# ── Inline events in the summary ─────────────────────────────────────────────
def test_summary_includes_events_inline(client, emp_headers, seed_dates):
    r = client.get("/attendance/summary", headers=emp_headers)
    day = next(d for d in r.json() if d["date"] == seed_dates["present"])
    assert len(day["events"]) == 2
    assert {e["direction"] for e in day["events"]} == {"entry", "exit"}


# ── Targeted entry/exit disputes ─────────────────────────────────────────────
def _present_day_events(client, emp_headers, seed_dates):
    r = client.get("/attendance/summary", headers=emp_headers)
    day = next(d for d in r.json() if d["date"] == seed_dates["present"])
    return day["events"]


def test_entry_dispute_alters_only_entry(client, emp_headers, sup_headers, seed_dates):
    events = _present_day_events(client, emp_headers, seed_dates)
    entry = next(e for e in events if e["direction"] == "entry")
    r = client.post("/disputes", headers=emp_headers, json={
        "for_date": seed_dates["present"], "target_kind": "entry",
        "event_id": entry["id"], "message": "camera saw me late; I was in at 09:00",
    })
    assert r.status_code == 200
    did = r.json()["id"]

    # Supervisor corrects the entry to 09:00 -> hours grow to 9.0.
    r = client.post(f"/supervisor/disputes/{did}/approve", headers=sup_headers,
                    json={"entry_time": "09:00"})
    assert r.status_code == 200
    day = next(d for d in client.get("/attendance/summary", headers=emp_headers).json()
               if d["date"] == seed_dates["present"])
    assert day["hours_in_office"] == 9.0
    assert day["adjusted"] is True


def test_entry_dispute_requires_entry_time(client, emp_headers, sup_headers, seed_dates):
    events = _present_day_events(client, emp_headers, seed_dates)
    entry = next(e for e in events if e["direction"] == "entry")
    did = client.post("/disputes", headers=emp_headers, json={
        "for_date": seed_dates["present"], "target_kind": "entry", "event_id": entry["id"],
    }).json()["id"]
    # Approving with only an exit time is rejected for an entry dispute.
    r = client.post(f"/supervisor/disputes/{did}/approve", headers=sup_headers,
                    json={"exit_time": "19:00"})
    assert r.status_code == 400


def test_dispute_wrong_direction_rejected(client, emp_headers, seed_dates):
    events = _present_day_events(client, emp_headers, seed_dates)
    entry = next(e for e in events if e["direction"] == "entry")
    # Claiming an entry crossing is an 'exit' dispute must fail.
    r = client.post("/disputes", headers=emp_headers, json={
        "for_date": seed_dates["present"], "target_kind": "exit", "event_id": entry["id"],
    })
    assert r.status_code == 400


def test_cannot_dispute_another_users_event(client, emp2_headers, emp_headers, seed_dates):
    events = _present_day_events(client, emp_headers, seed_dates)  # EMP001's events
    entry = next(e for e in events if e["direction"] == "entry")
    r = client.post("/disputes", headers=emp2_headers, json={
        "for_date": seed_dates["present"], "target_kind": "entry", "event_id": entry["id"],
    })
    assert r.status_code == 404


# ── Sequence validation on correction ────────────────────────────────────────
def test_override_rejects_entry_while_inside(client, sup_headers, emp_headers, seed_dates):
    # present day = [entry 09:15, exit 18:00]. Adding an entry at 12:00 is impossible
    # (already inside) -> rejected with a helpful message.
    r = client.post("/supervisor/overrides", headers=sup_headers, json={
        "external_id": "EMP001", "for_date": seed_dates["present"],
        "entry_time": "12:00", "reason": "test",
    })
    assert r.status_code == 400
    assert "entr" in r.json()["detail"].lower()


def test_override_fixes_double_exit_by_adding_entry(client, sup_headers, emp_headers, db_session):
    # Manufacture a double-exit anomaly for EMP002, then fix it.
    from app.db.models import Person
    emp2 = db_session.query(Person).filter_by(external_id="EMP002").one()
    d = date.today() - timedelta(days=1)
    while d.weekday() == 6:
        d -= timedelta(days=1)

    def utc(hh, mm):
        local = datetime.combine(d, time(hh, mm), tzinfo=IST)
        return local.astimezone(timezone.utc).replace(tzinfo=None)

    db_session.add_all([
        AttendanceEvent(person_id=emp2.id, camera_label="gate-in-1", direction="entry",
                        source="camera", event_time=utc(9, 0)),
        AttendanceEvent(person_id=emp2.id, camera_label="gate-out-1", direction="exit",
                        source="camera", event_time=utc(14, 0)),
        AttendanceEvent(person_id=emp2.id, camera_label="gate-out-2", direction="exit",
                        source="camera", event_time=utc(17, 0)),
    ])
    db_session.commit()

    # Supervisor sees the anomaly.
    an = client.get("/supervisor/anomalies", headers=sup_headers).json()
    assert any(x["external_id"] == "EMP002" and x["date"] == d.isoformat() for x in an)

    # Fix by adding the missing entry at 14:30 -> valid, anomaly clears.
    r = client.post("/supervisor/overrides", headers=sup_headers, json={
        "external_id": "EMP002", "for_date": d.isoformat(),
        "entry_time": "14:30", "reason": "re-entry missed",
    })
    assert r.status_code == 200
    an2 = client.get("/supervisor/anomalies", headers=sup_headers).json()
    assert not any(x["external_id"] == "EMP002" and x["date"] == d.isoformat() for x in an2)


# ── Editing the disputed crossing on an already-messy day ─────────────────────
def _seed_messy_day(db_session, ext="EMP002"):
    """A day with entry 04:20, exit 07:30, entry 09:45, exit 11:30 for `ext`.
    Returns (date, {label: event_id}). Clean, then we perturb it in tests."""
    from app.db.models import Person
    p = db_session.query(Person).filter_by(external_id=ext).one()
    d = date.today() - timedelta(days=2)
    while d.weekday() == 6:
        d -= timedelta(days=1)

    def utc(hh, mm):
        local = datetime.combine(d, time(hh, mm), tzinfo=IST)
        return local.astimezone(timezone.utc).replace(tzinfo=None)

    evs = [
        AttendanceEvent(person_id=p.id, camera_label="gate-in-1", direction="entry",
                        source="camera", event_time=utc(4, 20)),
        AttendanceEvent(person_id=p.id, camera_label="gate-out-1", direction="exit",
                        source="camera", event_time=utc(7, 30)),
        AttendanceEvent(person_id=p.id, camera_label="gate-in-2", direction="entry",
                        source="camera", event_time=utc(9, 45)),
        AttendanceEvent(person_id=p.id, camera_label="gate-out-2", direction="exit",
                        source="camera", event_time=utc(11, 30)),
    ]
    db_session.add_all(evs)
    db_session.commit()
    return d, evs


def test_edit_disputed_entry_replaces_not_inserts(client, emp2_headers, sup_headers, db_session):
    """The reported bug: disputing entry2 (09:45) and correcting it to 09:30 must
    succeed — it replaces the disputed crossing rather than inserting a new one."""
    d, evs = _seed_messy_day(db_session)
    entry2_id = evs[2].id

    did = client.post("/disputes", headers=emp2_headers, json={
        "for_date": d.isoformat(), "target_kind": "entry",
        "event_id": entry2_id, "message": "I entered at 09:30",
    }).json()["id"]

    r = client.post(f"/supervisor/disputes/{did}/approve", headers=sup_headers,
                    json={"entry_time": "09:30"})
    assert r.status_code == 200, r.text

    # The corrected day: entry 04:20, exit 07:30, entry 09:30, exit 11:30 — valid.
    day = next(x for x in client.get("/supervisor/employee/EMP002/summary"
                                     f"?from_date={d.isoformat()}&to_date={d.isoformat()}",
                                     headers=sup_headers).json() if x["date"] == d.isoformat())
    entries = [e for e in day["events"] if e["direction"] == "entry"]
    # Still exactly two entries (the disputed one was replaced, not duplicated).
    assert len(entries) == 2
    assert day["has_anomaly"] is False


def test_edit_disputed_entry_rejected_when_it_creates_conflict(client, emp2_headers, sup_headers, db_session):
    """Moving entry2 to 07:15 (before the 07:30 exit) DOES conflict — you'd have
    two entries in a row — so it must be rejected."""
    d, evs = _seed_messy_day(db_session)
    entry2_id = evs[2].id

    did = client.post("/disputes", headers=emp2_headers, json={
        "for_date": d.isoformat(), "target_kind": "entry",
        "event_id": entry2_id, "message": "I entered at 07:15",
    }).json()["id"]

    r = client.post(f"/supervisor/disputes/{did}/approve", headers=sup_headers,
                    json={"entry_time": "07:15"})
    assert r.status_code == 400
    assert "entr" in r.json()["detail"].lower()


def test_edit_on_preexisting_anomaly_day_is_allowed(client, emp2_headers, sup_headers, db_session):
    """A day that ALREADY has a camera anomaly (two entries in a row) must still
    allow correcting the disputed crossing, as long as the edit doesn't add a NEW
    conflict."""
    from app.db.models import Person
    p = db_session.query(Person).filter_by(external_id="EMP002").one()
    d = date.today() - timedelta(days=3)
    while d.weekday() == 6:
        d -= timedelta(days=1)

    def utc(hh, mm):
        local = datetime.combine(d, time(hh, mm), tzinfo=IST)
        return local.astimezone(timezone.utc).replace(tzinfo=None)

    # entry 08:46, entry 09:35 (no exit between -> anomaly), exit 12:37.
    evs = [
        AttendanceEvent(person_id=p.id, camera_label="gate-in-1", direction="entry",
                        source="camera", event_time=utc(8, 46)),
        AttendanceEvent(person_id=p.id, camera_label="gate-in-2", direction="entry",
                        source="camera", event_time=utc(9, 35)),
        AttendanceEvent(person_id=p.id, camera_label="gate-out-2", direction="exit",
                        source="camera", event_time=utc(12, 37)),
    ]
    db_session.add_all(evs)
    db_session.commit()

    # Dispute the first entry, correcting 08:46 -> 07:45 (still before 09:35).
    did = client.post("/disputes", headers=emp2_headers, json={
        "for_date": d.isoformat(), "target_kind": "entry",
        "event_id": evs[0].id, "message": "I entered at 07:45",
    }).json()["id"]

    r = client.post(f"/supervisor/disputes/{did}/approve", headers=sup_headers,
                    json={"entry_time": "07:45"})
    # The pre-existing "two entries in a row" anomaly remains, but the edit didn't
    # make it worse — so the correction is accepted.
    assert r.status_code == 200, r.text

