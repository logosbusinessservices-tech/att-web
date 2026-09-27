"""Field attendance: verify a live selfie (1:1) + GPS geofence, then log an event.

Flow (Option B — capture offline, verify on server/sync):
  1. Quality-gate + embed the selfie, verify 1:1 against the person's OWN template.
  2. Find the nearest station; check the GPS point against its radius (per-station
     radius_m, else the default). Poor GPS accuracy is treated as "uncertain".
  3. Inside geofence with good accuracy  -> event is 'approved'.
     Outside / no GPS / coarse accuracy  -> event is 'pending' (supervisor decides).
  4. Store the selfie for audit (purged after retention days) and write the event.

The identity match always uses the server's buffalo_s model, so a field selfie is
directly comparable with the camera pipeline's embeddings.
"""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AttendanceEvent, FaceEmbedding, Person, Station
from app.face.model import decode_image_bytes, embed_largest_face
from app.face.verify import verify
from app.geo.geofence import inside_geofence, nearest_station
from app.services import attendance_service as svc


class FieldError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _enrolled_blob(db: Session, person_id: int) -> bytes | None:
    row = db.execute(
        select(FaceEmbedding).where(FaceEmbedding.person_id == person_id)
    ).scalars().first()
    return row.embedding if row else None


def _save_selfie(person_external_id: str, image: bytes) -> str:
    """Persist the audit selfie and return its stored path (purged after N days)."""
    base = Path(settings.field_selfie_dir)
    base.mkdir(parents=True, exist_ok=True)
    fname = f"{person_external_id}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:8]}.jpg"
    path = base / fname
    path.write_bytes(image)
    return str(path)


def open_entry_today(db: Session, person: Person) -> bool:
    """True if the person currently has an unclosed entry today (checked in)."""
    today = svc.today_local()
    events = db.execute(
        select(AttendanceEvent).where(AttendanceEvent.person_id == person.id)
    ).scalars().all()
    day = [e for e in svc._effective_events(events)
           if svc._to_local(e.event_time).date() == today]
    day.sort(key=lambda e: e.event_time)
    inside = False
    for e in day:
        if e.direction == "entry":
            inside = True
        elif e.direction == "exit":
            inside = False
    return inside


def next_direction(db: Session, person: Person) -> str:
    """Server-suggested next action: 'exit' if checked in, else 'entry'."""
    return "exit" if open_entry_today(db, person) else "entry"


def check_in(
    db: Session,
    person: Person,
    *,
    image: bytes,
    direction: str,
    latitude: float | None,
    longitude: float | None,
    accuracy_m: float | None,
    captured_at: datetime | None = None,
) -> dict:
    """Verify identity + location and log a field event. Caller commits."""
    if not person.field_scan_enabled:
        raise FieldError("Field attendance isn't enabled for your account.", status_code=403)
    if direction not in ("entry", "exit"):
        raise FieldError("direction must be 'entry' or 'exit'.")

    # Mandatory check-in/out pairing: can't exit without being checked in, and
    # can't check in twice in a row.
    inside = open_entry_today(db, person)
    if direction == "entry" and inside:
        raise FieldError("You're already checked in. Please check out first.")
    if direction == "exit" and not inside:
        raise FieldError("You're not checked in yet. Please check in first.")

    # 1) Identity — 1:1 against the person's own enrolled template.
    blob = _enrolled_blob(db, person.id)
    if blob is None:
        raise FieldError("Your face isn't enrolled yet. Ask your supervisor to enroll you.", status_code=422)
    img = decode_image_bytes(image)
    if img is None:
        raise FieldError("The selfie couldn't be read. Please retry.", status_code=422)
    emb, quality = embed_largest_face(img)
    if emb is None:
        raise FieldError("No face detected. Keep your face centred and retry.", status_code=422)
    if quality < settings.field_min_quality:
        raise FieldError("Too blurry or off-angle. Retry in better light.", status_code=422)
    passed, sim = verify(emb, blob)
    if not passed:
        raise FieldError("Face didn't match your profile. Please try again.", status_code=422)

    # 2) Location — nearest station + geofence, tolerant of missing/coarse GPS.
    stations = db.execute(select(Station)).scalars().all()
    station, dist = nearest_station(latitude, longitude, stations) if (
        latitude is not None and longitude is not None and stations
    ) else (None, None)

    gps_ok = (
        latitude is not None
        and longitude is not None
        and accuracy_m is not None
        and accuracy_m <= settings.gps_max_accuracy_m
    )
    within = False
    if station is not None and dist is not None:
        radius = station.radius_m or settings.field_default_radius_m
        within, _ = inside_geofence(latitude, longitude, station.center_lat, station.center_lon, radius)

    # 3) Approve automatically only when location is confidently valid.
    if within and gps_ok:
        review_status = "approved"
        message = f"Checked {'in' if direction == 'entry' else 'out'} at {station.name}."
    else:
        review_status = "pending"
        if station is None:
            message = "Location unavailable — sent to your supervisor for approval."
        elif not gps_ok:
            message = f"GPS was uncertain near {station.name} — sent to your supervisor for approval."
        else:
            message = (f"Not at a station — {dist/1000:.1f} km from {station.name}. "
                       "Sent to your supervisor for approval.")

    # 4) Store the audit selfie + write the event.
    selfie_path = _save_selfie(person.external_id, image)
    # Offline scans carry their capture time; live scans use the trusted server clock.
    if captured_at is not None:
        when = captured_at.astimezone(timezone.utc).replace(tzinfo=None) if captured_at.tzinfo else captured_at
    else:
        when = datetime.now(timezone.utc).replace(tzinfo=None)
    ev = AttendanceEvent(
        person_id=person.id,
        is_visitor=False,
        similarity=sim,
        camera_label=f"field-{station.name}" if station else "field",
        direction=direction,
        source="field",
        event_time=when,
        latitude=latitude,
        longitude=longitude,
        location_verified=bool(within and gps_ok),
        review_status=review_status,
        gps_accuracy_m=accuracy_m,
        distance_m=dist,
        nearest_station_id=station.id if station else None,
        selfie_path=selfie_path,
    )
    db.add(ev)
    db.flush()

    # Alert the employee (and their supervisor's EA) when review is needed.
    if review_status == "pending":
        from app.services import notifications as notif
        notif.notify_field_pending(db, person, ev)

    return {
        "event": ev,
        "direction": direction,
        "review_status": review_status,
        "inside_geofence": bool(within and gps_ok),
        "station_name": station.name if station else None,
        "distance_m": dist,
        "message": message,
        "similarity": sim,
    }


def purge_old_selfies(db: Session) -> int:
    """Delete audit selfies older than the retention window; keep event metadata.
    Returns the number of files removed."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.field_selfie_retention_days)
    rows = db.execute(
        select(AttendanceEvent).where(AttendanceEvent.selfie_path.isnot(None))
    ).scalars().all()
    removed = 0
    for e in rows:
        when = e.event_time
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when < cutoff:
            try:
                Path(e.selfie_path).unlink(missing_ok=True)
            except OSError:
                pass
            e.selfie_path = None
            removed += 1
    db.commit()
    return removed
