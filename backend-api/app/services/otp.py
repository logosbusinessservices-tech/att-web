"""One-time-password (OTP) login.

Flow:
  request(phone)  -> find the person by phone, generate a 6-digit code, store it
                     HASHED with a short expiry, and SMS it to them.
  verify(phone,c) -> check the newest unconsumed code: not expired, attempts left,
                     matches -> consume it and hand back the Person to log in.

Security notes:
  • The code is hashed (bcrypt) at rest — a DB leak never reveals live codes.
  • Attempts are capped, codes expire fast, and requests are rate-limited, so
    brute-forcing a 6-digit code in the window is infeasible.
  • Phone lookup is normalized (digits only) so "+91 90000 00001" == "9000000001".
"""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password, verify_password
from app.config import settings
from app.db.models import OtpChallenge, Person
from app.services.sms import send_sms


class OtpError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def normalize_phone(phone: str) -> str:
    """Keep only digits; drop a leading country code's formatting.

    We match on the last 10 digits so local and +91-prefixed forms unify.
    """
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _find_person_by_phone(db: Session, phone: str) -> Person | None:
    target = normalize_phone(phone)
    if not target:
        return None
    # Small user base: normalize in Python to avoid DB-specific string funcs.
    for p in db.execute(select(Person).where(Person.phone.isnot(None))).scalars():
        if normalize_phone(p.phone) == target:
            return p
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _issue_challenge(db: Session, identifier: str) -> str:
    """Create a hashed OTP challenge for any identifier (phone digits or email:...).

    Enforces the resend cooldown. Returns the plaintext code (to be delivered).
    """
    recent = db.execute(
        select(OtpChallenge)
        .where(OtpChallenge.phone == identifier)
        .order_by(OtpChallenge.created_at.desc())
    ).scalars().first()
    if recent is not None:
        age = (_now() - _aware(recent.created_at)).total_seconds()
        if age < settings.otp_resend_cooldown_s:
            raise OtpError(
                f"Please wait {int(settings.otp_resend_cooldown_s - age)}s before requesting another code.",
                status_code=429,
            )
    code = "".join(secrets.choice("0123456789") for _ in range(settings.otp_length))
    db.add(OtpChallenge(
        phone=identifier,
        code_hash=hash_password(code),
        expires_at=_now() + timedelta(minutes=settings.otp_ttl_minutes),
    ))
    db.commit()
    return code


def _consume_challenge(db: Session, identifier: str, code: str) -> None:
    """Validate + consume the newest live challenge for `identifier` or raise."""
    challenge = db.execute(
        select(OtpChallenge)
        .where(OtpChallenge.phone == identifier, OtpChallenge.consumed.is_(False))
        .order_by(OtpChallenge.created_at.desc())
    ).scalars().first()

    if challenge is None:
        raise OtpError("No active code. Please request a new one.")
    if _aware(challenge.expires_at) < _now():
        raise OtpError("Code expired. Please request a new one.")
    if challenge.attempts >= settings.otp_max_attempts:
        challenge.consumed = True
        db.commit()
        raise OtpError("Too many attempts. Please request a new code.", status_code=429)

    challenge.attempts += 1
    if not verify_password(code, challenge.code_hash):
        db.commit()
        left = settings.otp_max_attempts - challenge.attempts
        raise OtpError(f"Incorrect code. {max(left, 0)} attempt(s) left.")

    challenge.consumed = True
    db.commit()


def request_otp(db: Session, phone: str) -> dict:
    """Create + send a login OTP. Returns a small dict (may include the code in dev)."""
    person = _find_person_by_phone(db, phone)
    # Anti-enumeration: we behave the same whether or not the number exists, but
    # only actually create/send a code for a known, active person.
    if person is not None and person.is_active:
        code = _issue_challenge(db, normalize_phone(phone))
        send_sms(person.phone, f"Your attendance login code is {code}. It expires in "
                               f"{settings.otp_ttl_minutes} minutes.")
        out = {"sent": True, "ttl_minutes": settings.otp_ttl_minutes}
        if settings.otp_debug_return_code:
            out["debug_code"] = code  # DEV ONLY
        return out

    return {"sent": True, "ttl_minutes": settings.otp_ttl_minutes}


def request_password_otp(db: Session, person: Person) -> dict:
    """Send a 2FA code to the logged-in user's phone for a password change.
    Returns an ack dict (may include the code in dev)."""
    if not person.phone:
        raise OtpError("No phone on file for your account.", status_code=400)
    code = _issue_challenge(db, normalize_phone(person.phone))
    send_sms(person.phone, f"Your password-change code is {code}. It expires in "
                           f"{settings.otp_ttl_minutes} minutes.")
    out = {"sent": True, "ttl_minutes": settings.otp_ttl_minutes}
    if settings.otp_debug_return_code:
        out["debug_code"] = code  # DEV ONLY
    return out


def verify_password_otp(db: Session, person: Person, code: str) -> None:
    """Validate a password-change 2FA code (sent to the user's phone)."""
    identifier = normalize_phone(person.phone or "")
    if not identifier:
        raise OtpError("No phone on file for your account.", status_code=400)
    _consume_challenge(db, identifier, code)


def verify_otp(db: Session, phone: str, code: str) -> Person:
    """Validate a login code and return the Person on success (else raise)."""
    _consume_challenge(db, normalize_phone(phone), code)
    person = _find_person_by_phone(db, phone)
    if person is None or not person.is_active:
        raise OtpError("Account not found.", status_code=404)
    return person




def _aware(dt: datetime) -> datetime:
    """SQLite may return naive datetimes; treat those as UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
