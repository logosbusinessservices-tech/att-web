"""Edge event ingestion: the camera pipeline POSTs recognition events here.

This is how the edge box (near the cameras) feeds the cloud DB the website reads.
Secured with a shared EDGE_API_KEY header, so the DB is never exposed directly.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.edge import require_edge_key
from app.config import settings
from app.db.database import get_db
from app.db.models import AttendanceEvent, Person
from app.schemas import EdgeEventIn, EventAck

router = APIRouter(prefix="/events", tags=["events"])


def _existing_event_id(db: Session, event_uuid: str) -> int | None:
    return db.execute(
        select(AttendanceEvent.id).where(AttendanceEvent.event_uuid == event_uuid)
    ).scalar_one_or_none()


@router.post("", response_model=EventAck, dependencies=[Depends(require_edge_key)])
def ingest_event(payload: EdgeEventIn, db: Session = Depends(get_db)):
    """Store one camera attendance event (source='camera').

    Safe to retry: an event whose `event_uuid` was already stored is answered
    with status 'duplicate' and the original id, and nothing new is written.
    """
    if payload.event_uuid:
        existing = _existing_event_id(db, payload.event_uuid)
        if existing is not None:
            return EventAck(id=existing, status="duplicate")

    if payload.direction is not None and payload.direction.lower() not in ("entry", "exit"):
        raise HTTPException(status_code=422, detail="direction must be 'entry' or 'exit'")

    person_id = None
    if not payload.is_visitor and payload.external_id:
        person = db.execute(
            select(Person).where(Person.external_id == payload.external_id)
        ).scalar_one_or_none()
        if person is not None:
            person_id = person.id

    # Direction: trust the edge if it sent one, else derive from camera_label.
    direction = payload.direction
    if direction is None:
        direction = settings.camera_direction_map.get(payload.camera_label)
    if direction is not None:
        direction = direction.lower()

    event = AttendanceEvent(
        person_id=person_id,
        is_visitor=payload.is_visitor or person_id is None,
        similarity=payload.similarity,
        camera_label=payload.camera_label,
        track_id=payload.track_id,
        source="camera",
        direction=direction,
        event_time=payload.event_time or datetime.now(timezone.utc),
        event_uuid=payload.event_uuid,
        crop_path=payload.crop_ref,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        # Two copies of the same event raced past the check above.
        db.rollback()
        existing = _existing_event_id(db, payload.event_uuid) if payload.event_uuid else None
        if existing is None:
            raise
        return EventAck(id=existing, status="duplicate")
    db.refresh(event)
    return EventAck(id=event.id)
