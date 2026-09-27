"""Auth routes: login (issue JWT) and current-user info."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, user_out
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.database import get_db
from app.db.models import Department, Person, Station
from app.schemas import (
    DepartmentOut,
    OtpRequest,
    OtpRequestAck,
    OtpVerify,
    PasswordChange,
    SignupAck,
    SignupCreate,
    SignupOptionsOut,
    SignupOtpRequest,
    StationOut,
    Token,
    UserOut,
)
from app.services import otp as otp_service
from app.services import signup as signup_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Login with external_id (employee code) as username + password.

    Returns a JWT the frontend stores and sends on every later request.
    """
    person = db.execute(
        select(Person).where(Person.external_id == form.username)
    ).scalar_one_or_none()

    if (
        person is None
        or not person.is_active
        or not person.password_hash
        or not verify_password(form.password, person.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect employee code or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(subject=str(person.id), role=person.role)
    return Token(access_token=token, role=person.role, display_name=person.display_name)


@router.get("/me", response_model=UserOut)
def me(
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return user_out(current, db)


# ── Self sign-up (public) ────────────────────────────────────────────────────
@router.get("/signup/options", response_model=SignupOptionsOut)
def signup_options(db: Session = Depends(get_db)):
    """Public department + station lists the sign-up form needs."""
    departments = db.execute(select(Department).order_by(Department.name)).scalars().all()
    stations = db.execute(select(Station).order_by(Station.name)).scalars().all()
    return SignupOptionsOut(
        departments=[DepartmentOut.model_validate(d) for d in departments],
        stations=[StationOut.model_validate(s) for s in stations],
    )


@router.post("/signup/otp", response_model=OtpRequestAck)
def signup_otp(body: SignupOtpRequest, db: Session = Depends(get_db)):
    """Send a verification code to a would-be employee's mobile."""
    try:
        result = signup_service.request_signup_otp(db, body.phone)
    except signup_service.SignupError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return OtpRequestAck(**result)


@router.post("/signup", response_model=SignupAck, status_code=status.HTTP_201_CREATED)
def signup(body: SignupCreate, db: Session = Depends(get_db)):
    """Create a pending account (awaiting supervisor approval)."""
    try:
        signup_service.create_signup(
            db,
            phone=body.phone,
            code=body.code,
            display_name=body.display_name,
            department_id=body.department_id,
            home_station_id=body.home_station_id,
            email=body.email,
            blood_group=body.blood_group,
        )
    except signup_service.SignupError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return SignupAck(
        status="pending",
        message="Sign-up received. Your supervisor will review and approve your account.",
    )


# ── OTP login (no password needed) ───────────────────────────────────────────
@router.post("/otp/request", response_model=OtpRequestAck)
def otp_request(body: OtpRequest, db: Session = Depends(get_db)):
    """Send a one-time code to the phone. Always 200 (doesn't reveal if the
    number exists), except when rate-limited."""
    try:
        result = otp_service.request_otp(db, body.phone)
    except otp_service.OtpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return OtpRequestAck(**result)


@router.post("/otp/verify", response_model=Token)
def otp_verify(body: OtpVerify, db: Session = Depends(get_db)):
    """Verify the code and issue a JWT, just like a password login."""
    try:
        person = otp_service.verify_otp(db, body.phone, body.code)
    except otp_service.OtpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    token = create_access_token(subject=str(person.id), role=person.role)
    return Token(access_token=token, role=person.role, display_name=person.display_name)


# ── Change password (old password OR mobile OTP 2FA) ─────────────────────────
@router.post("/password/otp", response_model=OtpRequestAck)
def password_change_otp(
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a 2FA code to the logged-in user's phone for a password change."""
    try:
        result = otp_service.request_password_otp(db, current)
    except otp_service.OtpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return OtpRequestAck(**result)


@router.post("/password/change", response_model=UserOut)
def password_change(
    body: PasswordChange,
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change your password by proving identity one of two ways:
      • old_password — verify your current password, or
      • otp_code — a 2FA code sent to your phone.
    """
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    if body.old_password:
        if not current.password_hash or not verify_password(body.old_password, current.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
    elif body.otp_code:
        try:
            otp_service.verify_password_otp(db, current, body.otp_code)
        except otp_service.OtpError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide your current password or a verification code",
        )

    current.password_hash = hash_password(body.new_password)
    current.must_change_password = False
    db.commit()
    db.refresh(current)
    return user_out(current, db)

