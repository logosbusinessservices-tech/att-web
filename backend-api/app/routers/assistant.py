"""Executive Assistant (EA) endpoints.

The EA decouples grunt work from the supervisor. An EA:
  1. Handles onboarding — the *global* sign-up approval queue (all departments).
  2. Completes tasks a supervisor delegates to them (their supervisor only):
       • field_approval  — decide a pending field scan.
       • attendance_edit — fix one employee's day (in/out times).

Onboarding is global (any EA can clear any pending sign-up, with an
already-handled guard). Delegated tasks are private to the assigned EA.
"""

import os
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_assistant
from app.db.database import get_db
from app.db.models import AttendanceEvent, DelegatedTask, Person, Station
from app.schemas import (
    AssistantProfileOut,
    DaySummary,
    DelegatedTaskOut,
    EmployeeCreated,
    EventAdd,
    EventEdit,
    FieldReviewDecision,
    OverrideCreate,
    OverrideOut,
    SignupApprove,
    SignupOut,
    SignupReject,
)
from app.routers.supervisor import (
    _day_for,
    _field_review_item,
    _is_enrolled,
    _seed_avatar_from,
    _signup_out,
)
from app.services import attendance_service as svc
from app.services import corrections
from app.services import enrollment as enroll_service
from app.services import notifications as notifications_service
from app.services import signup as signup_service

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _now():
    return datetime.now(timezone.utc)


