"""Phase 2: disputes, append-only overrides, approvals, dept-scoped authority."""

from datetime import date, timedelta


# ── Employee raises disputes ─────────────────────────────────────────────────
def test_create_dispute_ok(client, emp_headers, seed_dates):
    r = client.post("/disputes", headers=emp_headers, json={"for_date": seed_dates["absent"],
                                                            "message": "camera missed me"})
    assert r.status_code == 200
    assert r.json()["status"] == "open"


def test_duplicate_open_dispute_blocked(client, emp_headers, seed_dates):
    payload = {"for_date": seed_dates["absent"], "message": "x"}
    assert client.post("/disputes", headers=emp_headers, json=payload).status_code == 200
    r2 = client.post("/disputes", headers=emp_headers, json=payload)
    assert r2.status_code == 400
    assert "open dispute" in r2.json()["detail"].lower()


def test_future_date_dispute_blocked(client, emp_headers):
    future = (date.today() + timedelta(days=2)).isoformat()
    r = client.post("/disputes", headers=emp_headers, json={"for_date": future})
    assert r.status_code == 400


def test_dispute_older_than_30_days_blocked(client, emp_headers):
    old = (date.today() - timedelta(days=45)).isoformat()
    r = client.post("/disputes", headers=emp_headers, json={"for_date": old})
    assert r.status_code == 400
    assert "30" in r.json()["detail"]


