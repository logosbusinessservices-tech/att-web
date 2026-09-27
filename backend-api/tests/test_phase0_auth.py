"""Phase 0: foundations — health, auth (JWT), role guards, profile enrichment."""


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_success_returns_token(client):
    r = client.post("/auth/login", data={"username": "EMP001", "password": "pass123"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "employee"
    assert body["display_name"] == "Test Employee"
    assert body["access_token"]


def test_login_wrong_password_rejected(client):
    r = client.post("/auth/login", data={"username": "EMP001", "password": "nope"})
    assert r.status_code == 401


def test_login_unknown_user_rejected(client):
    r = client.post("/auth/login", data={"username": "GHOST", "password": "pass123"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_garbage_token(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_me_resolves_names_not_ids(client, emp_headers):
    r = client.get("/auth/me", headers=emp_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["external_id"] == "EMP001"
    # Human-friendly resolved fields, not raw ids.
    assert body["department_name"] == "Operations"
    assert body["home_station_name"] == "Central Station"
    assert body["blood_group"] == "O+"
    assert body["email"] == "test.employee@rail.gov.in"


def test_employee_profile_endpoint(client, emp_headers):
    r = client.get("/employees/profile", headers=emp_headers)
    assert r.status_code == 200
    assert r.json()["department_name"] == "Operations"


def test_supervisor_ping_allows_supervisor(client, sup_headers):
    r = client.get("/supervisor/ping", headers=sup_headers)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_supervisor_ping_blocks_employee(client, emp_headers):
    r = client.get("/supervisor/ping", headers=emp_headers)
    assert r.status_code == 403