# ── Profile ──────────────────────────────────────────────────────────────────
@router.get("/profile", response_model=AssistantProfileOut)
def assistant_profile(
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    sup = db.get(Person, current.manager_id) if current.manager_id else None
    return AssistantProfileOut(
        external_id=current.external_id,
        display_name=current.display_name,
        supervisor_external_id=sup.external_id if sup else None,
        supervisor_name=sup.display_name if sup else None,
    )


# ── Onboarding (global sign-up queue) ────────────────────────────────────────
@router.get("/signups", response_model=list[SignupOut])
def list_signups(
    status: str = Query(default="worklist"),
    _: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    """Every new hire still needing onboarding, across all departments. An item
    drops off once it's both approved and enrolled (or rejected)."""
    people = db.execute(
        select(Person)
        .where(Person.role == "employee")
        .order_by(Person.created_at.desc())
    ).scalars().all()

    out: list[SignupOut] = []
    for p in people:
        item = _signup_out(db, p)
        needs_work = p.status == "pending" or (p.status == "active" and not item.is_enrolled)
        if status == "all":
            if p.status in ("pending", "rejected") or needs_work:
                out.append(item)
        elif status in ("pending", "active", "rejected"):
            if p.status == status:
                out.append(item)
        else:  # worklist (default)
            if needs_work:
                out.append(item)
    return out


def _load_pending_signup(db: Session, signup_id: int) -> Person:
    p = db.get(Person, signup_id)
    if p is None or p.status != "pending":
        raise HTTPException(status_code=404, detail="Sign-up not found")
    return p


@router.post("/signups/{signup_id}/approve", response_model=EmployeeCreated)
def approve_signup(
    signup_id: int,
    body: SignupApprove,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    """Assign an employee code + permissions and activate the account (step 1)."""
    p = _load_pending_signup(db, signup_id)
    try:
        person = signup_service.approve_signup(
            db,
            approver=current,
            signup=p,
            external_id=body.external_id,
            manager_id=body.manager_id,
            home_station_id=body.home_station_id,
            field_scan_enabled=body.field_scan_enabled,
        )
    except signup_service.SignupError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    from app.db.models import Department
    dept = db.get(Department, person.department_id)
    return EmployeeCreated(
        id=person.id,
        external_id=person.external_id,
        display_name=person.display_name,
        department_id=person.department_id,
        department_name=dept.name if dept else None,
        role=person.role,
        enrolled=False,
    )


@router.post("/signups/{signup_id}/reject", response_model=SignupOut)
def reject_signup(
    signup_id: int,
    body: SignupReject,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    """Reject a self-sign-up (kept for audit); the applicant is notified."""
    p = _load_pending_signup(db, signup_id)
    try:
        person = signup_service.reject_signup(db, signup=p, reason=body.reason)
    except signup_service.SignupError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return _signup_out(db, person)


@router.post("/signups/{signup_id}/photos", response_model=SignupOut)
async def onboard_signup_photos(
    signup_id: int,
    photos: list[UploadFile] = File(...),
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    """Upload a new hire's attendance photos (step 2)."""
    p = db.get(Person, signup_id)
    if p is None or p.status == "rejected":
        raise HTTPException(status_code=404, detail="Sign-up not found")
    images = [await f.read() for f in photos]
    try:
        enroll_service.enroll_person(db, p, images)
    except enroll_service.EnrollmentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _seed_avatar_from(p, images)
    db.commit()
    db.refresh(p)
    return _signup_out(db, p)


# ── Delegated tasks ──────────────────────────────────────────────────────────
def _task_out(db: Session, t: DelegatedTask) -> DelegatedTaskOut:
    sup = db.get(Person, t.supervisor_id)
    out = DelegatedTaskOut(
        id=t.id,
        task_type=t.task_type,
        status=t.status,
        comment=t.comment,
        supervisor_name=sup.display_name if sup else "—",
        created_at=t.created_at,
    )
    if t.task_type == "field_approval" and t.event_id is not None:
        ev = db.get(AttendanceEvent, t.event_id)
        if ev is not None:
            person = db.get(Person, ev.person_id)
            station = db.get(Station, ev.nearest_station_id) if ev.nearest_station_id else None
            field = _field_review_item(ev, person, station)
            if ev.selfie_path:
                field.selfie_url = f"/assistant/field/selfie/{ev.id}"
            out.field = field
    elif t.task_type == "attendance_edit" and t.person_id is not None:
        person = db.get(Person, t.person_id)
        if person is not None and t.for_date:
            out.external_id = person.external_id
            out.display_name = person.display_name
            out.for_date = t.for_date
            out.day = _day_for(db, person, date.fromisoformat(t.for_date))
    return out


@router.get("/tasks", response_model=list[DelegatedTaskOut])
def list_tasks(
    type: str | None = Query(default=None),  # field_approval | attendance_edit
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    q = select(DelegatedTask).where(
        DelegatedTask.assistant_id == current.id,
        DelegatedTask.status == "open",
    )
    if type in ("field_approval", "attendance_edit"):
        q = q.where(DelegatedTask.task_type == type)
    tasks = db.execute(q.order_by(DelegatedTask.created_at.desc())).scalars().all()
    return [_task_out(db, t) for t in tasks]


def _load_open_task(db: Session, current: Person, task_id: int, task_type: str) -> DelegatedTask:
    t = db.get(DelegatedTask, task_id)
    if t is None or t.assistant_id != current.id:
        raise HTTPException(status_code=404, detail="Task not found")
    if t.task_type != task_type:
        raise HTTPException(status_code=400, detail="Wrong task type")
    if t.status != "open":
        raise HTTPException(status_code=409, detail="This task is no longer open")
    return t


def _decide_field(db: Session, current: Person, task_id: int, approved: bool) -> DelegatedTaskOut:
    t = _load_open_task(db, current, task_id, "field_approval")
    ev = db.get(AttendanceEvent, t.event_id) if t.event_id else None
    if ev is None or ev.source != "field":
        raise HTTPException(status_code=404, detail="Field scan not found")
    ev.review_status = "approved" if approved else "rejected"
    ev.location_verified = approved
    employee = db.get(Person, ev.person_id)
    if employee is not None:
        notifications_service.notify_field_decision(db, employee, ev, approved=approved)
    t.status = "completed"
    t.completed_by = current.id
    t.completed_at = _now()
    db.commit()
    db.refresh(t)
    return _task_out(db, t)


@router.post("/tasks/{task_id}/field/approve", response_model=DelegatedTaskOut)
def approve_field_task(
    task_id: int,
    body: FieldReviewDecision,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    return _decide_field(db, current, task_id, approved=True)


@router.post("/tasks/{task_id}/field/reject", response_model=DelegatedTaskOut)
def reject_field_task(
    task_id: int,
    body: FieldReviewDecision,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    return _decide_field(db, current, task_id, approved=False)


@router.get("/field/selfie/{event_id}")
def field_selfie(
    event_id: int,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    """Serve the audit selfie for a delegated field scan (EA must own a task on it)."""
    owns = db.execute(
        select(DelegatedTask.id).where(
            DelegatedTask.assistant_id == current.id,
            DelegatedTask.event_id == event_id,
        )
    ).first()
    if owns is None:
        raise HTTPException(status_code=404, detail="Field scan not found")
    ev = db.get(AttendanceEvent, event_id)
    if ev is None or not ev.selfie_path or not os.path.exists(ev.selfie_path):
        raise HTTPException(status_code=404, detail="Selfie no longer available")
    return FileResponse(ev.selfie_path, media_type="image/jpeg")


# ── Attendance-edit tasks: reuse the correction primitives, scoped to task ────
def _load_attendance_task(db: Session, current: Person, task_id: int) -> tuple[DelegatedTask, Person, date]:
    t = _load_open_task(db, current, task_id, "attendance_edit")
    person = db.get(Person, t.person_id)
    if person is None or not t.for_date:
        raise HTTPException(status_code=404, detail="Employee not found")
    return t, person, date.fromisoformat(t.for_date)


def _task_event_scoped(db: Session, person: Person, for_date: date, event_id: int) -> AttendanceEvent:
    ev = db.get(AttendanceEvent, event_id)
    if ev is None or ev.person_id != person.id or svc._to_local(ev.event_time).date() != for_date:
        raise HTTPException(status_code=404, detail="Crossing not in this task's day")
    return ev


@router.get("/tasks/{task_id}/day", response_model=DaySummary)
def task_day(
    task_id: int,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    _, person, for_date = _load_attendance_task(db, current, task_id)
    return _day_for(db, person, for_date)


@router.patch("/tasks/{task_id}/events/{event_id}", response_model=DaySummary)
def task_edit_crossing(
    task_id: int,
    event_id: int,
    body: EventEdit,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    _, person, for_date = _load_attendance_task(db, current, task_id)
    ev = _task_event_scoped(db, person, for_date, event_id)
    try:
        corrections.edit_event_time(db, current, ev, body.time)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return _day_for(db, person, for_date)


@router.delete("/tasks/{task_id}/events/{event_id}", response_model=DaySummary)
def task_delete_crossing(
    task_id: int,
    event_id: int,
    reason: str | None = Query(default=None),
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    _, person, for_date = _load_attendance_task(db, current, task_id)
    ev = _task_event_scoped(db, person, for_date, event_id)
    corrections.delete_event(db, current, ev, reason)
    db.commit()
    return _day_for(db, person, for_date)


@router.post("/tasks/{task_id}/events", response_model=DaySummary)
def task_add_crossing(
    task_id: int,
    body: EventAdd,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    _, person, for_date = _load_attendance_task(db, current, task_id)
    try:
        corrections.add_event(db, current, person, for_date, body.direction, body.time)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return _day_for(db, person, for_date)


@router.post("/tasks/{task_id}/override", response_model=OverrideOut)
def task_override(
    task_id: int,
    body: OverrideCreate,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    _, person, for_date = _load_attendance_task(db, current, task_id)
    if not (body.new_status or body.entry_time or body.exit_time):
        raise HTTPException(status_code=400, detail="Provide a status change or corrected time(s)")
    try:
        ov = corrections.apply_correction(
            db, person, for_date,
            new_status=body.new_status,
            entry_time=body.entry_time,
            exit_time=body.exit_time,
            reason=body.reason,
            supervisor=current,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return OverrideOut(
        ok=True, for_date=ov.for_date,
        original_status=ov.original_status, new_status=ov.new_status,
    )


@router.post("/tasks/{task_id}/complete", response_model=DelegatedTaskOut)
def complete_attendance_task(
    task_id: int,
    current: Person = Depends(require_assistant),
    db: Session = Depends(get_db),
):
    """Mark a delegated attendance-edit task done (EA-driven, per the workflow)."""
    t = _load_open_task(db, current, task_id, "attendance_edit")
    t.status = "completed"
    t.completed_by = current.id
    t.completed_at = _now()
    db.commit()
    db.refresh(t)
    return _task_out(db, t)
