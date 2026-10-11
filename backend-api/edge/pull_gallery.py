"""Edge <- cloud gallery sync (the counterpart to push_events.py).

Run this on the edge box periodically (e.g. every minute). It asks for the full
snapshot of everyone the gates should recognize and REPLACES the local gallery
with it, so approvals, renames and deactivations all take effect. It sends back
the version it already holds, so an unchanged gallery costs one tiny reply.

Local file (next to this script by default):
    gallery/embeddings.json   {version, model_name, model_sha256,
                               people: {external_id: {name, num_photos, embedding_b64, updated_at}}}

Config via environment on the edge box:
    ATTWEB_API_URL   the backend's https address
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
TIMEOUT_S = 10


def _load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def sync_gallery() -> int | None:
    """Fetch the snapshot and replace the local gallery if it changed.

    Returns the number of people now in the gallery, or None if nothing changed
    or the backend was unreachable (the last good gallery is kept).
    """
    GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    held = _load_json(GALLERY_FILE, {})

    url = f"{API_URL.rstrip('/')}/edge/gallery"
    if held.get("version"):
        url += "?" + urllib.parse.urlencode({"version": held["version"]})
    req = urllib.request.Request(url, headers={"X-Edge-Key": EDGE_KEY})

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            snap = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        print(f"gallery sync failed: {exc}")
        return None

    if snap.get("unchanged"):
        return None

    gallery = {
        "version": snap["version"],
        "model_name": snap["model_name"],
        "model_sha256": snap.get("model_sha256"),
        "people": {
            it["external_id"]: {
                "name": it["display_name"],
                "num_photos": it["num_photos"],
                "embedding_b64": it["embedding_b64"],
                "updated_at": it["updated_at"],
            }
            for it in snap["items"]
        },
    }
    tmp = GALLERY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(gallery, indent=2), encoding="utf-8")
    tmp.replace(GALLERY_FILE)  # atomic: readers never see a half-written file
    return len(gallery["people"])


def load_embeddings() -> dict:
    """Helper the pipeline can import: {external_id: numpy-ready float32 list}.

    Decodes the base64 blobs. (Kept dependency-free; convert to numpy in the
    pipeline where numpy is already available.)
    """
    import struct

    people = _load_json(GALLERY_FILE, {}).get("people", {})
    out: dict[str, list[float]] = {}
    for ext, rec in people.items():
        raw = base64.b64decode(rec["embedding_b64"])
        out[ext] = list(struct.unpack(f"{len(raw) // 4}f", raw))
    return out


if __name__ == "__main__":
    n = sync_gallery()
    total = len(_load_json(GALLERY_FILE, {}).get("people", {}))
    print("gallery unchanged" if n is None else f"gallery replaced: {n} people")
    print(f"gallery has {total} people")
