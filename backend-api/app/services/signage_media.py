"""Signage media slides: images and videos shown on the gate monitors.

Only the EA001 super-admin can manage these. Each slide is an uploaded file
(JPEG, PNG, or MP4) stored in blob / local storage. The NUC downloads them
via the edge endpoint.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.config import settings
from app.db.models import Person, SignageMedia

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ("image", ".jpg"),
    "image/png": ("image", ".png"),
    "video/mp4": ("video", ".mp4"),
}

SUPER_ADMIN_EXTERNAL_ID = "EA001"


class SignageMediaError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def require_super_admin(person: Person) -> None:
    if person.external_id != SUPER_ADMIN_EXTERNAL_ID:
        raise SignageMediaError(
            "Only the super admin (EA001) can manage signage media.", status_code=403
        )


def active_media(db: Session) -> list[SignageMedia]:
    return list(db.execute(
        select(SignageMedia)
        .where(SignageMedia.removed_at.is_(None))
        .order_by(SignageMedia.position, SignageMedia.id)
    ).scalars().all())


def upload_media(
    db: Session, uploader: Person, data: bytes, filename: str, content_type: str,
) -> SignageMedia:
    """Validate and store a new media slide."""
    require_super_admin(uploader)

    ct_lower = content_type.lower()
    if ct_lower not in ALLOWED_CONTENT_TYPES:
        raise SignageMediaError(
            "Unsupported file type. Upload JPEG, PNG images or MP4 videos.",
            status_code=422,
        )

    if len(data) > settings.signage_media_max_bytes:
        mb = settings.signage_media_max_bytes // (1024 * 1024)
        raise SignageMediaError(
            f"File is too large. Maximum size is {mb} MB.", status_code=422
        )

    if not data:
        raise SignageMediaError("The uploaded file is empty.", status_code=422)

    current = active_media(db)
    if len(current) >= settings.signage_media_max_count:
        raise SignageMediaError(
            f"There are already {settings.signage_media_max_count} media slides. "
            "Remove one before uploading another.",
            status_code=409,
        )

    media_type, ext = ALLOWED_CONTENT_TYPES[ct_lower]
    blob_name = f"{uuid.uuid4().hex}{ext}"

    ref = storage.save(storage.SIGNAGE_MEDIA, blob_name, data, content_type=ct_lower)

    next_position = (max(m.position for m in current) + 1) if current else 0
    media = SignageMedia(
        media_type=media_type,
        original_filename=filename or blob_name,
        storage_ref=ref,
        content_type=ct_lower,
        file_size=len(data),
        position=next_position,
        created_by=uploader.id,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def remove_media(db: Session, remover: Person, media_id: int) -> None:
    require_super_admin(remover)
    media = db.get(SignageMedia, media_id)
    if media is None or media.removed_at is not None:
        raise SignageMediaError("Media not found.", status_code=404)
    media.removed_at = _now()
    media.removed_by = remover.id
    db.commit()
    # Delete the actual file from storage.
    storage.delete(media.storage_ref)


def reorder_media(db: Session, editor: Person, ids: list[int]) -> list[SignageMedia]:
    require_super_admin(editor)
    current = active_media(db)
    if len(ids) != len(set(ids)) or set(ids) != {m.id for m in current}:
        raise SignageMediaError(
            "The media list has changed. Refresh and try again.", status_code=409
        )
    by_id = {m.id: m for m in current}
    for position, media_id in enumerate(ids):
        item = by_id[media_id]
        if item.position != position:
            item.position = position
    db.commit()
    return active_media(db)


def media_version(items: list[SignageMedia]) -> str:
    """Short fingerprint so the NUC can skip downloads when nothing changed."""
    payload = json.dumps(
        [[m.id, m.media_type, m.file_size] for m in items], ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
