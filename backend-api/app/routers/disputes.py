"""Employee-facing disputes (Phase 2).

An employee contests a day they disagree with. A dispute has a lifecycle:
    open -> (supervisor) -> resolved | rejected
Rules: can only dispute the last 30 days, not a future date, and not while an
open dispute already exists for that same date.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db.database import get_db
from app.db.models import AttendanceEvent, Dispute, Person
from app.schemas import DisputeCreate, DisputeOut, DisputeUpdate
from app.services import attendance_service as svc

router = APIRouter(prefix="/disputes", tags=["disputes"])

DISPUTE_WINDOW_DAYS = 30
_OPEN_STATES = ("open", "under_review")


def dispute_out(d: Dispute, person: Person | None) -> DisputeOut:
    return DisputeOut(
        id=d.id,
        person_id=d.person_id,
        external_id=person.external_id if person else None,
        display_name=person.display_name if person else None,
        for_date=d.for_date,
        target_kind=d.target_kind or "day",
        event_id=d.event_id,
        message=d.message,
        status=d.status,
        resolution_note=d.resolution_note,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


@router.post("", response_model=DisputeOut)
def create_dispute(
    body: DisputeCreate,
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = svc.today_local()
    if body.for_date > today:
        raise HTTPException(status_code=400, detail="Cannot dispute a future date")
    if (today - body.for_date).days > DISPUTE_WINDOW_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Disputes are limited to the last {DISPUTE_WINDOW_DAYS} days",
        )

    target_kind = body.target_kind or "day"
    if target_kind not in ("entry", "exit", "day"):
        raise HTTPException(status_code=400, detail="Invalid target_kind")

    # A dispute about a specific crossing must reference one of the employee's own
    # events, of the matching direction, on that date.
    if target_kind in ("entry", "exit"):
        if body.event_id is None:
            raise HTTPException(
                status_code=400, detail=f"An {target_kind} dispute must reference the crossing"
            )
        ev = db.get(AttendanceEvent, body.event_id)
        if ev is None or ev.person_id != current.id:
            raise HTTPException(status_code=404, detail="Crossing not found")
        if ev.direction != target_kind:
            raise HTTPException(
                status_code=400, detail=f"That crossing is not an {target_kind}"
            )
        if svc._to_local(ev.event_time).date() != body.for_date:
            raise HTTPException(status_code=400, detail="Crossing is not on that date")

    iso = body.for_date.isoformat()
    # No duplicate open dispute for the same target (date + kind + specific event).
    dup_q = select(Dispute).where(
        Dispute.person_id == current.id,
        Dispute.for_date == iso,
        Dispute.target_kind == target_kind,
        Dispute.status.in_(_OPEN_STATES),
    )
    if body.event_id is not None:
        dup_q = dup_q.where(Dispute.event_id == body.event_id)
    existing = db.execute(dup_q).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=400, detail="You already have an open dispute for this"
        )

    d = Dispute(
        person_id=current.id,
        for_date=iso,
        target_kind=target_kind,
        event_id=body.event_id,
        message=body.message,
        status="open",
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return dispute_out(d, current)


@router.patch("/{dispute_id}", response_model=DisputeOut)
def update_dispute(
    dispute_id: int,
    body: DisputeUpdate,
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Edit the explanation on your own dispute while it is still open."""
    d = db.get(Dispute, dispute_id)
    if d is None or d.person_id != current.id:
        raise HTTPException(status_code=404, detail="Dispute not found")
    if d.status not in _OPEN_STATES:
        raise HTTPException(
            status_code=400, detail="Only an open dispute can be edited"
        )
    d.message = body.message
    db.commit()
    db.refresh(d)
    return dispute_out(d, current)


@router.get("/me", response_model=list[DisputeOut])
def my_disputes(
    status: str | None = Query(default=None),
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(Dispute).where(Dispute.person_id == current.id)
    if status:
        q = q.where(Dispute.status == status)
    rows = db.execute(q.order_by(Dispute.created_at.desc())).scalars().all()
    return [dispute_out(d, current) for d in rows]
