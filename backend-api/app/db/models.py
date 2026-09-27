"""SQLAlchemy models.

These EXTEND the pipeline's existing tables (persons, face_embeddings,
attendance_events) with the web columns, and ADD the website-only tables
(departments, stations, attendance_overrides, disputes, leave_requests).

Nothing here mutates pipeline data destructively: overrides are append-only and
the raw attendance_events row is never edited.

Storage note: face embeddings are stored as raw float32 bytes (LargeBinary),
identical to the pipeline's SQLite BLOB format, so cosine matching is a plain
dot product of L2-normalized vectors. pgvector is a targeted prod optimization.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Departments & Stations (new) ─────────────────────────────────────────────
class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    persons: Mapped[list["Person"]] = relationship(back_populates="department")


class Station(Base):
    """A railway station with its own geofence (per-station radius)."""

    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # Center-point + radius geofence for v1 (Haversine). Polygon/PostGIS later.
    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lon: Mapped[float] = mapped_column(Float, nullable=False)
    radius_m: Mapped[float] = mapped_column(Float, nullable=False, default=200.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    persons: Mapped[list["Person"]] = relationship(back_populates="home_station")


# ── Persons (extends pipeline table) ─────────────────────────────────────────
class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # ── Website extensions ──
    # Lifecycle: a self-signup starts 'pending' (is_active False, can't log in);
    # a supervisor approval flips it to 'active', a rejection to 'rejected'.
    # Seeded/supervisor-created accounts default to 'active'.
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")  # pending|active|rejected
    # When the account was approved/activated. Reminders (password, attendance
    # photos) count from here, since created_at is when they first signed up.
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Cosmetic profile photo (NOT the biometric face template). Defaults to a
    # supervisor-taken shot; the employee may replace it with their own.
    avatar_path: Mapped[str | None] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, nullable=False, default="employee")  # employee | supervisor
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    home_station_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id"))
    # The supervisor who manages this person (assigned at onboarding or later).
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"))
    email: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    blood_group: Mapped[str | None] = mapped_column(String)
    password_hash: Mapped[str | None] = mapped_column(String)
    # True right after onboarding (default password == employee code). The UI
    # nags them to set a real password; supervisors are notified if they don't.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Permission: may this person mark field attendance (face + GPS)? Off by
    # default; a supervisor grants it at onboarding or later.
    field_scan_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    department: Mapped["Department | None"] = relationship(back_populates="persons")
    home_station: Mapped["Station | None"] = relationship(back_populates="persons")
    embeddings: Mapped[list["FaceEmbedding"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )


# ── Face embeddings (pipeline table) ─────────────────────────────────────────
class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    # 512 x float32, L2-normalized — raw bytes, same as the pipeline's BLOB.
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    num_photos: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Bumped on every (re)enrollment so the edge can pull only what changed.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    person: Mapped["Person"] = relationship(back_populates="embeddings")


# ── Attendance events (extends pipeline table) ───────────────────────────────
class AttendanceEvent(Base):
    __tablename__ = "attendance_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id", ondelete="SET NULL"))
    is_visitor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    similarity: Mapped[float | None] = mapped_column(Float)
    camera_label: Mapped[str] = mapped_column(String, nullable=False)
    track_id: Mapped[int | None] = mapped_column(Integer)
    crop_path: Mapped[str | None] = mapped_column(String)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # ── Website extensions ──
    source: Mapped[str] = mapped_column(String, nullable=False, default="camera")  # camera | field | manual
    # Relayed from the edge (or derived from camera_label): entry | exit | None.
    # Drives hours-in-office and entry/exit counts.
    direction: Mapped[str | None] = mapped_column(String)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location_verified: Mapped[bool | None] = mapped_column(Boolean)
    # Field-attendance review workflow. Camera/manual events are 'approved';
    # a field scan is 'approved' when inside a station geofence with good GPS,
    # else 'pending' (uncertain location) awaiting supervisor decision.
    review_status: Mapped[str] = mapped_column(String, nullable=False, default="approved")  # approved|pending|rejected
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)          # to nearest station
    nearest_station_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id"))
    selfie_path: Mapped[str | None] = mapped_column(String)          # audit copy (purged after N days)
    # When a supervisor corrects a specific crossing, we DON'T edit the original:
    # we append a manual event that supersedes it. This points at the original id.
    replaces_event_id: Mapped[int | None] = mapped_column(ForeignKey("attendance_events.id"))
    # A voided manual event is a tombstone: it supersedes the crossing it replaces
    # and is itself excluded (an audit-friendly delete).
    voided: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# ── Attendance overrides (new, append-only audit trail) ──────────────────────
class AttendanceOverride(Base):
    """Never edits an event. A supervisor's correction is a new linked row.

    Effective status = latest override for the event if any, else the raw event.
    """

    __tablename__ = "attendance_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("attendance_events.id"))
    # Fallback keying when there is no single event (e.g. marking a whole day).
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"))
    for_date: Mapped[str | None] = mapped_column(String)  # ISO date the correction applies to
    original_status: Mapped[str | None] = mapped_column(String)
    new_status: Mapped[str] = mapped_column(String, nullable=False)  # present | absent | late
    reason: Mapped[str | None] = mapped_column(Text)
    overridden_by: Mapped[int] = mapped_column(ForeignKey("persons.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Disputes (new, workflow) ─────────────────────────────────────────────────
class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("attendance_events.id"))
    # What the employee is contesting: a specific entry crossing, a specific exit
    # crossing, or a whole (usually absent) day.
    target_kind: Mapped[str] = mapped_column(String, nullable=False, default="day")  # entry|exit|day
    for_date: Mapped[str | None] = mapped_column(String)
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")  # open|under_review|resolved|rejected
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("persons.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# ── Leave requests (new, Phase 4 — table created now) ────────────────────────
class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), nullable=False)
    start_date: Mapped[str] = mapped_column(String, nullable=False)
    end_date: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")  # pending|approved|rejected
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("persons.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── OTP login challenges (new) ───────────────────────────────────────
class OtpChallenge(Base):
    """A short-lived one-time code sent to a phone. The code itself is stored
    HASHED (never plaintext), like a password.
    """

    __tablename__ = "otp_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String, nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Delegated tasks (supervisor → their Executive Assistant) ─────────────────
class DelegatedTask(Base):
    """A unit of work a supervisor hands to their EA.

    Two kinds:
      • field_approval  — decide one pending field scan (keyed by event_id).
      • attendance_edit — fix one employee's day (keyed by person_id + for_date).
    A field-approval task also completes implicitly when its event leaves the
    'pending' review state; an attendance-edit task is closed by an explicit
    "Mark complete" once the EA is done adjusting the day.
    """

    __tablename__ = "delegated_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_type: Mapped[str] = mapped_column(String, nullable=False)  # field_approval | attendance_edit
    supervisor_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), nullable=False)
    assistant_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")  # open|completed|recalled
    comment: Mapped[str | None] = mapped_column(Text)  # optional (field) / required (attendance_edit)
    # field_approval keying:
    event_id: Mapped[int | None] = mapped_column(ForeignKey("attendance_events.id"))
    # attendance_edit keying:
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id"))
    for_date: Mapped[str | None] = mapped_column(String)  # ISO date
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("persons.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Notifications (per-recipient inbox) ──────────────────────────────────────
class Notification(Base):
    """A stored alert delivered to one person (employee, EA, etc.).

    Used for field-attendance updates: a scan that needs approval (pending),
    and its later approval/rejection. Kept append-only; `is_read` toggles.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False)  # field_pending|field_approved|field_rejected
    message: Mapped[str] = mapped_column(Text, nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("attendance_events.id"))
    for_date: Mapped[str | None] = mapped_column(String)  # ISO date the scan is for
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
