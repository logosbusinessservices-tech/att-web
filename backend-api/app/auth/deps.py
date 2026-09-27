"""FastAPI auth dependencies: extract the current user from the JWT and guard roles."""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.db.database import get_db
from app.db.models import FaceEmbedding, Person

# tokenUrl is where the interactive docs send the login form.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Person:
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    person = db.get(Person, int(payload["sub"]))
    if person is None or not person.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return person


def require_supervisor(current: Person = Depends(get_current_user)) -> Person:
    # The chief manager has supervisor-level access across all departments.
    if current.role not in ("supervisor", "chief"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Supervisor role required"
        )
    return current


def require_assistant(current: Person = Depends(get_current_user)) -> Person:
    if current.role != "assistant":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Executive Assistant role required"
        )
    return current


def user_out(person: Person, db: Session | None = None) -> dict:
    """Build the profile payload with resolved department/station names.

    When `db` is provided, also reports whether the person's attendance photos
    are enrolled (drives the employee "upload your photos" nag + avatar URL)."""
    has_face_enrolled = True
    if db is not None:
        has_face_enrolled = db.execute(
            select(FaceEmbedding.id).where(FaceEmbedding.person_id == person.id)
        ).first() is not None
    needs_attendance_photos = (
        db is not None
        and person.role == "employee"
        and bool(person.is_active)
        and not has_face_enrolled
    )
    # Resolve the person's manager (e.g. an EA's supervisor) for their profile.
    manager = None
    if db is not None and person.manager_id is not None:
        manager = db.get(Person, person.manager_id)
    return {
        "id": person.id,
        "external_id": person.external_id,
        "display_name": person.display_name,
        "role": person.role,
        "manager_id": person.manager_id,
        "manager_name": manager.display_name if manager else None,
        "manager_external_id": manager.external_id if manager else None,
        "department_id": person.department_id,
        "department_name": person.department.name if person.department else None,
        "home_station_id": person.home_station_id,
        "home_station_name": person.home_station.name if person.home_station else None,
        "email": person.email,
        "phone": person.phone,
        "blood_group": person.blood_group,
        "must_change_password": bool(person.must_change_password),
        "field_scan_enabled": bool(person.field_scan_enabled),
        "avatar_url": f"/employees/{person.external_id}/avatar" if person.avatar_path else None,
        "has_face_enrolled": has_face_enrolled,
        "needs_attendance_photos": needs_attendance_photos,
    }
