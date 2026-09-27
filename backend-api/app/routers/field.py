"""Field attendance routes (employee-facing): face + GPS check-in / check-out."""

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db.database import get_db
from app.db.models import Person, Station
from app.schemas import DaySummary, FieldCheckInResult, FieldStatusOut, StationOut
from app.config import settings
from app.services import attendance_service as svc
from app.services import corrections
from app.services import field as field_service
from sqlalchemy import select

router = APIRouter(prefix="/attendance/field", tags=["field"])


@router.get("/stations", response_model=list[StationOut])
def field_stations(
    _: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All station geofences (also cached client-side for offline distance checks)."""
    return db.execute(select(Station).order_by(Station.name)).scalars().all()


@router.get("/status", response_model=FieldStatusOut)
def field_status(
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permission + server-suggested next action for the field-scan screen."""
    return FieldStatusOut(
        field_scan_enabled=bool(current.field_scan_enabled),
        next_direction=field_service.next_direction(db, current),
        open_entry=field_service.open_entry_today(db, current),
        home_station_id=current.home_station_id,
        home_station_name=current.home_station.name if current.home_station else None,
    )


@router.post("", response_model=FieldCheckInResult)
async def field_check_in(
    selfie: UploadFile = File(...),
    direction: str = Form(...),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    accuracy_m: float | None = Form(default=None),
    captured_at: datetime | None = Form(default=None),
    current: Person = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify the selfie (1:1) + GPS geofence and log a field entry/exit."""
    image = await selfie.read()
    try:
        result = field_service.check_in(
            db, current,
            image=image,
            direction=direction,
            latitude=latitude,
            longitude=longitude,
            accuracy_m=accuracy_m,
            captured_at=captured_at,
        )
    except field_service.FieldError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    db.commit()

    ev = result["event"]
    the_date = svc._to_local(ev.event_time).date()
    events = db.query(type(ev)).filter_by(person_id=current.id).all()
    ov = corrections.latest_overrides(db, current.id, the_date, the_date)
    day = svc.summarize_person(events, the_date, the_date, ov)[0]

    return FieldCheckInResult(
        event_id=ev.id,
        direction=result["direction"],
        review_status=result["review_status"],
        inside_geofence=result["inside_geofence"],
        station_name=result["station_name"],
        distance_m=result["distance_m"],
        message=result["message"],
        similarity=result["similarity"] if settings.field_debug_return_similarity else None,
        day=DaySummary(**day),
    )
