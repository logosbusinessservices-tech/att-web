"""Edge gallery sync: the edge box PULLS enrolled face templates from the cloud.

The camera pipeline needs everyone's embeddings locally to recognize faces at the
gate. When a supervisor enrolls a new employee here, the edge picks it up on its
next poll of GET /edge/gallery (key-guarded, mirrors POST /events).

Incremental: pass ?since=<ISO8601> to fetch only templates updated after that
time, so the edge syncs deltas, not the whole gallery every minute.
"""

import base64
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.db.models import FaceEmbedding, Person
from app.schemas import EdgeDisplayMessage, EdgeDisplayMessages, GalleryItem
from app.services import display_messages as display_messages_service

router = APIRouter(prefix="/edge", tags=["edge"])


def _check_edge_key(x_edge_key: str | None = Header(default=None)):
    if x_edge_key != settings.edge_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid edge API key"
        )


@router.get("/gallery", response_model=list[GalleryItem], dependencies=[Depends(_check_edge_key)])
def gallery(
    since: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """All enrolled face templates (optionally only those updated after `since`)."""
    q = (
        select(FaceEmbedding, Person)
        .join(Person, FaceEmbedding.person_id == Person.id)
        .where(Person.is_active.is_(True))
    )
    if since is not None:
        q = q.where(FaceEmbedding.updated_at > since)

    out: list[GalleryItem] = []
    for emb, person in db.execute(q.order_by(FaceEmbedding.updated_at)).all():
        out.append(GalleryItem(
            external_id=person.external_id,
            display_name=person.display_name,
            num_photos=emb.num_photos,
            updated_at=emb.updated_at,
            embedding_b64=base64.b64encode(emb.embedding).decode("ascii"),
        ))
    return out


@router.get(
    "/display-messages",
    response_model=EdgeDisplayMessages,
    dependencies=[Depends(_check_edge_key)],
)
def display_messages(db: Session = Depends(get_db)):
    """The announcements every gate monitor shows, top first."""
    messages = display_messages_service.active_messages(db)
    return EdgeDisplayMessages(
        version=display_messages_service.board_version(messages),
        messages=[EdgeDisplayMessage(id=m.id, text=m.text) for m in messages],
    )
