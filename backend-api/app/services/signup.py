"""Self sign-up + supervisor approval.

Flow:
  request_signup_otp(phone) -> SMS a one-time code proving the number is theirs.
  create_signup(...)        -> verify the code, then create a *pending* Person
                               (is_active False, no password, placeholder code).
  approve_signup(...)       -> a supervisor assigns the real employee code, flips
                               the account to active, sets the default password
                               (== employee code, must-change), and SMSes them.
  reject_signup(...)        -> mark rejected (kept for audit) and SMS them.

Security notes:
  • Pending accounts cannot log in — get_current_user/login both require is_active.
  • The mobile is OTP-verified before the request is created, so someone can't
    sign up with a number that isn't theirs.
  • Dedupe: a number already tied to an active or pending account is rejected.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.db.models import Department, Designation, EmploymentType, Person, Station
from app.services import otp as otp_service
from app.services.otp import normalize_phone
from app.services.sms import send_sms


class SignupError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _signup_identifier(phone: str) -> str:
    """Namespace sign-up OTP challenges so they never collide with login codes."""
    return "signup:" + normalize_phone(phone)


def _active_or_pending_with_phone(db: Session, phone: str) -> Person | None:
    target = normalize_phone(phone)
    if not target:
        return None
    for p in db.execute(
        select(Person).where(Person.phone.isnot(None), Person.status != "rejected")
    ).scalars():
        if normalize_phone(p.phone) == target:
            return p
    return None


def request_signup_otp(db: Session, phone: str) -> dict:
    """Send a verification code to a would-be employee's phone."""
    if not normalize_phone(phone):
        raise SignupError("Enter a valid mobile number.")
    if _active_or_pending_with_phone(db, phone) is not None:
        raise SignupError(
            "This number is already registered or awaiting approval.", status_code=409
        )
    try:
        code = otp_service._issue_challenge(db, _signup_identifier(phone))
    except otp_service.OtpError as exc:
        raise SignupError(exc.message, status_code=exc.status_code) from exc
    from app.config import settings

    send_sms(
        phone,
        f"Your sign-up verification code is {code}. It expires in "
        f"{settings.otp_ttl_minutes} minutes.",
    )
    out = {"sent": True, "ttl_minutes": settings.otp_ttl_minutes}
    if settings.otp_debug_return_code:
        out["debug_code"] = code  # DEV ONLY
    return out


def _resolve_choice(db: Session, model, choice_id, custom, label: str):
    """Validate an optional lookup choice and return (id, custom_to_store).

    When the chosen row is the `Other` sentinel, the typed value is required and
    preserved; otherwise any custom text is discarded so analytics stay clean.
    """
    if choice_id is None:
        return None, None
    row = db.get(model, choice_id)
    if row is None:
        raise SignupError(f"Select a valid {label}.")
    if row.is_other:
        text = (custom or "").strip()
        if not text:
            raise SignupError(f"Enter your {label}.")
        return choice_id, text
    return choice_id, None


def create_signup(
    db: Session,
    *,
    phone: str,
    display_name: str,
    department_id: int,
    department_custom: str | None = None,
    designation_id: int | None = None,
    designation_custom: str | None = None,
    employment_type_id: int | None = None,
    employment_type_custom: str | None = None,
    date_of_birth=None,
    home_station_id: int | None = None,
    email: str | None = None,
    blood_group: str | None = None,
) -> Person:
    """Create a pending account for Executive-Assistant approval (no OTP)."""
    if not (display_name or "").strip():
        raise SignupError("Enter your full name.")
    if not normalize_phone(phone):
        raise SignupError("Enter a valid mobile number.")

    dept = db.get(Department, department_id)
    if dept is None:
        raise SignupError("Select a valid department.")
    dept_custom = None
    if dept.is_other:
        dept_custom = (department_custom or "").strip()
        if not dept_custom:
            raise SignupError("Enter your department.")

    desig_id, desig_custom = _resolve_choice(
        db, Designation, designation_id, designation_custom, "designation"
    )
    emp_id, emp_custom = _resolve_choice(
        db, EmploymentType, employment_type_id, employment_type_custom, "employment type"
    )

    if home_station_id is not None and db.get(Station, home_station_id) is None:
        raise SignupError("Select a valid home station.")

    # Without OTP, the human EA review is the gate; still block obvious dupes.
    if _active_or_pending_with_phone(db, phone) is not None:
        raise SignupError(
            "This number is already registered or awaiting approval.", status_code=409
        )

    person = Person(
        # Placeholder until the EA assigns the real employee code at approval.
        external_id=f"SIGNUP-{uuid.uuid4().hex[:12]}",
        display_name=display_name.strip(),
        role="employee",
        status="pending",
        is_active=False,
        department_id=department_id,
        department_custom=dept_custom,
        designation_id=desig_id,
        designation_custom=desig_custom,
        employment_type_id=emp_id,
        employment_type_custom=emp_custom,
        date_of_birth=date_of_birth,
        home_station_id=home_station_id,
        phone=phone,
        email=email or None,
        blood_group=blood_group or None,
    )
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def approve_signup(
    db: Session,
    *,
    approver: Person,
    signup: Person,
    external_id: str,
    manager_id: int | None = None,
    home_station_id: int | None = None,
    field_scan_enabled: bool = False,
) -> Person:
    """Assign the employee code, activate the account, and notify the employee.

    `approver` is whoever handled the onboarding (a supervisor, or the EA). The
    new hire's manager defaults to the approver only when that approver is a
    supervisor; an EA-approved hire is left unassigned for later settings edits.
    """
    from datetime import datetime, timezone

    if signup.status != "pending":
        raise SignupError("This sign-up has already been handled.", status_code=409)

    code = (external_id or "").strip()
    if not code:
        raise SignupError("Assign an employee code.")
    clash = db.execute(
        select(Person).where(Person.external_id == code, Person.id != signup.id)
    ).scalar_one_or_none()
    if clash is not None:
        raise SignupError("Employee code already in use.", status_code=409)

    if manager_id is None and approver.role == "supervisor":
        manager_id = approver.id
    manager = db.get(Person, manager_id) if manager_id else None
    if manager is not None and manager.role != "supervisor":
        raise SignupError("Assigned manager must be a supervisor.")

    if home_station_id is not None:
        if db.get(Station, home_station_id) is None:
            raise SignupError("Select a valid home station.")
        signup.home_station_id = home_station_id

    signup.external_id = code
    signup.status = "active"
    signup.is_active = True
    signup.manager_id = manager_id
    signup.field_scan_enabled = bool(field_scan_enabled)
    signup.password_hash = hash_password(code)
    signup.must_change_password = True
    signup.activated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(signup)

    if signup.phone:
        send_sms(
            signup.phone,
            f"Your attendance account is approved. Sign in with employee code "
            f"{code} and password {code}, then change your password.",
        )
    return signup


def reject_signup(
    db: Session, *, signup: Person, reason: str | None = None
) -> Person:
    """Mark a sign-up rejected (kept for audit) and notify the applicant."""
    if signup.status != "pending":
        raise SignupError("This sign-up has already been handled.", status_code=409)
    signup.status = "rejected"
    signup.is_active = False
    db.commit()
    db.refresh(signup)
    if signup.phone:
        tail = f" Reason: {reason.strip()}" if (reason or "").strip() else ""
        send_sms(signup.phone, f"Your attendance sign-up was not approved.{tail}")
    return signup
