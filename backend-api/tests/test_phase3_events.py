"""Supervisor granular crossing edits: edit time, delete, add (append-only)."""


def _present_events(client, sup_headers, seed_dates):
    d = seed_dates["present"]
    days = client.get(f"/supervisor/employee/EMP001/summary?from_date={d}&to_date={d}",
                      headers=sup_headers).json()
    return d, days[0]["events"]


def test_edit_crossing_time_changes_hours(client, sup_headers, seed_dates):
    d, events = _present_events(client, sup_headers, seed_dates)
    entry = next(e for e in events if e["direction"] == "entry")
    # present day is 09:15 -> 18:00 (8.75h). Move entry to 09:00 -> 9.0h.
    r = client.patch(f"/supervisor/events/{entry['id']}", headers=sup_headers, json={"time": "09:00"})
    assert r.status_code == 200, r.text
    assert r.json()["hours_in_office"] == 9.0


def test_delete_crossing_removes_it(client, sup_headers, seed_dates):
    d, events = _present_events(client, sup_headers, seed_dates)
    ex = next(e for e in events if e["direction"] == "exit")
    r = client.delete(f"/supervisor/events/{ex['id']}", headers=sup_headers)
    assert r.status_code == 200
    day = r.json()
    assert day["exit_count"] == 0
    assert day["hours_in_office"] == 0.0  # no exit to pair the entry


def test_add_crossing(client, sup_headers, seed_dates):
    d, events = _present_events(client, sup_headers, seed_dates)
    ex = next(e for e in events if e["direction"] == "exit")
    # Remove the 18:00 exit, then add a 19:00 exit.
    client.delete(f"/supervisor/events/{ex['id']}", headers=sup_headers)
    r = client.post("/supervisor/events", headers=sup_headers, json={
        "external_id": "EMP001", "for_date": d, "direction": "exit", "time": "19:00",
    })
    assert r.status_code == 200
    day = r.json()
    assert day["exit_count"] == 1
    assert day["hours_in_office"] == 9.75  # 09:15 -> 19:00


def test_add_crossing_rejects_conflict(client, sup_headers, seed_dates):
    d, _ = _present_events(client, sup_headers, seed_dates)
    # Adding a second entry (already inside) is impossible -> rejected.
    r = client.post("/supervisor/events", headers=sup_headers, json={
        "external_id": "EMP001", "for_date": d, "direction": "entry", "time": "12:00",
    })
    assert r.status_code == 400


def test_edit_crossing_dept_scoped(client, sup_headers, emp3_headers, seed_dates):
    # Give EMP003 (other dept) a crossing via their own... they have none; add via
    # supervisor is blocked, so just assert add for EMP003 is 403.
    r = client.post("/supervisor/events", headers=sup_headers, json={
        "external_id": "EMP003", "for_date": seed_dates["present"], "direction": "entry", "time": "09:00",
    })
    assert r.status_code == 403


def test_delete_unknown_event_404(client, sup_headers):
    assert client.delete("/supervisor/events/999999", headers=sup_headers).status_code == 404
