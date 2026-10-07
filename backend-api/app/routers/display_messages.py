"""Executive Assistant: manage the announcements shown on the gate monitors."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.deps import require_assistant
from app.db.database import get_db
from app.db.models import DisplayMessage, Person
from app.schemas import DisplayMessageIn, DisplayMessageOut, DisplayMessageReorder
from app.services import display_messages as svc

router = APIRouter(prefix="/assistant/display-messages", tags=["display-messages"])


def _out(msg: DisplayMessage) -> DisplayMessageOut:
    return DisplayMessageOut(
        id=msg.id,
        text=msg.text,
        position=msg.position,
        created_at=msg.created_at,
        updated_at=msg.updated_at,
    )


def _raise(exc: svc.DisplayMessageError):
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("", response_model=list[DisplayMessageOut])
def list_messages(
    _: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    """Current board, top first."""
    return [_out(m) for m in svc.active_messages(db)]


@router.post("", response_model=DisplayMessageOut, status_code=status.HTTP_201_CREATED)
def add_message(
    body: DisplayMessageIn,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    try:
        return _out(svc.add_message(db, current, body.text))
    except svc.DisplayMessageError as exc:
        _raise(exc)


@router.patch("/{message_id}", response_model=DisplayMessageOut)
def edit_message(
    message_id: int,
    body: DisplayMessageIn,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    try:
        return _out(svc.edit_message(db, current, message_id, body.text))
    except svc.DisplayMessageError as exc:
        _raise(exc)


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_message(
    message_id: int,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    try:
        svc.remove_message(db, current, message_id)
    except svc.DisplayMessageError as exc:
        _raise(exc)


@router.put("/order", response_model=list[DisplayMessageOut])
def reorder_messages(
    body: DisplayMessageReorder,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    try:
        return [_out(m) for m in svc.reorder_messages(db, current, body.ids)]
    except svc.DisplayMessageError as exc:
        _raise(exc)
