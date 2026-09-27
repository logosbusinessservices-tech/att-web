"""Phase 2: supervisor corrections — the "human layer" over automatic attendance.

Design principle: APPEND-ONLY. Raw camera events are facts and are never edited
or deleted. A supervisor correction is expressed as:

  • an AttendanceOverride row — the audit trail (who/what/when/why + original vs
    new status). It may force a day's displayed status.
  • optional manual AttendanceEvent rows (source="manual") that inject a missing
    entry/exit crossing so hours-in-office and entry/exit counts recompute
    naturally through the normal aggregation.

"Latest override wins": if several overrides exist for the same person+date, the
most recent one is authoritative. History is preserved either way.
"""

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AttendanceEvent, AttendanceOverride, Person
from app.services import attendance_service as svc

_TZ = ZoneInfo(settings.display_timezone)


def _parse_hhmm(hhmm: str) -> tuple[int, int]:
    """Parse an IST wall-clock 'HH:MM' string into (hour, minute)."""
    try:
        h, m = hhmm.strip().split(":")
        hh, mm = int(h), int(m)
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise ValueError
        return hh, mm
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid time '{hhmm}', expected HH:MM (IST)") from exc


def _to_naive_utc(for_date: date, hh: int, mm: int) -> datetime:
    """IST wall-clock time on `for_date` -> naive-UTC datetime (pipeline storage form)."""
    local = datetime.combine(for_date, time(hh, mm), tzinfo=_TZ)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def latest_overrides(
    db: Session, person_id: int, from_date: date, to_date: date
) -> dict[str, dict]:
    """Return {iso_date: {"new_status", "reason"}} — latest override per date in range."""
    rows = (
        db.execute(
            select(AttendanceOverride)
            .where(AttendanceOverride.person_id == person_id)
            .order_by(AttendanceOverride.created_at)
        )
        .scalars()
        .all()
    )
    lo, hi = from_date.isoformat(), to_date.isoformat()
    result: dict[str, dict] = {}
    for o in rows:
        if o.for_date and lo <= o.for_date <= hi:
            result[o.for_date] = {"new_status": o.new_status, "reason": o.reason}
    return result  # later rows overwrite earlier -> latest wins


def _make_manual(
    person_id: int, for_date: date, direction: str, hhmm: str, replaces: int | None
) -> AttendanceEvent:
    hh, mm = _parse_hhmm(hhmm)
    return AttendanceEvent(
        person_id=person_id,
        is_visitor=False,
        camera_label=f"manual-{direction}",
        direction=direction,
        source="manual",
        event_time=_to_naive_utc(for_date, hh, mm),
        replaces_event_id=replaces,
    )


