"""Edge -> cloud attendance push, with offline queue + retry (the "backup").

Drop this into the camera pipeline (edge box). Instead of writing attendance to
a local DB, call push_event(...). If the internet is down, the event is appended
to a local JSONL queue and retried later, so no attendance is ever lost.

This uses only the standard library (urllib) so the edge box needs no extra deps.

Config via environment on the edge box:
    ATTWEB_API_URL   e.g. https://your-backend.onrender.com
    ATTWEB_EDGE_KEY  must equal the backend's EDGE_API_KEY
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL = os.environ.get("ATTWEB_API_URL", "http://127.0.0.1:8000")
EDGE_KEY = os.environ.get("ATTWEB_EDGE_KEY", "change-me-edge-key")
QUEUE_FILE = Path(os.environ.get("ATTWEB_QUEUE_FILE", "edge_queue/pending.jsonl"))
TIMEOUT_S = 5


def _post_event(event: dict) -> bool:
    """POST one event. Returns True on success, False on any failure."""
    data = json.dumps(event).encode("utf-8")
    req = urllib.request.Request(
        f"{API_URL.rstrip('/')}/events",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "X-Edge-Key": EDGE_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return False


def _enqueue(event: dict) -> None:
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def flush_queue() -> int:
    """Retry all queued events. Returns how many were successfully sent.

    Call this periodically (e.g. every minute) or before pushing a new event.
    """
    if not QUEUE_FILE.exists():
        return 0
    remaining: list[dict] = []
    sent = 0
    for line in QUEUE_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        event = json.loads(line)
        if _post_event(event):
            sent += 1
        else:
            remaining.append(event)
    # Rewrite the queue with only the still-failing events.
    with QUEUE_FILE.open("w", encoding="utf-8") as f:
        for event in remaining:
            f.write(json.dumps(event) + "\n")
    return sent


def push_event(
    external_id: str | None,
    camera_label: str,
    similarity: float | None = None,
    is_visitor: bool = False,
    track_id: int | None = None,
) -> bool:
    """Send one recognition event to the cloud, queuing it if offline.

    Returns True if delivered now, False if it was queued for retry.
    """
    event = {
        "external_id": external_id,
        "is_visitor": is_visitor,
        "similarity": similarity,
        "camera_label": camera_label,
        "track_id": track_id,
        "event_time": datetime.now(timezone.utc).isoformat(),
    }
    flush_queue()  # opportunistically drain backlog first
    if _post_event(event):
        return True
    _enqueue(event)
    return False


if __name__ == "__main__":
    ok = push_event(external_id="EMP001", camera_label="edge-test", similarity=0.87)
    print("delivered" if ok else "queued (offline)")