def test_my_disputes_lists_own(client, emp_headers, seed_dates):
    client.post("/disputes", headers=emp_headers, json={"for_date": seed_dates["absent"]})
    r = client.get("/disputes/me", headers=emp_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_edit_open_dispute(client, emp_headers, seed_dates):
    did = client.post("/disputes", headers=emp_headers,
                      json={"for_date": seed_dates["absent"], "message": "first"}).json()["id"]
    r = client.patch(f"/disputes/{did}", headers=emp_headers, json={"message": "corrected note"})
    assert r.status_code == 200
    assert r.json()["message"] == "corrected note"


def test_cannot_edit_others_dispute(client, emp_headers, emp2_headers, seed_dates):
    did = client.post("/disputes", headers=emp_headers,
                      json={"for_date": seed_dates["absent"], "message": "x"}).json()["id"]
    r = client.patch(f"/disputes/{did}", headers=emp2_headers, json={"message": "hax"})
    assert r.status_code == 404


def test_cannot_edit_resolved_dispute(client, emp_headers, sup_headers, seed_dates):
    did = client.post("/disputes", headers=emp_headers,
                      json={"for_date": seed_dates["absent"], "message": "x"}).json()["id"]
    client.post(f"/supervisor/disputes/{did}/approve", headers=sup_headers,
                json={"new_status": "present", "reason": "ok"})
    r = client.patch(f"/disputes/{did}", headers=emp_headers, json={"message": "late edit"})
    assert r.status_code == 400


# ── Supervisor queue + approval flow ─────────────────────────────────────────
def test_supervisor_sees_dept_disputes(client, emp_headers, sup_headers, seed_dates):
    client.post("/disputes", headers=emp_headers, json={"for_date": seed_dates["absent"]})
    r = client.get("/supervisor/disputes?status=open", headers=sup_headers)
    assert r.status_code == 200
    assert any(d["external_id"] == "EMP001" for d in r.json())


def test_approve_creates_override_and_fixes_status(client, emp_headers, sup_headers, seed_dates):
    # absent day -> dispute -> approve with injected times -> present + hours
    client.post("/disputes", headers=emp_headers, json={"for_date": seed_dates["absent"]})
    did = client.get("/supervisor/disputes", headers=sup_headers).json()[0]["id"]
    r = client.post(f"/supervisor/disputes/{did}/approve", headers=sup_headers,
                    json={"new_status": "present", "entry_time": "09:15",
                          "exit_time": "18:00", "reason": "verified on exit log"})
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"

    # Employee's view now shows the corrected day.
    summ = client.get("/attendance/summary", headers=emp_headers).json()
    day = next(d for d in summ if d["date"] == seed_dates["absent"])
    assert day["status"] == "present"
    assert day["adjusted"] is True
    assert day["hours_in_office"] == 8.75


def test_approve_requires_some_change(client, emp_headers, sup_headers, seed_dates):
    client.post("/disputes", headers=emp_headers, json={"for_date": seed_dates["absent"]})
    did = client.get("/supervisor/disputes", headers=sup_headers).json()[0]["id"]
    r = client.post(f"/supervisor/disputes/{did}/approve", headers=sup_headers, json={})
    assert r.status_code == 400


def test_reject_dispute(client, emp_headers, sup_headers, seed_dates):
    client.post("/disputes", headers=emp_headers, json={"for_date": seed_dates["late"]})
    did = client.get("/supervisor/disputes", headers=sup_headers).json()[0]["id"]
    r = client.post(f"/supervisor/disputes/{did}/reject", headers=sup_headers,
                    json={"resolution_note": "no official duty record"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    # And the underlying attendance is unchanged.
    summ = client.get("/attendance/summary", headers=emp_headers).json()
    day = next(d for d in summ if d["date"] == seed_dates["late"])
    assert day["status"] == "present"


# ── Direct override (no dispute) ─────────────────────────────────────────────
def test_direct_override_absent_to_present(client, sup_headers, emp_headers, seed_dates):
    r = client.post("/supervisor/overrides", headers=sup_headers,
                    json={"external_id": "EMP001", "for_date": seed_dates["absent"],
                          "new_status": "present", "reason": "offsite duty"})
    assert r.status_code == 200
    body = r.json()
    assert body["original_status"] == "absent"
    assert body["new_status"] == "present"

    summ = client.get("/attendance/summary", headers=emp_headers).json()
    day = next(d for d in summ if d["date"] == seed_dates["absent"])
    assert day["status"] == "present"
    assert day["adjusted"] is True


def test_latest_override_wins(client, sup_headers, emp_headers, seed_dates):
    d = seed_dates["absent"]
    client.post("/supervisor/overrides", headers=sup_headers,
                json={"external_id": "EMP001", "for_date": d, "new_status": "present"})
    client.post("/supervisor/overrides", headers=sup_headers,
                json={"external_id": "EMP001", "for_date": d, "new_status": "absent"})
    summ = client.get("/attendance/summary", headers=emp_headers).json()
    day = next(x for x in summ if x["date"] == d)
    assert day["status"] == "absent"  # most recent override wins


# ── Dept-scoped authority ────────────────────────────────────────────────────
def test_supervisor_cannot_override_other_department(client, sup_headers):
    # EMP003 is in "Signals", supervisor is in "Operations".
    r = client.post("/supervisor/overrides", headers=sup_headers,
                    json={"external_id": "EMP003", "for_date": date.today().isoformat(),
                          "new_status": "present"})
    assert r.status_code == 403


def test_supervisor_queue_excludes_other_department(client, emp3_headers, sup_headers):
    # EMP003 raises a dispute; Operations supervisor should NOT see it.
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    client.post("/disputes", headers=emp3_headers, json={"for_date": yesterday})
    q = client.get("/supervisor/disputes?status=open", headers=sup_headers).json()
    assert all(d["external_id"] != "EMP003" for d in q)


def test_employee_cannot_access_override_endpoint(client, emp_headers, seed_dates):
    r = client.post("/supervisor/overrides", headers=emp_headers,
                    json={"external_id": "EMP001", "for_date": seed_dates["absent"],
                          "new_status": "present"})
    assert r.status_code == 403


# ── Append-only guarantee ────────────────────────────────────────────────────
def test_raw_events_untouched_after_override(client, sup_headers, emp_headers, seed_dates):
    before = client.get(f"/attendance/day/{seed_dates['present']}", headers=emp_headers).json()
    client.post("/supervisor/overrides", headers=sup_headers,
                json={"external_id": "EMP001", "for_date": seed_dates["present"],
                      "new_status": "absent", "reason": "test"})
    after = client.get(f"/attendance/day/{seed_dates['present']}", headers=emp_headers).json()
    # Original two camera crossings are still present (a manual row may be added
    # only when times are supplied; here none were, so count is unchanged).
    camera = [e for e in after if e["source"] == "camera"]
    assert len(camera) == len(before)
