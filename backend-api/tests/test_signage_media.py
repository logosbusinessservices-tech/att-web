"""Tests for the signage media (image/video slides) feature."""

import io
import pytest

from app.auth.security import hash_password
from app.db.models import Person


@pytest.fixture()
def ea2_headers(client, db_session):
    """A second assistant (EA002) who is NOT the super admin."""
    pw = hash_password("EA002")
    ea2 = Person(
        external_id="EA002", display_name="Other Assistant", role="assistant",
        password_hash=pw,
    )
    db_session.add(ea2)
    db_session.commit()
    r = client.post("/auth/login", data={"username": "EA002", "password": "EA002"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# A minimal valid JPEG (smallest possible).
TINY_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n"
    b"\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d"
    b"\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
    b"\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04"
    b"\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00T\xdb\x9e\xa3\xa0\xa3\xff\xd9"
)


class TestSuperAdminGating:
    """Only EA001 can access signage media endpoints."""

    def test_non_ea_cannot_list(self, client, sup_headers):
        r = client.get("/assistant/signage-media", headers=sup_headers)
        assert r.status_code == 403

    def test_ea002_cannot_list(self, client, ea2_headers):
        r = client.get("/assistant/signage-media", headers=ea2_headers)
        assert r.status_code == 403

    def test_ea001_can_list(self, client, ea_headers):
        r = client.get("/assistant/signage-media", headers=ea_headers)
        assert r.status_code == 200
        assert r.json() == []

    def test_ea002_cannot_upload(self, client, ea2_headers):
        r = client.post(
            "/assistant/signage-media", headers=ea2_headers,
            files={"file": ("test.jpg", io.BytesIO(TINY_JPEG), "image/jpeg")},
        )
        assert r.status_code == 403


class TestUpload:
    def test_upload_image(self, client, ea_headers):
        r = client.post(
            "/assistant/signage-media", headers=ea_headers,
            files={"file": ("photo.jpg", io.BytesIO(TINY_JPEG), "image/jpeg")},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["media_type"] == "image"
        assert body["original_filename"] == "photo.jpg"
        assert body["content_type"] == "image/jpeg"
        assert body["position"] == 0

    def test_upload_png(self, client, ea_headers):
        # PNG magic bytes (minimal valid)
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        r = client.post(
            "/assistant/signage-media", headers=ea_headers,
            files={"file": ("img.png", io.BytesIO(png), "image/png")},
        )
        assert r.status_code == 201
        assert r.json()["content_type"] == "image/png"

    def test_upload_mp4(self, client, ea_headers):
        mp4 = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 100
        r = client.post(
            "/assistant/signage-media", headers=ea_headers,
            files={"file": ("clip.mp4", io.BytesIO(mp4), "video/mp4")},
        )
        assert r.status_code == 201
        assert r.json()["media_type"] == "video"

    def test_reject_unsupported_type(self, client, ea_headers):
        r = client.post(
            "/assistant/signage-media", headers=ea_headers,
            files={"file": ("doc.pdf", io.BytesIO(b"fake"), "application/pdf")},
        )
        assert r.status_code == 422

    def test_reject_empty_file(self, client, ea_headers):
        r = client.post(
            "/assistant/signage-media", headers=ea_headers,
            files={"file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")},
        )
        assert r.status_code == 422

    def test_limit_enforced(self, client, ea_headers):
        for i in range(8):
            r = client.post(
                "/assistant/signage-media", headers=ea_headers,
                files={"file": (f"img{i}.jpg", io.BytesIO(TINY_JPEG), "image/jpeg")},
            )
            assert r.status_code == 201, f"Upload {i} failed: {r.text}"
        # 9th should fail.
        r = client.post(
            "/assistant/signage-media", headers=ea_headers,
            files={"file": ("img9.jpg", io.BytesIO(TINY_JPEG), "image/jpeg")},
        )
        assert r.status_code == 409


class TestRemoveAndReorder:
    def _upload(self, client, ea_headers, name="test.jpg"):
        r = client.post(
            "/assistant/signage-media", headers=ea_headers,
            files={"file": (name, io.BytesIO(TINY_JPEG), "image/jpeg")},
        )
        assert r.status_code == 201
        return r.json()

    def test_remove(self, client, ea_headers):
        item = self._upload(client, ea_headers)
        r = client.delete(f"/assistant/signage-media/{item['id']}", headers=ea_headers)
        assert r.status_code == 204
        # Should be gone from list.
        items = client.get("/assistant/signage-media", headers=ea_headers).json()
        assert len(items) == 0

    def test_remove_nonexistent(self, client, ea_headers):
        r = client.delete("/assistant/signage-media/99999", headers=ea_headers)
        assert r.status_code == 404

    def test_reorder(self, client, ea_headers):
        a = self._upload(client, ea_headers, "a.jpg")
        b = self._upload(client, ea_headers, "b.jpg")
        c = self._upload(client, ea_headers, "c.jpg")
        # Reverse the order.
        r = client.put(
            "/assistant/signage-media/order", headers=ea_headers,
            json={"ids": [c["id"], b["id"], a["id"]]},
        )
        assert r.status_code == 200
        items = r.json()
        assert [i["id"] for i in items] == [c["id"], b["id"], a["id"]]

    def test_reorder_stale_ids(self, client, ea_headers):
        a = self._upload(client, ea_headers, "a.jpg")
        r = client.put(
            "/assistant/signage-media/order", headers=ea_headers,
            json={"ids": [a["id"], 99999]},
        )
        assert r.status_code == 409


class TestPreview:
    def test_preview(self, client, ea_headers):
        r = client.post(
            "/assistant/signage-media", headers=ea_headers,
            files={"file": ("photo.jpg", io.BytesIO(TINY_JPEG), "image/jpeg")},
        )
        item = r.json()
        r = client.get(f"/assistant/signage-media/{item['id']}/preview", headers=ea_headers)
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"


class TestEdgeEndpoint:
    def test_edge_signage_media_empty(self, client):
        r = client.get("/edge/signage-media", headers={"X-Edge-Key": "change-me-edge-key"})
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert "version" in body

    def test_edge_signage_media_with_items(self, client, ea_headers):
        client.post(
            "/assistant/signage-media", headers=ea_headers,
            files={"file": ("photo.jpg", io.BytesIO(TINY_JPEG), "image/jpeg")},
        )
        r = client.get("/edge/signage-media", headers={"X-Edge-Key": "change-me-edge-key"})
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["media_type"] == "image"

    def test_edge_download_file(self, client, ea_headers):
        up = client.post(
            "/assistant/signage-media", headers=ea_headers,
            files={"file": ("photo.jpg", io.BytesIO(TINY_JPEG), "image/jpeg")},
        ).json()
        r = client.get(
            f"/edge/signage-media/{up['id']}/file",
            headers={"X-Edge-Key": "change-me-edge-key"},
        )
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"
        assert len(r.content) > 0
