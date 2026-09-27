"""Seed Hyderabad railway/MMTS stations with a default geofence radius.

Coordinates were sourced from OpenStreetMap (see scripts/hyderabad_stations.json)
and filtered to Indian Railways / MMTS stations (Metro excluded). Each station's
radius_m defaults to FIELD_DEFAULT_RADIUS_M (1 km) and is tweakable per row later.

DEV ONLY. Usage:
    backend-api/.venv/Scripts/python.exe -m scripts.seed_stations
"""

import json
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.db.database import SessionLocal
from app.db.init_db import init_db
from app.db.models import Station

DATA = Path(__file__).with_name("hyderabad_stations.json")


def main():
    init_db()
    rows = json.loads(DATA.read_text(encoding="utf-8-sig"))
    db = SessionLocal()
    created = updated = 0
    try:
        for r in rows:
            name = r["name"].strip()
            lat, lon = float(r["lat"]), float(r["lon"])
            existing = db.execute(
                select(Station).where(Station.name == name)
            ).scalar_one_or_none()
            if existing is None:
                db.add(Station(
                    name=name, center_lat=lat, center_lon=lon,
                    radius_m=settings.field_default_radius_m,
                ))
                created += 1
            else:
                existing.center_lat = lat
                existing.center_lon = lon
                if not existing.radius_m:
                    existing.radius_m = settings.field_default_radius_m
                updated += 1
        db.commit()
        print(f"Stations seeded: {created} created, {updated} updated "
              f"(radius {settings.field_default_radius_m:.0f} m).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
