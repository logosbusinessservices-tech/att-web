"""Supervisor read endpoints (Phase 1 data layer).

Provides attendance the three ways requested:
  1. All employees (org-wide) rollup
  2. Department-wise (filter by department_id)
  3. Individual employee (per-day summary for any employee)

Role-guarded. The rich dashboard UI is Phase 2; these endpoints power it.
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_supervisor
from app.auth.security import hash_password
from app.config import settings
from app.db.database import get_db
from app.db.models import (
    AttendanceEvent,
    DelegatedTask,
    Department,
    Dispute,
    FaceEmbedding,
    Person,
    Station,
)
from app.routers.disputes import dispute_out
from app.schemas import (
    AnomalyDayOut,
    DaySummary,
    DelegateAttendanceRequest,
    DelegateFieldRequest,
    DepartmentOut,
    DisputeOut,
    DisputeReject,
    DisputeResolve,
    EmployeeCreate,
    EmployeeCreated,
    EmployeeSettingsOut,
    EmployeeSettingsUpdate,
    EnrollResult,
    EventAdd,
    EventEdit,
    FieldReviewDecision,
    FieldReviewItem,
    NotificationOut,
    OverrideCreate,
    OverrideOut,
    PersonRollup,
    SignupOut,
    SupervisorOut,
)
from app.services import attendance_service as svc
from app.services import corrections
from app.services import enrollment as enroll_service
from app.services import notifications as notifications_service
from app.services.report import build_overview_workbook

router = APIRouter(prefix="/supervisor", tags=["supervisor"])


def _default_month() -> tuple[date, date]:
    today = svc.today_local()
    return svc.month_range(today.year, today.month)


def _is_chief(current: Person) -> bool:
    return current.role == "chief"


def _dept_scope(current: Person, requested: int | None) -> int | None:
    """Which department to show. The chief manager may view any/all departments;
    a supervisor is locked to their own regardless of what's requested."""
    if _is_chief(current):
        return requested
    return current.department_id


def _mgmt_types(current: Person, types: str | None) -> str | None:
    """The chief's default view includes supervisors alongside employees."""
    if types is None and _is_chief(current):
        return "office,field,supervisor"
    return types


