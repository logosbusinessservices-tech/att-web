"""Edge (NUC) endpoints: gallery sync + gate-monitor announcements.

Gallery: the edge PULLS a full snapshot of everyone the gates should recognize
and replaces its local list with it. A full snapshot (rather than "what changed
since") means approvals that change an employee code, renames and deactivations
all reach the gate. The edge sends back the last `version` it holds; if nothing
changed it gets a tiny `unchanged` reply instead of the whole list.
"""

import base64
import hashlib
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.edge import require_edge_key
from app.config import settings
from app.db.database import get_db
from app.db.models import FaceEmbedding, Person
from app.face.model import EMBEDDING_DIM, model_fingerprint
from app.schemas import EdgeDisplayMessage, EdgeDisplayMessages, GalleryItem, GallerySnapshot
from app.services import display_messages as display_messages_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/edge", tags=["edge"])


def _gallery_version(rows) -> str:
    digest = hashlib.sha256(settings.face_model_name.encode("utf-8"))
    for emb, person in rows:
        digest.update(f"\x1f{person.external_id}\x1f{person.display_name}\x1f{emb.num_photos}\x1f".encode("utf-8"))
        digest.update(emb.embedding)
    return digest.hexdigest()[:20]


def _safe_fingerprint() -> str | None:
    try:
        return model_fingerprint()
    except Exception:
        log.exception("Could not fingerprint the recognition model")
        return None


@router.get("/gallery", response_model=GallerySnapshot, dependencies=[Depends(require_edge_key)])
def gallery(
    version: str | None = Query(default=None, max_length=64),
    db: Session = Depends(get_db),
):
    """Every active, enrolled person, plus the model the templates were built with."""
    rows = db.execute(
        select(FaceEmbedding, Person)
        .join(Person, FaceEmbedding.person_id == Person.id)
        .where(Person.is_active.is_(True), Person.status == "active")
        .order_by(Person.external_id)
    ).all()
    current = _gallery_version(rows)
    snapshot = GallerySnapshot(
        version=current,
        model_name=settings.face_model_name,
        model_sha256=_safe_fingerprint(),
        embedding_dim=EMBEDDING_DIM,
        count=len(rows),
    )
    if version == current:
        snapshot.unchanged = True
        return snapshot
    snapshot.items = [
        GalleryItem(
            external_id=person.external_id,
            display_name=person.display_name,
            num_photos=emb.num_photos,
            updated_at=emb.updated_at,
            embedding_b64=base64.b64encode(emb.embedding).decode("ascii"),
        )
        for emb, person in rows
    ]
    return snapshot


@router.get(
    "/display-messages",
    response_model=EdgeDisplayMessages,
    dependencies=[Depends(require_edge_key)],
)
def display_messages(db: Session = Depends(get_db)):
    """The announcements every gate monitor shows, top first."""
    messages = display_messages_service.active_messages(db)
    return EdgeDisplayMessages(
        version=display_messages_service.board_version(messages),
        messages=[EdgeDisplayMessage(id=m.id, text=m.text) for m in messages],
    )
