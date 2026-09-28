"""Receiver orientation must preserve horizontal behavior and solar geometry."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.physical_lights.daylight.orientation import _direct_normal, oriented_daylight
from custom_components.physical_lights.daylight.preview import daily_curve, render_svg

VALIDATION = json.loads((Path(__file__).parent / "data/directional_validation.json").read_text())


def test_horizontal_equals_reference_at_any_bearing():
    from custom_components.physical_lights.daylight.model import from_elevation

    for elevation in (-12, -6, 0, 5, 35, 75):
        reference = from_elevation(elevation)
        for bearing in (0, 90, 180, 270):
            got = oriented_daylight(elevation, 120, 0, "fixed", bearing)
            assert got["lux"] == pytest.approx(reference["lux"])
            assert got["melanopic_edi"] == pytest.approx(reference["melanopic_edi"])
            if reference["cct_kelvin"] is not None:
                assert got["cct_kelvin"] == pytest.approx(reference["cct_kelvin"])
            else:
                assert got["cct_kelvin"] is None


def test_angled_receiver_facing_away_matches_independent_simulation():
    got = oriented_daylight(0, 90, 45, "fixed", 270)
    assert got["lux"] == pytest.approx(679, rel=0.10)


@pytest.mark.parametrize("case", VALIDATION["vertical"])
def test_vertical_reference_matches_independent_sunrise_facing_runs(case):
    got = oriented_daylight(
        case["elevation"], 90, 90, "fixed", (90 - case["relative_azimuth"]) % 360
    )
    assert got["lux"] == pytest.approx(case["lux"], rel=0.10)
    if case["elevation"] >= 0 and case["cct_kelvin"] and case["cct_kelvin"] <= 10000:
        assert got["cct_kelvin"] == pytest.approx(case["cct_kelvin"], abs=350)


@pytest.mark.parametrize("case", VALIDATION["intermediate_tilt"])
def test_intermediate_tilt_matches_withheld_diffuse_simulations(case):
    got = oriented_daylight(
        case["elevation"],
        90,
        case["tilt"],
        "fixed",
        (90 - case["relative_azimuth"]) % 360,
    )
    assert got["lux"] - got["direct_lux"] == pytest.approx(case["diffuse_lux"], rel=0.10)
    direct_xyz, direct_edi = _direct_normal(case["elevation"])
    projected_edi = got["direct_lux"] * direct_edi / (683 * direct_xyz[1])
    assert got["melanopic_edi"] - projected_edi == pytest.approx(
        case["diffuse_melanopic_edi"], rel=0.10
    )


def test_sun_behind_vertical_receiver_has_no_direct_component():
    east = oriented_daylight(30, 90, 90, "fixed", 90)
    west = oriented_daylight(30, 90, 90, "fixed", 270)
    assert east["direct_lux"] > 0
    assert west["direct_lux"] == 0
    assert east["lux"] > west["lux"]


def test_following_sun_ignores_saved_bearing():
    a = oriented_daylight(30, 90, 90, "follow_sun", 0)
    b = oriented_daylight(30, 90, 90, "follow_sun", 180)
    assert a["lux"] == pytest.approx(b["lux"])


def test_unresolved_twilight_does_not_invent_color_or_melanopic_edi():
    result = oriented_daylight(-12, 90, 90, "fixed", 90)
    assert result["lux"] > 0
    assert result["melanopic_edi"] is None
    assert result["cct_kelvin"] is None


def test_direct_normal_beam_is_visible_on_sun_facing_vertical_at_horizon():
    facing = oriented_daylight(0, 90, 90, "fixed", 90)
    horizontal = oriented_daylight(0, 90, 0, "fixed", 90)
    away = oriented_daylight(0, 90, 90, "fixed", 270)
    assert facing["direct_lux"] == pytest.approx(93.22, rel=0.01)
    assert horizontal["direct_lux"] == 0
    assert away["direct_lux"] == 0


def test_daily_preview_spans_local_day_and_is_an_svg():
    curve = daily_curve(
        40.7,
        -74.0,
        "America/New_York",
        datetime(2026, 9, 26, tzinfo=ZoneInfo("America/New_York")).date(),
        {"tilt": 90, "facing_mode": "fixed", "bearing": 90},
    )
    assert curve[0]["time"].hour == 0
    assert curve[-1]["time"].hour == 0
    assert curve[-1]["time"].day == 27
    assert any(row["lux"] > 0 for row in curve)
    svg = render_svg(curve)
    assert svg.startswith("<svg")
    assert "Illuminance" in svg
    assert "Melanopic EDI" in svg
    assert "Color temperature" in svg
