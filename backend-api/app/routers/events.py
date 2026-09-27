"""Edge event ingestion: the camera pipeline POSTs recognition events here.

This is how the edge box (near the cameras) feeds the cloud DB the website reads.
Secured with a shared EDGE_API_KEY header, so the DB is never exposed directly.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.db.models import AttendanceEvent, Person
from app.schemas import EdgeEventIn, EventAck

router = APIRouter(prefix="/events", tags=["events"])


def _check_edge_key(x_edge_key: str | None = Header(default=None)):
    if x_edge_key != settings.edge_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid edge API key"
        )


@router.post("", response_model=EventAck, dependencies=[Depends(_check_edge_key)])
def ingest_event(payload: EdgeEventIn, db: Session = Depends(get_db)):
    """Store one camera attendance event (source='camera')."""
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
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return EventAck(id=event.id)