def _build_and_validate(
    db: Session,
    person: Person,
    for_date: date,
    *,
    target_kind: str,
    disputed_event_id: int | None,
    entry_time: str | None,
    exit_time: str | None,
) -> list[AttendanceEvent]:
    """Construct the proposed manual events and reject if they break the day's
    entry/exit sequence (e.g. adding an entry while the employee is already inside).
    Returns the new (not-yet-added) manual events on success.
    """
    all_events = (
        db.execute(select(AttendanceEvent).where(AttendanceEvent.person_id == person.id))
        .scalars()
        .all()
    )
    effective = svc._effective_events(all_events)
    day_events = [e for e in effective if svc._to_local(e.event_time).date() == for_date]

    # Baseline anomalies ALREADY on this day, before we touch anything. A dispute
    # is often raised precisely because the day is messy (e.g. a camera missed a
    # crossing, leaving two entries in a row). We must not block a correction just
    # because such a pre-existing anomaly still lingers — only if THIS edit makes
    # the day *worse* by introducing a new conflict.
    baseline = svc.detect_anomalies(sorted(day_events, key=lambda e: e.event_time))

    manuals: list[AttendanceEvent] = []
    if target_kind == "entry":
        manuals.append(_make_manual(person.id, for_date, "entry", entry_time, disputed_event_id))
    elif target_kind == "exit":
        manuals.append(_make_manual(person.id, for_date, "exit", exit_time, disputed_event_id))
    else:  # day
        if entry_time:
            manuals.append(_make_manual(person.id, for_date, "entry", entry_time, None))
        if exit_time:
            manuals.append(_make_manual(person.id, for_date, "exit", exit_time, None))

    # Editing a specific crossing REPLACES it (append-only: the manual event
    # supersedes the disputed one). So the disputed record is removed from the
    # candidate day and the corrected time takes its place.
    replaced = {m.replaces_event_id for m in manuals if m.replaces_event_id is not None}
    candidate = [e for e in day_events if e.id not in replaced] + manuals
    candidate.sort(key=lambda e: e.event_time)

    after = svc.detect_anomalies(candidate)
    # Only reject if the correction INTRODUCES a conflict that wasn't there before
    # (e.g. moving an entry before the prior exit, so you'd be "entering while
    # already inside"). A correction that keeps or reduces the mess is allowed.
    if len(after) > len(baseline):
        introduced = _first_new_anomaly(baseline, after)
        raise ValueError(introduced["message"])
    return manuals


def _first_new_anomaly(baseline: list[dict], after: list[dict]) -> dict:
    """Return the first anomaly in `after` that isn't accounted for by `baseline`
    (matched loosely by type), for a precise, human-friendly rejection message."""
    remaining = list(baseline)
    for a in after:
        match = next((b for b in remaining if b["type"] == a["type"]), None)
        if match is None:
            return a
        remaining.remove(match)
    return after[-1]  # fallback: shouldn't happen when len(after) > len(baseline)



def apply_correction(
    db: Session,
    person: Person,
    for_date: date,
    *,
    target_kind: str = "day",
    disputed_event_id: int | None = None,
    new_status: str | None = None,
    entry_time: str | None = None,
    exit_time: str | None = None,
    reason: str | None = None,
    supervisor: Person,
) -> AttendanceOverride:
    """Create manual events (if times given) + an append-only override row.

    `target_kind` limits what may change: "entry" alters only the entry crossing,
    "exit" only the exit crossing, "day" may add both. Time changes are validated
    against the day's sequence and rejected (ValueError) if they'd be impossible.
    Caller is responsible for committing the session.
    """
    # Snapshot the status as it stands BEFORE this correction (for the audit trail).
    events_before = (
        db.execute(select(AttendanceEvent).where(AttendanceEvent.person_id == person.id))
        .scalars()
        .all()
    )
    prior = svc.summarize_person(
        events_before, for_date, for_date, latest_overrides(db, person.id, for_date, for_date)
    )[0]
    original_status = prior["status"]

    if entry_time or exit_time:
        manuals = _build_and_validate(
            db, person, for_date,
            target_kind=target_kind,
            disputed_event_id=disputed_event_id,
            entry_time=entry_time,
            exit_time=exit_time,
        )
        for m in manuals:
            db.add(m)
        db.flush()

    # If the supervisor didn't force a status, recompute it WITH the new manual
    # events (e.g. adding a 09:15 entry to an absent day makes it "present").
    if new_status:
        final_status = new_status
    else:
        events_after = (
            db.execute(select(AttendanceEvent).where(AttendanceEvent.person_id == person.id))
            .scalars()
            .all()
        )
        final_status = svc.summarize_person(events_after, for_date, for_date, None)[0]["status"]

    override = AttendanceOverride(
        event_id=disputed_event_id,
        person_id=person.id,
        for_date=for_date.isoformat(),
        original_status=original_status,
        new_status=final_status,
        reason=reason,
        overridden_by=supervisor.id,
    )
    db.add(override)
    db.flush()
    return override


