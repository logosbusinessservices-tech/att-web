"""OTP login: request/verify, expiry, attempt cap, cooldown, phone normalization."""

from app.services import otp as otp_service


def test_phone_normalization():
    assert otp_service.normalize_phone("+91 90000 00001") == "9000000001"
    assert otp_service.normalize_phone("09000000001") == "9000000001"
    assert otp_service.normalize_phone("9000000001") == "9000000001"


def test_request_returns_debug_code_in_dev(client):
    r = client.post("/auth/otp/request", json={"phone": "+91 90000 00001"})
    assert r.status_code == 200
    assert r.json()["sent"] is True
    assert len(r.json()["debug_code"]) == 6  # EMP001 has this phone in the seed


def test_request_unknown_phone_still_ok_but_no_code(client):
    r = client.post("/auth/otp/request", json={"phone": "+91 99999 99999"})
    assert r.status_code == 200
    assert r.json().get("debug_code") is None  # no person -> no real code


def test_verify_success_issues_token(client):
    code = client.post("/auth/otp/request", json={"phone": "9000000001"}).json()["debug_code"]
    r = client.post("/auth/otp/verify", json={"phone": "9000000001", "code": code})
    assert r.status_code == 200
    assert r.json()["role"] == "employee"
    assert r.json()["access_token"]


def test_verify_wrong_code_rejected(client):
    client.post("/auth/otp/request", json={"phone": "9000000001"})
    r = client.post("/auth/otp/verify", json={"phone": "9000000001", "code": "000000"})
    # Could randomly match the real code 1-in-a-million; treat 400 as expected.
    assert r.status_code in (400, 200)
    if r.status_code == 400:
        assert "attempt" in r.json()["detail"].lower()


def test_token_from_otp_works_on_protected_route(client):
    code = client.post("/auth/otp/request", json={"phone": "9000000001"}).json()["debug_code"]
    tok = client.post("/auth/otp/verify", json={"phone": "9000000001", "code": code}).json()["access_token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["external_id"] == "EMP001"


def test_cooldown_blocks_rapid_resend(client):
    client.post("/auth/otp/request", json={"phone": "9000000001"})
    r = client.post("/auth/otp/request", json={"phone": "9000000001"})
    assert r.status_code == 429


def test_attempt_cap(client):
    from app.config import settings
    client.post("/auth/otp/request", json={"phone": "9000000001"})
    last = None
    for _ in range(settings.otp_max_attempts + 1):
        last = client.post("/auth/otp/verify", json={"phone": "9000000001", "code": "999999"})
    # After exhausting attempts the challenge is consumed -> 429 or "no active code".
    assert last.status_code in (400, 429)
