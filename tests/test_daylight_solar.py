from datetime import datetime, timezone

from custom_components.physical_lights.daylight.solar import solar_context


def test_equinox_equator_noon_and_midnight():
    noon = solar_context(0, 0, "UTC", datetime(2026, 3, 20, 12, 7, tzinfo=timezone.utc))
    night = solar_context(0, 0, "UTC", datetime(2026, 3, 20, 0, 7, tzinfo=timezone.utc))
    assert noon["geometric_elevation"] > 89
    assert noon["daylight_level"] > 0.999
    assert night["geometric_elevation"] < -89
    assert night["daylight_level"] == 0


def test_polar_night_has_no_division_by_zero():
    result = solar_context(89, 0, "UTC", datetime(2026, 12, 21, 12, tzinfo=timezone.utc))
    assert result["noon_elevation"] < -18
    assert result["daylight_level"] == 0
