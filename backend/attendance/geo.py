"""Distance calculation for GPS check-in (§5, §6).

Pure functions, no ORM, no settings lookup. This decides whether someone is recorded as
inside or outside the office, so it is worth being able to test in isolation.
"""

from __future__ import annotations

import math

EARTH_RADIUS_METERS = 6_371_008.8  # IUGG mean radius


def haversine_meters(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two points, in metres.

    Haversine rather than a projected/flat approximation: at office-radius scale the
    difference is negligible, but haversine is correct everywhere including across the
    antimeridian and near the poles, and costs nothing extra.
    """
    lat1, lon1, lat2, lon2 = (float(value) for value in (lat1, lon1, lat2, lon2))

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    # asin(sqrt(a)) is numerically stable for the small distances we care about;
    # clamping guards against a > 1 from floating point error at antipodal points.
    return 2 * EARTH_RADIUS_METERS * math.asin(min(1.0, math.sqrt(a)))


def validate_coordinates(latitude, longitude):
    """Raise ValueError for coordinates that cannot exist.

    A GPS failure sometimes reports 0,0 or out-of-range values; storing those as a real
    position would produce a confident, wrong distance.
    """
    latitude = float(latitude)
    longitude = float(longitude)
    if not -90.0 <= latitude <= 90.0:
        raise ValueError(f"Latitude {latitude} is outside the range -90..90.")
    if not -180.0 <= longitude <= 180.0:
        raise ValueError(f"Longitude {longitude} is outside the range -180..180.")
    return latitude, longitude


def distance_from_office(latitude, longitude, settings_obj) -> float:
    latitude, longitude = validate_coordinates(latitude, longitude)
    return haversine_meters(latitude, longitude, settings_obj.latitude, settings_obj.longitude)


def location_status(distance_meters: float, radius_meters: int) -> str:
    """INSIDE or OUTSIDE.

    Classifies only. Whether an OUTSIDE punch is refused is the caller's business, and
    depends on `AppSettings.require_check_in_inside_radius`; by default it is recorded
    and flagged rather than blocked (D2).
    """
    return "INSIDE" if distance_meters <= radius_meters else "OUTSIDE"
