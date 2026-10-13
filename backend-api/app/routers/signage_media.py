"""Super-admin (EA001): manage image/video slides on the gate monitors."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.deps import require_assistant
from app.db.database import get_db
from app.db.models import Person, SignageMedia
from app import storage
from app.schemas import SignageMediaOut, SignageMediaReorder
from app.services import signage_media as svc

router = APIRouter(prefix="/assistant/signage-media", tags=["signage-media"])


def _out(m: SignageMedia) -> SignageMediaOut:
    return SignageMediaOut(
        id=m.id,
        media_type=m.media_type,
        original_filename=m.original_filename,
        content_type=m.content_type,
        file_size=m.file_size,
        position=m.position,
        created_at=m.created_at,
    )


def _raise(exc: svc.SignageMediaError):
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("", response_model=list[SignageMediaOut])
def list_media(
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    try:
        svc.require_super_admin(current)
    except svc.SignageMediaError as exc:
        _raise(exc)
    return [_out(m) for m in svc.active_media(db)]


@router.post("", response_model=SignageMediaOut, status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile = File(...),
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    try:
        data = await file.read()
        return _out(svc.upload_media(db, current, data, file.filename, file.content_type))
    except svc.SignageMediaError as exc:
        _raise(exc)


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_media(
    media_id: int,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    try:
        svc.remove_media(db, current, media_id)
    except svc.SignageMediaError as exc:
        _raise(exc)


@router.put("/order", response_model=list[SignageMediaOut])
def reorder_media(
    body: SignageMediaReorder,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    try:
        return [_out(m) for m in svc.reorder_media(db, current, body.ids)]
    except svc.SignageMediaError as exc:
        _raise(exc)


@router.get("/{media_id}/preview")
def preview_media(
    media_id: int,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    """Serve the file for in-browser preview (thumbnail / video player)."""
    try:
        svc.require_super_admin(current)
    except svc.SignageMediaError as exc:
        _raise(exc)
    media = db.get(SignageMedia, media_id)
    if media is None or media.removed_at is not None:
        raise HTTPException(status_code=404, detail="Media not found.")
    data = storage.load(media.storage_ref)
    if data is None:
        raise HTTPException(status_code=404, detail="File not found in storage.")
    return Response(content=data, media_type=media.content_type)
