"""Geofence check for field attendance.

v1 uses a simple center-point + radius (Haversine) test per station, since each
railway station has its own size (radius_m on the Station row). PostGIS polygons
can replace this later without changing callers.
"""

import math


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two lat/lon points."""
    r = 6371000.0  # Earth radius, metres
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def inside_geofence(
    point_lat: float,
    point_lon: float,
    center_lat: float,
    center_lon: float,
    radius_m: float,
) -> tuple[bool, float]:
    """Return (is_inside, distance_m) for a point vs a station's circular geofence."""
    dist = haversine_m(point_lat, point_lon, center_lat, center_lon)
    return dist <= radius_m, dist


def nearest_station(point_lat: float, point_lon: float, stations: list) -> tuple[object | None, float]:
    """Return (station, distance_m) for the closest station to the point.

    `stations` is any iterable of objects with center_lat/center_lon. Returns
    (None, inf) if the list is empty.
    """
    best = None
    best_dist = float("inf")
    for s in stations:
        d = haversine_m(point_lat, point_lon, s.center_lat, s.center_lon)
        if d < best_dist:
            best, best_dist = s, d
    return best, best_dist
