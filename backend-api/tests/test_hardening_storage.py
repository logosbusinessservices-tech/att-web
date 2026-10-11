"""Step 2 hardening: OTP switched off, secret guards, photo storage, startup migration."""

import hashlib
import io
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from sqlalchemy import create_engine, inspect, text

from app import storage
from app.config import Settings, assert_production_secrets, settings
from app.db.migrate import run_migrations
from app.db.models import Person
from app.face import model as face_model
from app.services import enrollment as enroll_service


def _jpeg() -> bytes:
    ok, buf = cv2.imencode(".jpg", np.zeros((16, 16, 3), dtype=np.uint8))
    assert ok
    return buf.tobytes()


# ── OTP is off ───────────────────────────────────────────────────────────────
def test_otp_endpoints_look_nonexistent(client, emp_headers):
    assert client.post("/auth/otp/request", json={"phone": "9000000001"}).status_code == 404
    assert client.post("/auth/otp/verify", json={"phone": "9000000001", "code": "123456"}).status_code == 404
    assert client.post("/auth/signup/otp", json={"phone": "9000000099"}).status_code == 404
    assert client.post("/auth/password/otp", headers=emp_headers, json={}).status_code == 404


def test_password_change_ignores_otp_code_when_off(client, emp_headers):
    r = client.post("/auth/password/change", headers=emp_headers,
                    json={"otp_code": "123456", "new_password": "brandnew1"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Provide your current password"
    ok = client.post("/auth/password/change", headers=emp_headers,
                     json={"old_password": "pass123", "new_password": "brandnew1"})
    assert ok.status_code == 200


# ── Placeholder-secret guard ─────────────────────────────────────────────────
PG = "postgresql+psycopg://u:p@host:5432/db"


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_guard_refuses_placeholders_on_postgres():
    with pytest.raises(RuntimeError, match="JWT_SECRET, EDGE_API_KEY"):
        assert_production_secrets(_settings(database_url=PG))
    with pytest.raises(RuntimeError, match="EDGE_API_KEY"):
        assert_production_secrets(_settings(database_url=PG, jwt_secret="x" * 40))


def test_guard_allows_real_secrets_and_sqlite_dev():
    assert_production_secrets(_settings(database_url=PG, jwt_secret="x" * 40, edge_api_key="y" * 40))
    assert_production_secrets(_settings(database_url="sqlite:///./dev.db"))


# ── Storage: local mode ──────────────────────────────────────────────────────
def test_local_storage_round_trip():
    ref = storage.save(storage.AVATARS, "1_abc.jpg", b"img")
    assert storage.load(ref) == b"img"
    storage.delete(ref)
    assert storage.load(ref) is None
    storage.delete(ref)  # deleting twice is fine


# ── Storage: Azure mode (fake Blob client) ───────────────────────────────────
class _FakeBlobs:
    def __init__(self):
        self.files: dict[tuple[str, str], bytes] = {}

    def client(self, container, name):
        from azure.core.exceptions import ResourceNotFoundError
        files = self.files

        class _Client:
            def upload_blob(self, data, overwrite, content_settings):
                files[(container, name)] = data

            def download_blob(self):
                if (container, name) not in files:
                    raise ResourceNotFoundError("missing")
                return SimpleNamespace(readall=lambda: files[(container, name)])

            def delete_blob(self):
                if files.pop((container, name), None) is None:
                    raise ResourceNotFoundError("missing")

        return _Client()


@pytest.fixture()
def fake_blob(monkeypatch):
    blobs = _FakeBlobs()
    monkeypatch.setattr(settings, "azure_storage_connection_string", "fake")
    monkeypatch.setattr(storage, "_blob_client", blobs.client)
    return blobs


def test_blob_storage_round_trip(fake_blob):
    ref = storage.save(storage.FIELD_SELFIES, "EMP001_x.jpg", b"selfie")
    assert ref == "blob:field-selfies/EMP001_x.jpg"
    assert storage.load(ref) == b"selfie"
    storage.delete(ref)
    assert storage.load(ref) is None
    storage.delete(ref)
    assert storage.load("./data/avatars/old.jpg") is None  # pre-Azure link -> no photo


def test_avatar_lives_in_blob_and_old_one_is_removed(client, emp_headers, db_session, fake_blob):
    files = [("photo", ("me.jpg", io.BytesIO(_jpeg()), "image/jpeg"))]
    assert client.post("/employees/avatar", headers=emp_headers, files=files).status_code == 200
    first = db_session.query(Person).filter_by(external_id="EMP001").one().avatar_path
    assert first.startswith("blob:avatars/")

    img = client.get("/employees/EMP001/avatar", headers=emp_headers)
    assert img.status_code == 200 and img.content == _jpeg()

    files = [("photo", ("me2.jpg", io.BytesIO(_jpeg()), "image/jpeg"))]
    client.post("/employees/avatar", headers=emp_headers, files=files)
    db_session.expire_all()
    second = db_session.query(Person).filter_by(external_id="EMP001").one().avatar_path
    assert second != first
    assert storage.load(first) is None


# ── Onboarding photos are archived ───────────────────────────────────────────
def test_enrollment_archives_original_photos(client, sup_headers, db_session, monkeypatch, tmp_path):
    vec = np.ones(512, dtype=np.float32) / np.sqrt(512)
    monkeypatch.setattr(enroll_service, "embed_largest_face", lambda img: (vec, 0.9))
    photos = [("photos", (f"{i}.jpg", io.BytesIO(_jpeg()), "image/jpeg")) for i in range(2)]
    r = client.post("/supervisor/employees/EMP001/enroll", headers=sup_headers, files=photos)
    assert r.status_code == 200, r.text

    person_id = db_session.query(Person).filter_by(external_id="EMP001").one().id
    saved = list((tmp_path / "employee_photos" / str(person_id)).glob("*.jpg"))
    assert len(saved) == 2
    assert all(f.read_bytes() == _jpeg() for f in saved)


# ── Model fingerprint ────────────────────────────────────────────────────────
def test_model_fingerprint_hashes_recognition_file(monkeypatch, tmp_path):
    onnx = tmp_path / "w600k_mbf.onnx"
    onnx.write_bytes(b"model-weights")
    fake_app = SimpleNamespace(models={"recognition": SimpleNamespace(model_file=str(onnx))})
    monkeypatch.setattr(face_model, "_fingerprint", None)
    monkeypatch.setattr(face_model, "get_face_app", lambda: fake_app)
    assert face_model.model_fingerprint() == hashlib.sha256(b"model-weights").hexdigest()


# ── Startup migration ────────────────────────────────────────────────────────
def _old_schema_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE persons (id INTEGER PRIMARY KEY, avatar_path VARCHAR)"))
        conn.execute(text("CREATE TABLE attendance_events (id INTEGER PRIMARY KEY, selfie_path VARCHAR)"))
        conn.execute(text("INSERT INTO persons VALUES (1, './data/avatars/1.jpg'), (2, 'blob:avatars/2.jpg')"))
        conn.execute(text("INSERT INTO attendance_events VALUES (1, './data/field_selfies/a.jpg')"))
    return engine


def test_migration_adds_event_uuid_and_is_repeatable(tmp_path):
    engine = _old_schema_engine(tmp_path)
    run_migrations(engine)
    run_migrations(engine)
    insp = inspect(engine)
    assert "event_uuid" in {c["name"] for c in insp.get_columns("attendance_events")}
    assert any(i["name"] == "uq_attendance_events_event_uuid" and i["unique"]
               for i in insp.get_indexes("attendance_events"))
    with engine.connect() as conn:
        # Without Azure storage configured, local photo links are left alone.
        assert conn.execute(text("SELECT avatar_path FROM persons WHERE id = 1")).scalar() is not None


def test_migration_clears_dead_photo_links_when_on_blob(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "azure_storage_connection_string", "fake")
    engine = _old_schema_engine(tmp_path)
    run_migrations(engine)
    with engine.connect() as conn:
        avatars = dict(conn.execute(text("SELECT id, avatar_path FROM persons")).all())
        selfie = conn.execute(text("SELECT selfie_path FROM attendance_events")).scalar()
    assert avatars == {1: None, 2: "blob:avatars/2.jpg"}
    assert selfie is None
