"""Geometric solar position, deliberately excluding atmospheric refraction."""

from datetime import datetime
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import azimuth, elevation, noon

from .model import level_from_elevation


def solar_context(latitude: float, longitude: float, timezone: str, when: datetime) -> dict:
    observer = Observer(latitude, longitude, 0)
    local_date = when.astimezone(ZoneInfo(timezone)).date()
    transit = noon(observer, local_date, ZoneInfo(timezone))
    current = elevation(observer, when, with_refraction=False)
    peak = elevation(observer, transit, with_refraction=False)
    return {
        "geometric_elevation": current,
        "solar_azimuth": azimuth(observer, when),
        "noon_elevation": peak,
        "daylight_level": level_from_elevation(current, peak),
        "solar_noon": transit.isoformat(),
    }
