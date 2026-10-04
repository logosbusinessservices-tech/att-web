"""Pydantic request/response schemas (the API's data contract)."""

from datetime import date, datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, BaseModel


def _ensure_utc(dt: datetime) -> datetime:
    """Attendance times are stored as *naive UTC* (pipeline format). Tag them as
    UTC on the way out so the JSON carries a timezone offset (…+00:00). Without
    this, the browser's `new Date("…T03:45:00")` treats the bare string as LOCAL
    time and renders every crossing ~5.5h off in IST."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# A datetime that always serializes with a UTC offset.
UtcDatetime = Annotated[datetime, AfterValidator(_ensure_utc)]



# ── Auth ─────────────────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    display_name: str


class UserOut(BaseModel):
    id: int
    external_id: str
    display_name: str
    role: str
    department_id: int | None = None
    department_name: str | None = None
    home_station_id: int | None = None
    home_station_name: str | None = None
    email: str | None = None
    phone: str | None = None
    blood_group: str | None = None
    must_change_password: bool = False
    field_scan_enabled: bool = False
    # Cosmetic profile photo URL (None until one is set).
    avatar_url: str | None = None
    # True once the supervisor has enrolled the person's attendance photos.
    has_face_enrolled: bool = True
    # True while an active employee still has no attendance photos (drives the
    # employee ribbon nag and the enrollment deadline).
    needs_attendance_photos: bool = False

    class Config:
        from_attributes = True


# ── Attendance ───────────────────────────────────────────────────────────────
class AttendanceEventOut(BaseModel):
    id: int
    person_id: int | None
    is_visitor: bool
    similarity: float | None
    camera_label: str
    source: str
    direction: str | None
    latitude: float | None
    longitude: float | None
    location_verified: bool | None
    review_status: str = "approved"
    gps_accuracy_m: float | None = None
    distance_m: float | None = None
    event_time: UtcDatetime

    class Config:
        from_attributes = True


# ── Day summary / stats (Phase 1 aggregation) ────────────────────────────────
class AnomalyOut(BaseModel):
    type: str                       # missing_exit | missing_entry | unclosed_entry
    at: UtcDatetime | None = None
    message: str


class DaySummary(BaseModel):
    date: str                       # ISO date in IST, e.g. "2026-09-14"
    weekday: str                    # mon..sun
    is_working_day: bool
    status: str                     # present | absent | weekend
    first_seen: UtcDatetime | None     # UTC; frontend renders IST
    last_seen: UtcDatetime | None
    hours_in_office: float          # sum of entry->exit intervals, hours
    entry_count: int
    exit_count: int
    sources: list[str]              # e.g. ["camera"], ["field"], ["camera","field"]
    event_count: int
    adjusted: bool = False          # supervisor correction applied (Phase 2)
    adjustment_reason: str | None = None
    events: list[AttendanceEventOut] = []   # crossings behind the day (inline)
    has_anomaly: bool = False
    anomalies: list[AnomalyOut] = []


class PersonDaySummary(DaySummary):
    """A day summary tagged with the person (for supervisor views)."""
    person_id: int
    external_id: str
    display_name: str
    department_id: int | None = None


class AttendanceStats(BaseModel):
    from_date: str
    to_date: str
    present: int
    absent: int
    working_days: int
    attendance_pct: float
    total_hours: float


class PersonRollup(BaseModel):
    """Per-employee rollup over a date range, for supervisor overview tables."""
    person_id: int
    external_id: str
    display_name: str
    department_id: int | None = None
    department_name: str | None = None
    present: int
    absent: int
    attendance_pct: float
    total_hours: float


class DepartmentOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class StationOut(BaseModel):
    id: int
    name: str
    center_lat: float
    center_lon: float
    radius_m: float

    class Config:
        from_attributes = True


class DesignationOut(BaseModel):
    id: int
    name: str
    is_other: bool = False

    class Config:
        from_attributes = True


class EmploymentTypeOut(BaseModel):
    id: int
    name: str
    is_other: bool = False

    class Config:
        from_attributes = True


# ── Analytics (supervisor dashboards) ────────────────────────────────────────
class AnalyticsSummary(BaseModel):
    present: int
    absent: int
    total_hours: float
    attendance_pct: float
    active_employees: int
    pending_field_approvals: int


class TrendPoint(BaseModel):
    period: str
    present: int
    absent: int
    hours: float
    attendance_pct: float


class DeptStat(BaseModel):
    department_id: int | None = None
    name: str
    present: int
    absent: int
    total_hours: float
    attendance_pct: float
    headcount: int


class DimensionStat(BaseModel):
    """Attendance rollup grouped by a profile attribute (designation / employment
    type). Custom 'Other' entries roll up under the single 'Other' bucket."""
    key: str
    present: int
    absent: int
    total_hours: float
    attendance_pct: float
    headcount: int


class SourceSplit(BaseModel):
    camera: int
    field: int
    manual: int


class LowAttendanceRow(BaseModel):
    external_id: str
    display_name: str
    attendance_pct: float
    present: int
    absent: int


# ── Edge event ingestion (POST /events) ──────────────────────────────────────
class EdgeEventIn(BaseModel):
    external_id: str | None = None   # employee code (None => visitor)
    is_visitor: bool = False
    similarity: float | None = None
    camera_label: str
    direction: str | None = None     # entry | exit; falls back to CAMERA_DIRECTIONS
    track_id: int | None = None
    event_time: datetime | None = None  # UTC; server fills if omitted


class EventAck(BaseModel):
    id: int
    status: str = "stored"


# ── Disputes & overrides (Phase 2) ───────────────────────────────────────────
class DisputeCreate(BaseModel):
    for_date: date
    message: str | None = None
    target_kind: str = "day"          # entry | exit | day
    event_id: int | None = None       # required when target_kind is entry/exit


class DisputeOut(BaseModel):
    id: int
    person_id: int
    external_id: str | None = None
    display_name: str | None = None
    for_date: str | None = None
    target_kind: str = "day"
    event_id: int | None = None
    message: str | None = None
    status: str                       # open | resolved | rejected
    resolution_note: str | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class DisputeResolve(BaseModel):
    """Approve a dispute: optionally force a status and/or inject corrected times."""
    new_status: str | None = None     # present | late | absent
    entry_time: str | None = None     # 'HH:MM' IST — injects a manual entry crossing
    exit_time: str | None = None      # 'HH:MM' IST — injects a manual exit crossing
    reason: str | None = None


class DisputeUpdate(BaseModel):
    """Employee edits the explanation on their own still-open dispute."""
    message: str | None = None


class DisputeReject(BaseModel):
    resolution_note: str | None = None


class OverrideCreate(BaseModel):
    """Direct supervisor correction (no dispute required)."""
    external_id: str
    for_date: date
    new_status: str | None = None
    entry_time: str | None = None
    exit_time: str | None = None
    reason: str | None = None


class OverrideOut(BaseModel):
    ok: bool = True
    for_date: str | None = None
    original_status: str | None = None
    new_status: str | None = None


# ── Granular crossing edits (supervisor) ─────────────────────────────────────
class EventEdit(BaseModel):
    time: str                        # 'HH:MM' IST — new time for this crossing


class EventAdd(BaseModel):
    external_id: str
    for_date: date
    direction: str                   # entry | exit
    time: str                        # 'HH:MM' IST


class AnomalyDayOut(BaseModel):
    external_id: str
    display_name: str
    date: str
    anomalies: list[AnomalyOut]


# ── OTP login ────────────────────────────────────────────────────────────────
class OtpRequest(BaseModel):
    phone: str


class OtpRequestAck(BaseModel):
    sent: bool = True
    ttl_minutes: int
    channel: str | None = None       # sms | email (for password-change 2FA)
    debug_code: str | None = None    # DEV ONLY (OTP_DEBUG_RETURN_CODE)


class OtpVerify(BaseModel):
    phone: str
    code: str


# ── Change password (old password OR email/mobile OTP) ───────────────────────
class PasswordChange(BaseModel):
    new_password: str
    old_password: str | None = None  # path 1: verify current password
    otp_code: str | None = None      # path 2: 2FA code sent to phone


# ── Employee self-service profile edits ──────────────────────────────────────
class EmployeeProfileUpdate(BaseModel):
    email: str | None = None
    phone: str | None = None
    blood_group: str | None = None


# ── Supervisor notifications ─────────────────────────────────────────────────
class NotificationOut(BaseModel):
    type: str                        # password_reminder | camera_error
    severity: str = "info"           # info | warning
    external_id: str
    display_name: str
    date: str | None = None
    message: str


# ── Onboarding / enrollment (supervisor) ─────────────────────────────────────
class EmployeeCreate(BaseModel):
    external_id: str
    display_name: str
    phone: str | None = None
    email: str | None = None
    blood_group: str | None = None
    department_id: int | None = None    # defaults to the supervisor's department
    manager_id: int | None = None       # supervisor who manages them
    home_station_id: int | None = None
    role: str = "employee"          # employee | supervisor
    field_scan_enabled: bool = False


class EmployeeCreated(BaseModel):
    id: int
    external_id: str
    display_name: str
    department_id: int | None = None
    department_name: str | None = None
    role: str
    enrolled: bool = False


class EnrollResult(BaseModel):
    external_id: str
    enrolled: bool
    photos_used: int
    photos_submitted: int
    notes: list[str] = []


# ── Self sign-up (public) + supervisor approval ──────────────────────────────
class SignupOtpRequest(BaseModel):
    phone: str


class SignupCreate(BaseModel):
    phone: str
    display_name: str
    department_id: int
    department_custom: str | None = None       # required when department is "Other"
    designation_id: int | None = None
    designation_custom: str | None = None       # required when designation is "Other"
    employment_type_id: int | None = None
    employment_type_custom: str | None = None   # required when employment type is "Other"
    date_of_birth: date | None = None
    home_station_id: int | None = None
    email: str | None = None
    blood_group: str | None = None


class SignupAck(BaseModel):
    status: str                      # pending
    message: str


class SignupOptionsOut(BaseModel):
    """Public data the sign-up form needs (department + station pickers)."""
    departments: list[DepartmentOut]
    stations: list[StationOut]
    designations: list[DesignationOut]
    employment_types: list[EmploymentTypeOut]


class SignupOut(BaseModel):
    id: int
    display_name: str
    phone: str | None = None
    email: str | None = None
    blood_group: str | None = None
    department_id: int | None = None
    department_name: str | None = None
    department_custom: str | None = None
    designation_id: int | None = None
    designation_name: str | None = None
    designation_custom: str | None = None
    employment_type_id: int | None = None
    employment_type_name: str | None = None
    employment_type_custom: str | None = None
    date_of_birth: date | None = None
    home_station_id: int | None = None
    home_station_name: str | None = None
    status: str
    created_at: UtcDatetime
    # Onboarding progress: the two steps a supervisor completes per new hire.
    external_id: str | None = None   # assigned employee code (None until approved)
    is_approved: bool = False        # step 1 done (account activated)
    is_enrolled: bool = False        # step 2 done (attendance photos uploaded)
    field_scan_enabled: bool = False


class SignupApprove(BaseModel):
    external_id: str                 # supervisor assigns the employee code
    manager_id: int | None = None    # defaults to the approving supervisor
    home_station_id: int | None = None
    field_scan_enabled: bool = False


class SignupReject(BaseModel):
    reason: str | None = None


# ── Field attendance (face + GPS) ─────────────────────────────────────────
class FieldCheckInResult(BaseModel):
    event_id: int
    direction: str                   # entry | exit
    review_status: str               # approved | pending
    inside_geofence: bool
    station_name: str | None = None
    distance_m: float | None = None
    message: str
    similarity: float | None = None  # DEV ONLY (field_debug_return_similarity)
    day: DaySummary


class FieldStatusOut(BaseModel):
    """What the field-scan screen needs on open: permission + next expected action."""
    field_scan_enabled: bool
    next_direction: str              # entry | exit (server-suggested)
    open_entry: bool                 # currently checked in (has an unclosed entry today)
    home_station_id: int | None = None
    home_station_name: str | None = None


class FieldReviewItem(BaseModel):
    """A pending (uncertain-location) field scan for the supervisor to decide."""
    event_id: int
    external_id: str
    display_name: str
    for_date: str
    event_time: UtcDatetime
    direction: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    gps_accuracy_m: float | None = None
    distance_m: float | None = None
    nearest_station_name: str | None = None
    selfie_url: str | None = None
    similarity: float | None = None
    # True while this scan is delegated to the supervisor's EA (open task).
    delegated: bool = False
    delegated_task_id: int | None = None


class FieldReviewDecision(BaseModel):
    reason: str | None = None


# ── Employee settings / permissions (supervisor- & EA-managed) ────────────────
class EmployeeSettingsUpdate(BaseModel):
    display_name: str | None = None
    phone: str | None = None
    email: str | None = None
    blood_group: str | None = None
    role: str | None = None
    department_id: int | None = None
    department_custom: str | None = None
    designation_id: int | None = None
    designation_custom: str | None = None
    employment_type_id: int | None = None
    employment_type_custom: str | None = None
    date_of_birth: date | None = None
    manager_id: int | None = None
    home_station_id: int | None = None
    field_scan_enabled: bool | None = None


class EmployeeSettingsOut(BaseModel):
    external_id: str
    display_name: str
    phone: str | None = None
    email: str | None = None
    blood_group: str | None = None
    role: str
    department_id: int | None = None
    department_name: str | None = None
    department_custom: str | None = None
    designation_id: int | None = None
    designation_name: str | None = None
    designation_custom: str | None = None
    employment_type_id: int | None = None
    employment_type_name: str | None = None
    employment_type_custom: str | None = None
    date_of_birth: date | None = None
    manager_id: int | None = None
    manager_name: str | None = None
    home_station_id: int | None = None
    home_station_name: str | None = None
    field_scan_enabled: bool


class SupervisorOut(BaseModel):
    id: int
    external_id: str
    display_name: str
    department_id: int | None = None


class GalleryItem(BaseModel):
    """One enrolled face for the edge to sync into its local recognition DB."""
    external_id: str
    display_name: str
    num_photos: int
    updated_at: datetime
    embedding_b64: str              # base64 of the raw float32 512-d blob


# ── Delegation: supervisor → Executive Assistant ─────────────────────────────
class DelegateFieldRequest(BaseModel):
    """Hand one or more pending field scans to the supervisor's EA."""
    event_ids: list[int]
    comment: str | None = None       # optional note for the EA


class DelegateAttendanceRequest(BaseModel):
    """Hand a specific employee's day to the EA to fix in/out times."""
    external_id: str
    for_date: date
    comment: str                     # mandatory context for the EA


class DelegatedTaskOut(BaseModel):
    """A task in the EA's queue (either kind)."""
    id: int
    task_type: str                   # field_approval | attendance_edit
    status: str
    comment: str | None = None
    supervisor_name: str
    created_at: UtcDatetime
    # field_approval payload (mirrors FieldReviewItem when present):
    field: FieldReviewItem | None = None
    # attendance_edit payload:
    external_id: str | None = None
    display_name: str | None = None
    for_date: str | None = None
    day: DaySummary | None = None


class AssistantProfileOut(BaseModel):
    """EA's own profile plus who they assist."""
    external_id: str
    display_name: str
    supervisor_external_id: str | None = None
    supervisor_name: str | None = None


class InboxItem(BaseModel):
    """A stored notification in a person's own inbox (employee/EA)."""
    id: int
    type: str                        # field_pending | field_approved | field_rejected
    message: str
    for_date: str | None = None
    is_read: bool = False
    created_at: UtcDatetime


