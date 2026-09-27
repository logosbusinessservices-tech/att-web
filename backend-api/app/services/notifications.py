"""Per-recipient notifications for field-attendance updates.

A field scan that can't be auto-approved is sent for review; we alert the
employee (and their supervisor's Executive Assistant) that it's pending, and
again when it's approved or rejected. Auto-approved scans generate nothing.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AttendanceEvent, Notification, Person
from app.services import attendance_service as svc


def _assistant_for(db: Session, employee: Person) -> Person | None:
    """The EA of the employee's supervisor (their manager), if any."""
    if employee.manager_id is None:
        return None
    return db.execute(
        select(Person).where(
            Person.role == "assistant",
            Person.manager_id == employee.manager_id,
            Person.is_active.is_(True),
        )
    ).scalars().first()


def _recipients(db: Session, employee: Person) -> list[int]:
    ids = [employee.id]
    ea = _assistant_for(db, employee)
    if ea is not None and ea.id != employee.id:
        ids.append(ea.id)
    return ids


def _emit(db: Session, employee: Person, ev: AttendanceEvent, ntype: str, message: str) -> None:
    for_date = svc._to_local(ev.event_time).date().isoformat()
    for pid in _recipients(db, employee):
        # The EA sees whose scan it is; the employee sees it as their own.
        msg = message if pid == employee.id else f"{employee.display_name}: {message}"
        db.add(Notification(
            person_id=pid, type=ntype, message=msg, event_id=ev.id, for_date=for_date,
        ))


def notify_field_pending(db: Session, employee: Person, ev: AttendanceEvent) -> None:
    verb = "check-in" if ev.direction == "entry" else "check-out"
    _emit(db, employee, ev, "field_pending",
          f"Your field {verb} on {svc._to_local(ev.event_time).date().isoformat()} "
          "was sent for approval.")


def notify_field_decision(db: Session, employee: Person, ev: AttendanceEvent, approved: bool) -> None:
    verb = "check-in" if ev.direction == "entry" else "check-out"
    day = svc._to_local(ev.event_time).date().isoformat()
    if approved:
        _emit(db, employee, ev, "field_approved",
              f"Your field {verb} on {day} was approved.")
    else:
        _emit(db, employee, ev, "field_rejected",
              f"Your field {verb} on {day} was rejected.")