# ── Granular per-crossing edits (edit time / delete / add) ───────────────────
def _hhmm(event: AttendanceEvent) -> str:
    return svc._to_local(event.event_time).strftime("%H:%M")


def _day_effective(db: Session, person_id: int, for_date: date) -> list[AttendanceEvent]:
    all_events = (
        db.execute(select(AttendanceEvent).where(AttendanceEvent.person_id == person_id))
        .scalars().all()
    )
    eff = svc._effective_events(all_events)
    return [e for e in eff if svc._to_local(e.event_time).date() == for_date]


def _check_no_new_conflict(day_events: list[AttendanceEvent], candidate: list[AttendanceEvent]) -> None:
    baseline = svc.detect_anomalies(sorted(day_events, key=lambda e: e.event_time))
    after = svc.detect_anomalies(sorted(candidate, key=lambda e: e.event_time))
    if len(after) > len(baseline):
        raise ValueError(_first_new_anomaly(baseline, after)["message"])


def _status_before(db: Session, person_id: int, for_date: date) -> str:
    events = db.execute(select(AttendanceEvent).where(AttendanceEvent.person_id == person_id)).scalars().all()
    return svc.summarize_person(events, for_date, for_date, None)[0]["status"]


def edit_event_time(db: Session, supervisor: Person, event: AttendanceEvent, hhmm: str) -> AttendanceEvent:
    """Change one crossing's time (append a manual event that supersedes it)."""
    for_date = svc._to_local(event.event_time).date()
    before = _status_before(db, event.person_id, for_date)
    day_events = _day_effective(db, event.person_id, for_date)
    manual = _make_manual(event.person_id, for_date, event.direction, hhmm, event.id)
    candidate = [e for e in day_events if e.id != event.id] + [manual]
    _check_no_new_conflict(day_events, candidate)
    db.add(manual)
    db.flush()
    person = db.get(Person, event.person_id)
    after = _status_before(db, event.person_id, for_date)
    db.add(AttendanceOverride(
        event_id=event.id, person_id=person.id, for_date=for_date.isoformat(),
        original_status=before, new_status=after,
        reason=f"Edited {event.direction} time to {hhmm}", overridden_by=supervisor.id,
    ))
    db.flush()
    return manual


def delete_event(db: Session, supervisor: Person, event: AttendanceEvent, reason: str | None) -> AttendanceEvent:
    """Remove one crossing (append a voided tombstone that supersedes it)."""
    for_date = svc._to_local(event.event_time).date()
    before = _status_before(db, event.person_id, for_date)
    tomb = _make_manual(event.person_id, for_date, event.direction, _hhmm(event), event.id)
    tomb.voided = True
    db.add(tomb)
    db.flush()
    after = _status_before(db, event.person_id, for_date)
    db.add(AttendanceOverride(
        event_id=event.id, person_id=event.person_id, for_date=for_date.isoformat(),
        original_status=before, new_status=after,
        reason=reason or f"Removed {event.direction} crossing", overridden_by=supervisor.id,
    ))
    db.flush()
    return tomb


def add_event(db: Session, supervisor: Person, person: Person, for_date: date,
              direction: str, hhmm: str) -> AttendanceEvent:
    """Add a new entry/exit crossing (validated against the day's sequence)."""
    if direction not in ("entry", "exit"):
        raise ValueError("direction must be 'entry' or 'exit'")
    before = _status_before(db, person.id, for_date)
    day_events = _day_effective(db, person.id, for_date)
    manual = _make_manual(person.id, for_date, direction, hhmm, None)
    _check_no_new_conflict(day_events, day_events + [manual])
    db.add(manual)
    db.flush()
    after = _status_before(db, person.id, for_date)
    db.add(AttendanceOverride(
        person_id=person.id, for_date=for_date.isoformat(),
        original_status=before, new_status=after,
        reason=f"Added {direction} at {hhmm}", overridden_by=supervisor.id,
    ))
    db.flush()
    return manual

