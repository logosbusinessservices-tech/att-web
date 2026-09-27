"""Personal notification inbox (employees, EAs, and anyone signed in).

Currently carries field-attendance updates: a scan sent for approval, and its
later approval/rejection. Read-only list + a mark-all-read action.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db.database import get_db
from app.db.models import Notification, Person
from app.schemas import InboxItem

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[InboxItem])
def list_notifications(
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Notification)
        .where(Notification.person_id == current.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
    ).scalars().all()
    return rows


@router.post("/read")
def mark_all_read(
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.execute(
        update(Notification)
        .where(Notification.person_id == current.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return {"ok": True}
