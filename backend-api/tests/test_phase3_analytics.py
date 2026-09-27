"""Supervisor analytics endpoints (dashboards)."""

from app.db.models import Department


def _ops_id(db):
    return db.query(Department).filter_by(name="Operations").one().id


def test_analytics_requires_supervisor(client, emp_headers):
    assert client.get("/supervisor/analytics/summary", headers=emp_headers).status_code == 403


def test_analytics_requires_auth(client):
    assert client.get("/supervisor/analytics/summary").status_code == 401


def test_summary_kpis(client, sup_headers):
    r = client.get("/supervisor/analytics/summary", headers=sup_headers)
    assert r.status_code == 200
    body = r.json()
    # EMP001 has present days seeded; scoped to Operations (EMP001, EMP002).
    assert body["present"] >= 1
    assert body["active_employees"] == 2
    assert 0 <= body["attendance_pct"] <= 100
    assert "pending_field_approvals" in body


def test_summary_department_filter(client, sup_headers, db_session):
    r = client.get(f"/supervisor/analytics/summary?department_id={_ops_id(db_session)}", headers=sup_headers)
    assert r.status_code == 200
    assert r.json()["active_employees"] == 2  # EMP001, EMP002 in Operations


def test_trend_points(client, sup_headers):
    r = client.get("/supervisor/analytics/trend?granularity=day", headers=sup_headers)
    assert r.status_code == 200
    pts = r.json()
    assert len(pts) > 0
    p = pts[0]
    assert {"period", "present", "absent", "hours", "attendance_pct"} <= set(p)


def test_trend_month_granularity(client, sup_headers):
    r = client.get("/supervisor/analytics/trend?granularity=month", headers=sup_headers)
    assert r.status_code == 200
    # Buckets look like YYYY-MM.
    assert all(len(p["period"]) == 7 and p["period"][4] == "-" for p in r.json())


def test_by_department(client, sup_headers):
    # A supervisor only sees their own department's row.
    r = client.get("/supervisor/analytics/by-department", headers=sup_headers)
    assert r.status_code == 200
    names = {d["name"] for d in r.json()}
    assert names == {"Operations"}


def test_source_split_counts_camera(client, sup_headers):
    r = client.get("/supervisor/analytics/source-split", headers=sup_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["camera"] >= 4  # EMP001 has 4 seeded camera crossings
    assert set(body) == {"camera", "field", "manual"}


def test_lowest_attendance_ranked(client, sup_headers):
    r = client.get("/supervisor/analytics/lowest-attendance?limit=5", headers=sup_headers)
    assert r.status_code == 200
    rows = r.json()
    # Sorted ascending by attendance %.
    pcts = [x["attendance_pct"] for x in rows]
    assert pcts == sorted(pcts)


# ── Staff-type filter ────────────────────────────────────────────────────────
def test_types_office_default_employees(client, sup_headers):
    # Scoped to Operations: office == EMP001, EMP002.
    r = client.get("/supervisor/analytics/summary?types=office", headers=sup_headers)
    assert r.json()["active_employees"] == 2


def test_types_supervisor_only(client, sup_headers):
    r = client.get("/supervisor/analytics/summary?types=supervisor", headers=sup_headers)
    assert r.json()["active_employees"] == 1  # SUP001 (own department)


def test_types_field_only(client, sup_headers, db_session):
    from app.db.models import Person
    p = db_session.query(Person).filter_by(external_id="EMP001").one()
    p.field_scan_enabled = True
    db_session.commit()
    r = client.get("/supervisor/analytics/summary?types=field", headers=sup_headers)
    assert r.json()["active_employees"] == 1  # only EMP001 now


def test_types_multiselect_union(client, sup_headers, db_session):
    from app.db.models import Person
    p = db_session.query(Person).filter_by(external_id="EMP001").one()
    p.field_scan_enabled = True
    db_session.commit()
    # field (EMP001) + supervisor (SUP001) in Operations = 2.
    r = client.get("/supervisor/analytics/summary?types=field,supervisor", headers=sup_headers)
    assert r.json()["active_employees"] == 2


def test_overview_types_filter(client, sup_headers):
    r = client.get("/supervisor/attendance/overview?types=supervisor", headers=sup_headers)
    assert r.status_code == 200
    assert all(row["external_id"].startswith("SUP") for row in r.json())
