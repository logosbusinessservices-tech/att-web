"""Edge <- cloud gallery sync (the counterpart to push_events.py).

Run this on the edge box periodically (e.g. every minute via cron/loop). It pulls
newly enrolled/updated face templates and writes them to a local JSON file the
camera pipeline loads for recognition. Incremental: it remembers the last sync
time so it only fetches deltas.

Local files (next to this script by default):
    gallery/embeddings.json   { external_id: {name, num_photos, embedding_b64, updated_at} }
    gallery/last_sync.txt     ISO timestamp of the newest template seen

Config via environment on the edge box:
    ATTWEB_API_URL   e.g. https://your-backend.onrender.com
    ATTWEB_EDGE_KEY  must equal the backend's EDGE_API_KEY

Uses only the standard library (urllib) so the edge box needs no extra deps.
"""

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_URL = os.environ.get("ATTWEB_API_URL", "http://127.0.0.1:8000")
EDGE_KEY = os.environ.get("ATTWEB_EDGE_KEY", "change-me-edge-key")
GALLERY_DIR = Path(os.environ.get("ATTWEB_GALLERY_DIR", "gallery"))
GALLERY_FILE = GALLERY_DIR / "embeddings.json"
LAST_SYNC_FILE = GALLERY_DIR / "last_sync.txt"
TIMEOUT_S = 10


def _load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def sync_gallery() -> int:
    """Pull deltas and merge into the local gallery. Returns count synced."""
    GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    since = LAST_SYNC_FILE.read_text(encoding="utf-8").strip() if LAST_SYNC_FILE.exists() else ""

    url = f"{API_URL.rstrip('/')}/edge/gallery"
    if since:
        url += "?" + urllib.parse.urlencode({"since": since})
    req = urllib.request.Request(url, headers={"X-Edge-Key": EDGE_KEY})

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            items = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        print(f"gallery sync failed: {exc}")
        return 0

    if not items:
        return 0

    gallery = _load_json(GALLERY_FILE, {})
    newest = since
    for it in items:
        gallery[it["external_id"]] = {
            "name": it["display_name"],
            "num_photos": it["num_photos"],
            "embedding_b64": it["embedding_b64"],
            "updated_at": it["updated_at"],
        }
        if not newest or it["updated_at"] > newest:
            newest = it["updated_at"]

    GALLERY_FILE.write_text(json.dumps(gallery, indent=2), encoding="utf-8")
    if newest:
        LAST_SYNC_FILE.write_text(newest, encoding="utf-8")
    return len(items)


def load_embeddings() -> dict:
    """Helper the pipeline can import: {external_id: numpy-ready float32 list}.

    Decodes the base64 blobs. (Kept dependency-free; convert to numpy in the
    pipeline where numpy is already available.)
    """
    import struct

    gallery = _load_json(GALLERY_FILE, {})
    out: dict[str, list[float]] = {}
    for ext, rec in gallery.items():
        raw = base64.b64decode(rec["embedding_b64"])
        out[ext] = list(struct.unpack(f"{len(raw) // 4}f", raw))
    return out


if __name__ == "__main__":
    n = sync_gallery()
    print(f"synced {n} template(s); gallery has {len(_load_json(GALLERY_FILE, {}))} total")
