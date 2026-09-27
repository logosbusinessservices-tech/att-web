"""Employee self-service routes (profile + avatar)."""

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, user_out
from app.config import settings
from app.db.database import get_db
from app.db.models import Person
from app.face.model import decode_image_bytes
from app.schemas import EmployeeProfileUpdate, UserOut

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("/profile", response_model=UserOut)
def profile(
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return user_out(current, db)


@router.patch("/profile", response_model=UserOut)
def update_profile(
    body: EmployeeProfileUpdate,
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Let an employee fill in / update their own optional contact details."""
    if body.email is not None:
        current.email = body.email.strip() or None
    if body.blood_group is not None:
        current.blood_group = body.blood_group.strip() or None
    if body.phone is not None:
        phone = body.phone.strip()
        if phone:
            digits = "".join(ch for ch in phone if ch.isdigit())
            if len(digits) < 10:
                raise HTTPException(status_code=400, detail="Enter a valid mobile number.")
            clash = db.execute(
                select(Person).where(Person.id != current.id, Person.phone.isnot(None))
            ).scalars().all()
            target = digits[-10:]
            if any("".join(c for c in (p.phone or "") if c.isdigit())[-10:] == target for p in clash):
                raise HTTPException(status_code=409, detail="That number is already in use.")
            current.phone = phone
        else:
            current.phone = None
    db.commit()
    db.refresh(current)
    return user_out(current, db)


@router.post("/avatar", response_model=UserOut)
async def upload_avatar(
    photo: UploadFile = File(...),
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set your own profile photo (cosmetic — not the attendance face template)."""
    data = await photo.read()
    if len(data) > settings.avatar_max_bytes:
        raise HTTPException(status_code=413, detail="Image is too large (max 5 MB).")
    if decode_image_bytes(data) is None:
        raise HTTPException(status_code=422, detail="That file isn't a readable image.")

    os.makedirs(settings.avatar_dir, exist_ok=True)
    path = os.path.join(settings.avatar_dir, f"{current.id}_{uuid.uuid4().hex[:8]}.jpg")
    with open(path, "wb") as fh:
        fh.write(data)

    old = current.avatar_path
    current.avatar_path = path
    db.commit()
    db.refresh(current)
    if old and old != path and os.path.exists(old):
        try:
            os.remove(old)
        except OSError:
            pass
    return user_out(current, db)


@router.get("/{external_id}/avatar")
def get_avatar(
    external_id: str,
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Serve a profile photo. Visible to the person themselves and supervisors."""
    person = db.execute(
        select(Person).where(Person.external_id == external_id)
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(status_code=404, detail="Not found")
    if current.role != "supervisor" and current.id != person.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    if not person.avatar_path or not os.path.exists(person.avatar_path):
        raise HTTPException(status_code=404, detail="No photo set")
    return FileResponse(person.avatar_path, media_type="image/jpeg")