@router.get("/departments", response_model=list[DepartmentOut])
def departments(
    _: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    return db.execute(select(Department).order_by(Department.name)).scalars().all()


@router.get("/attendance/overview", response_model=list[PersonRollup])
def overview(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    department_id: int | None = Query(default=None),
    types: str | None = Query(default=None),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Per-employee rollup over a range. Optionally filter by department + staff type."""
    if from_date is None or to_date is None:
        from_date, to_date = _default_month()
    department_id = _dept_scope(current, department_id)
    types = _mgmt_types(current, types)
    return _compute_rollups(db, from_date, to_date, department_id, types)


def _compute_rollups(
    db: Session, from_date: date, to_date: date, department_id: int | None, types: str | None = None
) -> list[PersonRollup]:
    from app.services import analytics
    people = analytics._people(db, department_id, types)

    # Preload department names once.
    dept_names = {
        d.id: d.name for d in db.execute(select(Department)).scalars().all()
    }

    rollups: list[PersonRollup] = []
    for p in people:
        events = db.execute(
            select(AttendanceEvent).where(AttendanceEvent.person_id == p.id)
        ).scalars().all()
        ov = corrections.latest_overrides(db, p.id, from_date, to_date)
        days = svc.summarize_person(events, from_date, to_date, ov)
        stats = svc.compute_stats(days, from_date, to_date)
        rollups.append(
            PersonRollup(
                person_id=p.id,
                external_id=p.external_id,
                display_name=p.display_name,
                department_id=p.department_id,
                department_name=dept_names.get(p.department_id),
                present=stats["present"],
                absent=stats["absent"],
                attendance_pct=stats["attendance_pct"],
                total_hours=stats["total_hours"],
            )
        )
    return rollups


@router.get("/employee/{external_id}/summary", response_model=list[DaySummary])
def employee_summary(
    external_id: str,
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Per-day summary for one employee (case 3)."""
    if from_date is None or to_date is None:
        from_date, to_date = _default_month()
    person = db.execute(
        select(Person).where(Person.external_id == external_id)
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    _assert_same_department(current, person)
    events = db.execute(
        select(AttendanceEvent).where(AttendanceEvent.person_id == person.id)
    ).scalars().all()
    ov = corrections.latest_overrides(db, person.id, from_date, to_date)
    return svc.summarize_person(events, from_date, to_date, ov)


@router.get("/attendance/export")
def export_overview(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    department_id: int | None = Query(default=None),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Download an Excel (.xlsx) attendance report for the range/department."""
    if from_date is None or to_date is None:
        from_date, to_date = _default_month()

    department_id = _dept_scope(current, department_id)
    rollups = _compute_rollups(db, from_date, to_date, department_id, _mgmt_types(current, None))
    dept_name = None
    if department_id is not None:
        dept = db.get(Department, department_id)
        dept_name = dept.name if dept else None

    stream = build_overview_workbook(rollups, from_date, to_date, dept_name)
    fname = f"attendance_{from_date}_{to_date}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ── Disputes & overrides (Phase 2) ───────────────────────────────────────
def _assert_same_department(supervisor: Person, employee: Person) -> None:
    """Dept-scoped authority: a supervisor may only act on their own department.
    The chief manager is exempt (may act across all departments)."""
    if supervisor.role == "chief":
        return
    if supervisor.department_id is None or supervisor.department_id != employee.department_id:
        raise HTTPException(
            status_code=403, detail="This employee is not in your department"
        )


@router.get("/disputes", response_model=list[DisputeOut])
def list_disputes(
    status: str = Query(default="open"),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Pending queue, scoped to the supervisor's own department."""
    if current.department_id is None:
        return []
    q = (
        select(Dispute, Person)
        .join(Person, Dispute.person_id == Person.id)
        .where(Person.department_id == current.department_id)
    )
    if status != "all":
        q = q.where(Dispute.status == status)
    rows = db.execute(q.order_by(Dispute.created_at.desc())).all()
    return [dispute_out(d, p) for d, p in rows]


def _load_dispute(db: Session, dispute_id: int) -> tuple[Dispute, Person]:
    d = db.get(Dispute, dispute_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Dispute not found")
    person = db.get(Person, d.person_id)
    return d, person


@router.post("/disputes/{dispute_id}/approve", response_model=DisputeOut)
def approve_dispute(
    dispute_id: int,
    body: DisputeResolve,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    d, person = _load_dispute(db, dispute_id)
    _assert_same_department(current, person)
    tk = d.target_kind or "day"

    # Per-target rules: an entry dispute only alters the entry time, an exit
    # dispute only the exit time, a day dispute may set either/both (+status).
    if tk == "entry" and not body.entry_time:
        raise HTTPException(status_code=400, detail="Provide the corrected entry time")
    if tk == "exit" and not body.exit_time:
        raise HTTPException(status_code=400, detail="Provide the corrected exit time")
    if tk == "day" and not (body.new_status or body.entry_time or body.exit_time):
        raise HTTPException(
            status_code=400, detail="Provide a status change or corrected time(s)"
        )

    entry_time = body.entry_time if tk in ("entry", "day") else None
    exit_time = body.exit_time if tk in ("exit", "day") else None
    new_status = body.new_status if tk == "day" else None
    try:
        corrections.apply_correction(
            db, person, date.fromisoformat(d.for_date),
            target_kind=tk,
            disputed_event_id=d.event_id,
            new_status=new_status,
            entry_time=entry_time,
            exit_time=exit_time,
            reason=body.reason or d.message,
            supervisor=current,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    d.status = "resolved"
    d.resolution_note = body.reason
    d.resolved_by = current.id
    db.commit()
    db.refresh(d)
    return dispute_out(d, person)


@router.post("/disputes/{dispute_id}/reject", response_model=DisputeOut)
def reject_dispute(
    dispute_id: int,
    body: DisputeReject,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    d, person = _load_dispute(db, dispute_id)
    _assert_same_department(current, person)
    d.status = "rejected"
    d.resolution_note = body.resolution_note
    d.resolved_by = current.id
    db.commit()
    db.refresh(d)
    return dispute_out(d, person)


@router.post("/overrides", response_model=OverrideOut)
def create_override(
    body: OverrideCreate,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Direct correction with no dispute (e.g. a known team-wide offsite)."""
    person = db.execute(
        select(Person).where(Person.external_id == body.external_id)
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    _assert_same_department(current, person)
    if not (body.new_status or body.entry_time or body.exit_time):
        raise HTTPException(
            status_code=400, detail="Provide a status change or corrected time(s)"
        )
    try:
        ov = corrections.apply_correction(
            db, person, body.for_date,
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


# ── Granular crossing edits: edit time / delete / add ────────────────────────
def _day_for(db: Session, person: Person, for_date: date) -> DaySummary:
    events = db.execute(
        select(AttendanceEvent).where(AttendanceEvent.person_id == person.id)
    ).scalars().all()
    ov = corrections.latest_overrides(db, person.id, for_date, for_date)
    return DaySummary(**svc.summarize_person(events, for_date, for_date, ov)[0])


def _load_event_dept_scoped(db: Session, current: Person, event_id: int) -> tuple[AttendanceEvent, Person]:
    ev = db.get(AttendanceEvent, event_id)
    if ev is None or ev.person_id is None:
        raise HTTPException(status_code=404, detail="Crossing not found")
    person = db.get(Person, ev.person_id)
    _assert_same_department(current, person)
    return ev, person


@router.patch("/events/{event_id}", response_model=DaySummary)
def edit_crossing(
    event_id: int,
    body: EventEdit,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Change one crossing's time (append-only, audit-logged)."""
    ev, person = _load_event_dept_scoped(db, current, event_id)
    try:
        corrections.edit_event_time(db, current, ev, body.time)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return _day_for(db, person, svc._to_local(ev.event_time).date())


@router.delete("/events/{event_id}", response_model=DaySummary)
def delete_crossing(
    event_id: int,
    reason: str | None = Query(default=None),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Remove one crossing (append-only tombstone, audit-logged)."""
    ev, person = _load_event_dept_scoped(db, current, event_id)
    for_date = svc._to_local(ev.event_time).date()
    corrections.delete_event(db, current, ev, reason)
    db.commit()
    return _day_for(db, person, for_date)


@router.post("/events", response_model=DaySummary)
def add_crossing(
    body: EventAdd,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Add a new entry/exit crossing to a day (validated + audit-logged)."""
    person = db.execute(
        select(Person).where(Person.external_id == body.external_id)
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    _assert_same_department(current, person)
    try:
        corrections.add_event(db, current, person, body.for_date, body.direction, body.time)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return _day_for(db, person, body.for_date)


@router.get("/anomalies", response_model=list[AnomalyDayOut])
def anomalies(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    department_id: int | None = Query(default=None),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Days with impossible entry/exit sequences the supervisor should review.

    Scoped to the supervisor's own department (or a chosen sub-filter within it).
    """
    if from_date is None or to_date is None:
        from_date, to_date = _default_month()
    dept = department_id if department_id is not None else current.department_id
    if dept is None:
        return []
    people = db.execute(
        select(Person).where(
            Person.role == "employee",
            Person.department_id == dept,
            Person.is_active.is_(True),
        )
    ).scalars().all()

    out: list[AnomalyDayOut] = []
    for p in people:
        events = db.execute(
            select(AttendanceEvent).where(AttendanceEvent.person_id == p.id)
        ).scalars().all()
        ov = corrections.latest_overrides(db, p.id, from_date, to_date)
        for day in svc.summarize_person(events, from_date, to_date, ov):
            if day["has_anomaly"]:
                out.append(AnomalyDayOut(
                    external_id=p.external_id,
                    display_name=p.display_name,
                    date=day["date"],
                    anomalies=day["anomalies"],
                ))
    return out


def _aware(dt: datetime) -> datetime:
    """SQLite may return naive datetimes; treat those as UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Actionable alerts for the supervisor's own department:
      • password_reminder — an onboarded employee hasn't changed their default
        password within the configured window (default 3 days).
      • enroll_photos — a newly activated employee's attendance photos still
        haven't been uploaded (nag, escalates after the reminder window).
      • camera_error — two entries or two exits in a row (a missed opposite
        crossing → likely a camera-recognition miss) in the last two weeks.
    """
    if current.department_id is None:
        return []

    people = db.execute(
        select(Person).where(
            Person.department_id == current.department_id,
            Person.is_active.is_(True),
        )
    ).scalars().all()

    out: list[NotificationOut] = []
    now = datetime.now(timezone.utc)

    # 1) Unchanged default passwords past the reminder window.
    for p in people:
        if p.must_change_password and p.password_hash:
            since = _aware(p.activated_at) if p.activated_at else _aware(p.created_at)
            age_days = (now - since).days
            if age_days >= settings.password_reminder_days:
                out.append(NotificationOut(
                    type="password_reminder",
                    severity="warning",
                    external_id=p.external_id,
                    display_name=p.display_name,
                    message=(
                        f"{p.display_name} hasn't changed their default password "
                        f"in {age_days} days. Please remind them to set a new one."
                    ),
                ))

    # 1b) Newly activated employees whose attendance photos aren't enrolled yet.
    for p in people:
        if p.role != "employee" or _is_enrolled(db, p.id):
            continue
        since = _aware(p.activated_at) if p.activated_at else _aware(p.created_at)
        age_days = (now - since).days
        overdue = age_days >= settings.enroll_reminder_days
        out.append(NotificationOut(
            type="enroll_photos",
            severity="warning" if overdue else "info",
            external_id=p.external_id,
            display_name=p.display_name,
            message=(
                f"Upload attendance photos for {p.display_name} "
                + (
                    f"— overdue by {age_days - settings.enroll_reminder_days} day(s)."
                    if overdue
                    else f"within {settings.enroll_reminder_days} days of activation."
                )
            ),
        ))

    # 2) Back-to-back entry/entry or exit/exit — a camera miss to review.
    today = svc.today_local()
    from_date = today - timedelta(days=14)
    for p in people:
        if p.role != "employee":
            continue
        events = db.execute(
            select(AttendanceEvent).where(AttendanceEvent.person_id == p.id)
        ).scalars().all()
        ov = corrections.latest_overrides(db, p.id, from_date, today)
        for day in svc.summarize_person(events, from_date, today, ov):
            for a in day["anomalies"]:
                if a["type"] in ("missing_exit", "missing_entry"):
                    out.append(NotificationOut(
                        type="camera_error",
                        severity="warning",
                        external_id=p.external_id,
                        display_name=p.display_name,
                        date=day["date"],
                        message=f"{p.display_name} · {day['date']}: {a['message']}",
                    ))
    return out



# ── Onboarding & face enrollment from photos ──────────────────────────
def _is_enrolled(db: Session, person_id: int) -> bool:
    return db.execute(
        select(FaceEmbedding.id).where(FaceEmbedding.person_id == person_id)
    ).first() is not None


@router.post("/employees", response_model=EmployeeCreated)
def create_employee(
    body: EmployeeCreate,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Create a new person in a department with an assigned supervisor.

    Their default password is their employee code; they're flagged to change it
    on first login (and can also log in by OTP to their phone)."""
    if body.role not in ("employee", "supervisor"):
        raise HTTPException(status_code=400, detail="Invalid role")

    department_id = body.department_id or current.department_id
    if department_id is None:
        raise HTTPException(status_code=400, detail="Select a department")
    if db.get(Department, department_id) is None:
        raise HTTPException(status_code=400, detail="Department not found")

    manager_id = body.manager_id if body.manager_id is not None else current.id
    manager = db.get(Person, manager_id) if manager_id else None
    if manager is not None and manager.role != "supervisor":
        raise HTTPException(status_code=400, detail="Assigned manager must be a supervisor")

    exists = db.execute(
        select(Person).where(Person.external_id == body.external_id)
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="Employee code already in use")

    person = Person(
        external_id=body.external_id,
        display_name=body.display_name,
        role=body.role,
        department_id=department_id,
        manager_id=manager_id,
        home_station_id=body.home_station_id or current.home_station_id,
        phone=body.phone,
        email=body.email,
        blood_group=body.blood_group,
        password_hash=hash_password(body.external_id),
        must_change_password=True,
        field_scan_enabled=body.field_scan_enabled,
    )
    db.add(person)
    db.commit()
    db.refresh(person)
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


# ── Self sign-up approval queue ───────────────────────────────────────────────
def _seed_avatar_from(person: Person, images: list[bytes]) -> None:
    """Set a default profile avatar from the first supervisor-taken photo,
    unless the person already has one."""
    if person.avatar_path or not images:
        return
    import os
    import uuid
    os.makedirs(settings.avatar_dir, exist_ok=True)
    path = os.path.join(settings.avatar_dir, f"{person.id}_{uuid.uuid4().hex[:8]}.jpg")
    try:
        with open(path, "wb") as fh:
            fh.write(images[0])
        person.avatar_path = path
    except OSError:
        pass


def _signup_out(db: Session, p: Person) -> SignupOut:
    dept = db.get(Department, p.department_id) if p.department_id else None
    station = db.get(Station, p.home_station_id) if p.home_station_id else None
    assigned = p.external_id if not (p.external_id or "").startswith("SIGNUP-") else None
    return SignupOut(
        id=p.id,
        display_name=p.display_name,
        phone=p.phone,
        email=p.email,
        blood_group=p.blood_group,
        department_id=p.department_id,
        department_name=dept.name if dept else None,
        home_station_id=p.home_station_id,
        home_station_name=station.name if station else None,
        status=p.status,
        created_at=p.created_at,
        external_id=assigned,
        is_approved=(p.status == "active"),
        is_enrolled=_is_enrolled(db, p.id),
        field_scan_enabled=bool(p.field_scan_enabled),
    )


# NOTE: Self sign-up onboarding now lives entirely in Executive Assistant mode
# (see app/routers/assistant.py). The supervisor is no longer responsible for the
# approve-sign-ups queue. The helpers above (_signup_out, _seed_avatar_from,
# _is_enrolled) are reused by the assistant router.


@router.post("/employees/{external_id}/enroll", response_model=EnrollResult)
async def enroll_employee(
    external_id: str,
    photos: list[UploadFile] = File(...),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Upload photos of an employee -> build their face template (embedding).

    The template is comparable with the camera pipeline's, and the edge pulls it
    via GET /edge/gallery for on-site recognition.
    """
    person = db.execute(
        select(Person).where(Person.external_id == external_id)
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    _assert_same_department(current, person)

    images = [await f.read() for f in photos]
    try:
        summary = enroll_service.enroll_person(db, person, images)
    except enroll_service.EnrollmentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _seed_avatar_from(person, images)
    db.commit()
    return EnrollResult(
        external_id=external_id,
        enrolled=True,
        photos_used=summary["photos_used"],
        photos_submitted=summary["photos_submitted"],
        notes=summary["notes"],
    )


@router.get("/ping")
def supervisor_ping(current: Person = Depends(require_supervisor)):
    return {"ok": True, "supervisor": current.display_name}


# ── Field attendance approvals (uncertain-location scans) ─────────────────────
def _field_review_item(ev: AttendanceEvent, person: Person, station: Station | None) -> FieldReviewItem:
    return FieldReviewItem(
        event_id=ev.id,
        external_id=person.external_id,
        display_name=person.display_name,
        for_date=svc._to_local(ev.event_time).date().isoformat(),
        event_time=ev.event_time,
        direction=ev.direction,
        latitude=ev.latitude,
        longitude=ev.longitude,
        gps_accuracy_m=ev.gps_accuracy_m,
        distance_m=ev.distance_m,
        nearest_station_name=station.name if station else None,
        selfie_url=f"/supervisor/field/selfie/{ev.id}" if ev.selfie_path else None,
        similarity=ev.similarity,
    )


@router.get("/field/approvals", response_model=list[FieldReviewItem])
def field_approvals(
    status: str = Query(default="pending"),
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Field scans needing a decision. Scoped to the supervisor's department;
    the chief manager sees every department."""
    q = (
        select(AttendanceEvent, Person)
        .join(Person, AttendanceEvent.person_id == Person.id)
        .where(AttendanceEvent.source == "field")
    )
    if not _is_chief(current):
        if current.department_id is None:
            return []
        q = q.where(Person.department_id == current.department_id)
    if status != "all":
        q = q.where(AttendanceEvent.review_status == status)
    rows = db.execute(q.order_by(AttendanceEvent.event_time.desc())).all()
    # Which of these are currently delegated to this supervisor's EA (open task)?
    delegated = {
        t.event_id: t.id
        for t in db.execute(
            select(DelegatedTask).where(
                DelegatedTask.supervisor_id == current.id,
                DelegatedTask.task_type == "field_approval",
                DelegatedTask.status == "open",
            )
        ).scalars().all()
    }
    out = []
    for ev, person in rows:
        station = db.get(Station, ev.nearest_station_id) if ev.nearest_station_id else None
        item = _field_review_item(ev, person, station)
        if ev.id in delegated:
            item.delegated = True
            item.delegated_task_id = delegated[ev.id]
        out.append(item)
    return out


def _load_field_event(db: Session, current: Person, event_id: int) -> tuple[AttendanceEvent, Person]:
    ev = db.get(AttendanceEvent, event_id)
    if ev is None or ev.source != "field":
        raise HTTPException(status_code=404, detail="Field scan not found")
    person = db.get(Person, ev.person_id)
    _assert_same_department(current, person)
    return ev, person


@router.post("/field/approvals/{event_id}/approve", response_model=FieldReviewItem)
def approve_field(
    event_id: int,
    body: FieldReviewDecision,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Accept an uncertain-location field scan (special circumstances)."""
    ev, person = _load_field_event(db, current, event_id)
    ev.review_status = "approved"
    ev.location_verified = True
    notifications_service.notify_field_decision(db, person, ev, approved=True)
    db.commit()
    db.refresh(ev)
    station = db.get(Station, ev.nearest_station_id) if ev.nearest_station_id else None
    return _field_review_item(ev, person, station)


@router.post("/field/approvals/{event_id}/reject", response_model=FieldReviewItem)
def reject_field(
    event_id: int,
    body: FieldReviewDecision,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Reject a field scan; it stops counting toward attendance."""
    ev, person = _load_field_event(db, current, event_id)
    ev.review_status = "rejected"
    ev.location_verified = False
    notifications_service.notify_field_decision(db, person, ev, approved=False)
    db.commit()
    db.refresh(ev)
    station = db.get(Station, ev.nearest_station_id) if ev.nearest_station_id else None
    return _field_review_item(ev, person, station)


@router.get("/field/selfie/{event_id}")
def field_selfie(
    event_id: int,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Serve the audit selfie for a field scan (dept-scoped, may be purged)."""
    ev, _ = _load_field_event(db, current, event_id)
    if not ev.selfie_path:
        raise HTTPException(status_code=404, detail="Selfie no longer available")
    import os
    if not os.path.exists(ev.selfie_path):
        raise HTTPException(status_code=404, detail="Selfie no longer available")
    return FileResponse(ev.selfie_path, media_type="image/jpeg")


# ── Delegation to the Executive Assistant ────────────────────────────────────
def _my_assistant(db: Session, supervisor: Person) -> Person:
    """Resolve the supervisor's single EA (role 'assistant', managed by them)."""
    ea = db.execute(
        select(Person).where(
            Person.role == "assistant",
            Person.manager_id == supervisor.id,
            Person.is_active.is_(True),
        )
    ).scalars().first()
    if ea is None:
        raise HTTPException(
            status_code=400,
            detail="You don't have an Executive Assistant to delegate to.",
        )
    return ea


@router.post("/field/approvals/delegate")
def delegate_field_approvals(
    body: DelegateFieldRequest,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Hand one or more pending field scans to your EA (auto-assigned)."""
    if not body.event_ids:
        raise HTTPException(status_code=400, detail="Select at least one scan to delegate.")
    ea = _my_assistant(db, current)
    comment = (body.comment or "").strip() or None
    created = 0
    for event_id in body.event_ids:
        ev, _ = _load_field_event(db, current, event_id)
        if ev.review_status != "pending":
            continue
        already = db.execute(
            select(DelegatedTask.id).where(
                DelegatedTask.event_id == event_id,
                DelegatedTask.status == "open",
            )
        ).first()
        if already is not None:
            continue
        db.add(DelegatedTask(
            task_type="field_approval",
            supervisor_id=current.id,
            assistant_id=ea.id,
            comment=comment,
            event_id=event_id,
        ))
        created += 1
    db.commit()
    return {"delegated": created, "assistant": ea.display_name}


@router.post("/attendance/delegate")
def delegate_attendance_edit(
    body: DelegateAttendanceRequest,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Delegate fixing one employee's day to your EA (comment mandatory)."""
    if not (body.comment or "").strip():
        raise HTTPException(status_code=400, detail="A comment is required when delegating.")
    person = db.execute(
        select(Person).where(Person.external_id == body.external_id)
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    _assert_same_department(current, person)
    ea = _my_assistant(db, current)
    existing = db.execute(
        select(DelegatedTask.id).where(
            DelegatedTask.task_type == "attendance_edit",
            DelegatedTask.person_id == person.id,
            DelegatedTask.for_date == body.for_date.isoformat(),
            DelegatedTask.status == "open",
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="This day is already delegated.")
    db.add(DelegatedTask(
        task_type="attendance_edit",
        supervisor_id=current.id,
        assistant_id=ea.id,
        comment=body.comment.strip(),
        person_id=person.id,
        for_date=body.for_date.isoformat(),
    ))
    db.commit()
    return {"delegated": 1, "assistant": ea.display_name}


@router.post("/tasks/{task_id}/recall")
def recall_task(
    task_id: int,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Pull back a delegated task before the EA completes it."""
    t = db.get(DelegatedTask, task_id)
    if t is None or t.supervisor_id != current.id:
        raise HTTPException(status_code=404, detail="Task not found")
    if t.status != "open":
        raise HTTPException(status_code=409, detail="This task is no longer open")
    t.status = "recalled"
    db.commit()
    return {"ok": True}


@router.get("/assistant")
def my_assistant(
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Who is this supervisor's Executive Assistant (if any)."""
    ea = db.execute(
        select(Person).where(
            Person.role == "assistant",
            Person.manager_id == current.id,
            Person.is_active.is_(True),
        )
    ).scalars().first()
    if ea is None:
        return {"assistant": None}
    return {"assistant": {"external_id": ea.external_id, "display_name": ea.display_name}}



# ── Employee settings / permissions ──────────────────────────────────────────
def _settings_out(db: Session, person: Person) -> EmployeeSettingsOut:
    station = db.get(Station, person.home_station_id) if person.home_station_id else None
    dept = db.get(Department, person.department_id) if person.department_id else None
    manager = db.get(Person, person.manager_id) if person.manager_id else None
    return EmployeeSettingsOut(
        external_id=person.external_id,
        display_name=person.display_name,
        phone=person.phone,
        email=person.email,
        blood_group=person.blood_group,
        role=person.role,
        department_id=person.department_id,
        department_name=dept.name if dept else None,
        manager_id=person.manager_id,
        manager_name=manager.display_name if manager else None,
        home_station_id=person.home_station_id,
        home_station_name=station.name if station else None,
        field_scan_enabled=bool(person.field_scan_enabled),
    )


@router.get("/supervisors", response_model=list[SupervisorOut])
def list_supervisors(
    _: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """All supervisors (for assigning a manager during onboarding / settings)."""
    rows = db.execute(
        select(Person).where(Person.role == "supervisor").order_by(Person.display_name)
    ).scalars().all()
    return [SupervisorOut(id=p.id, external_id=p.external_id, display_name=p.display_name,
                          department_id=p.department_id) for p in rows]


@router.get("/employees/{external_id}/settings", response_model=EmployeeSettingsOut)
def get_employee_settings(
    external_id: str,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    person = db.execute(
        select(Person).where(Person.external_id == external_id)
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    _assert_same_department(current, person)
    return _settings_out(db, person)


@router.patch("/employees/{external_id}/settings", response_model=EmployeeSettingsOut)
def update_employee_settings(
    external_id: str,
    body: EmployeeSettingsUpdate,
    current: Person = Depends(require_supervisor),
    db: Session = Depends(get_db),
):
    """Edit any of an employee's onboarding details / permissions."""
    person = db.execute(
        select(Person).where(Person.external_id == external_id)
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    _assert_same_department(current, person)

    if body.role is not None:
        if body.role not in ("employee", "supervisor"):
            raise HTTPException(status_code=400, detail="Invalid role")
        person.role = body.role
    if body.department_id is not None:
        if db.get(Department, body.department_id) is None:
            raise HTTPException(status_code=400, detail="Department not found")
        person.department_id = body.department_id
    if body.manager_id is not None:
        mgr = db.get(Person, body.manager_id)
        if mgr is None or mgr.role != "supervisor":
            raise HTTPException(status_code=400, detail="Manager must be a supervisor")
        person.manager_id = body.manager_id
    if body.display_name is not None:
        person.display_name = body.display_name
    if body.phone is not None:
        person.phone = body.phone
    if body.email is not None:
        person.email = body.email
    if body.blood_group is not None:
        person.blood_group = body.blood_group
    if body.home_station_id is not None:
        person.home_station_id = body.home_station_id
    if body.field_scan_enabled is not None:
        person.field_scan_enabled = body.field_scan_enabled
    db.commit()
    db.refresh(person)
    return _settings_out(db, person)
