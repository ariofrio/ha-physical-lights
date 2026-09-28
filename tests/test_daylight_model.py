"""Public calculation contract; sample assertions use independent physical checks."""

import math

import pytest

from custom_components.physical_lights.daylight.model import from_elevation, from_level


def test_melanopic_edi_is_unscaled_and_independent_of_cct():
    # Previously integrated research spectra give about 1104 mEDI at the horizon.
    assert from_elevation(0)["melanopic_edi"] == pytest.approx(1104, rel=0.01)
    assert 80_000 < from_elevation(60)["melanopic_edi"] < 130_000
    twilight = from_elevation(-10)
    assert twilight["cct_kelvin"] is None
    assert twilight["melanopic_edi"] > 0
    assert twilight["melanopic_edi_reason"] is None


def test_melanopic_deep_twilight_is_unknown_and_night_is_a_reference_zero():
    for angle in (-17.99, -15, -12, -10.001):
        result = from_elevation(angle)
        assert result["lux"] > 0
        assert result["melanopic_edi"] is None
        assert result["melanopic_edi_reason"] == "outside_numerically_resolved_table"
    for angle in (-90, -18):
        result = from_elevation(angle)
        assert result["melanopic_edi"] == 0
        assert result["melanopic_edi_reason"] == "no_solar_reference"
    assert from_elevation(-10)["melanopic_edi"] > 0


def test_melanopic_reference_is_positive_monotone_and_continuous():
    samples = [from_elevation(-10 + i * 0.25)["melanopic_edi"] for i in range(401)]
    assert all(math.isfinite(value) and value > 0 for value in samples)
    assert all(b >= a for a, b in zip(samples, samples[1:]))
    for angle in (-8, -6, 0, 5, 20, 60, 75):
        assert from_elevation(angle - 1e-6)["melanopic_edi"] == pytest.approx(
            from_elevation(angle + 1e-6)["melanopic_edi"], rel=1e-5
        )


def test_daylight_is_finite_bright_and_returns_color():
    result = from_elevation(60)
    assert 80_000 < result["lux"] < 130_000
    assert 4500 < result["cct_kelvin"] < 7500
    assert result["geometric_elevation"] == 60
    assert all(math.isfinite(v) for v in result["xyz"])


@pytest.mark.parametrize("angle", [-18, -15, -12, -9, -6, -2, 0, 10, 60, 90])
def test_level_and_elevation_are_the_same_calculation(angle):
    # With a noon angle of 90, the -18..90 span is exactly 108 degrees.
    level = (angle + 18) / 108
    a = from_elevation(angle)
    b = from_level(level, 90)
    assert b["lux"] == pytest.approx(a["lux"])
    if a["melanopic_edi"] is None:
        assert b["melanopic_edi"] is None
    else:
        assert b["melanopic_edi"] == pytest.approx(a["melanopic_edi"])
    if a["cct_kelvin"] is None:
        assert b["cct_kelvin"] is None
    else:
        assert b["cct_kelvin"] == pytest.approx(a["cct_kelvin"])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -91, 91, None, True])
def test_bad_elevation_does_not_silently_become_night(value):
    with pytest.raises(ValueError):
        from_elevation(value)


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan"), None, True])
def test_level_is_a_bounded_normalized_number(value):
    with pytest.raises(ValueError):
        from_level(value, 60)


def test_twilight_is_included_and_night_has_no_fake_color():
    assert 1 < from_elevation(-6)["lux"] < 10
    assert from_elevation(-12)["lux"] > 0
    assert from_elevation(-18)["lux"] == 0
    assert from_elevation(-18)["cct_kelvin"] is None
    assert from_level(0, 60)["lux"] == 0


def test_brightness_is_continuous_and_monotone_over_the_full_range():
    samples = [from_elevation(-18 + i * 0.05) for i in range(2161)]
    assert all(b["lux"] >= a["lux"] for a, b in zip(samples, samples[1:]))
    for angle in (-18, -12, -10, -8, -6, -2, 0, 5, 60):
        a, b = from_elevation(angle - 1e-6), from_elevation(angle + 1e-6)
        assert abs(b["lux"] - a["lux"]) < 0.1


def test_cct_conversion_against_independent_colour_science():
    import colour
    import numpy as np

    for angle in (-6, -2, 0, 2, 5, 20, 60, 90):
        result = from_elevation(angle)
        if result["cct_kelvin"] is None:
            continue
        cct, duv = colour.temperature.XYZ_to_CCT_Ohno2013(np.array(result["xyz"]))
        assert result["cct_kelvin"] == pytest.approx(cct, rel=0.005)
        assert result["duv"] == pytest.approx(duv, abs=0.0001)


def test_estimated_twilight_does_not_invent_a_color():
    result = from_elevation(-17)
    assert result["lux"] > 0
    assert result["quality"] == "estimated_twilight"
    assert result["cct_kelvin"] is None
    assert result["xyz"] is None
    assert result["xy"] is None


def test_reference_lux_and_color_match_shipped_source_spectra():
    import csv
    from pathlib import Path

    import colour
    import numpy as np

    rows = list(csv.DictReader((Path(__file__).parents[1] / "tools/reference-spectra.csv").open()))
    for angle in (-6, 0, 20, 60, 90):
        spectra = []
        for seed in (21, 42):
            selection = [
                r for r in rows if float(r["elevation"]) == angle and int(r["seed"]) == seed
            ]
            spectra.append(
                [
                    float(r["direct_horizontal_W_m2_nm"]) + float(r["diffuse_horizontal_W_m2_nm"])
                    for r in selection
                ]
            )
        sd = colour.SpectralDistribution(dict(zip(range(360, 831), np.mean(spectra, axis=0))))
        # Integration with k=1 gives absolute tristimulus integrals, without the
        # default normalization to a perfect reflecting diffuser's Y=100.
        expected = colour.sd_to_XYZ(sd, method="Integration", k=1)
        actual = from_elevation(angle)
        assert actual["lux"] == pytest.approx(683 * expected[1], rel=0.0001)


def test_interpolation_matches_withheld_daylight_run():
    # Independent paired MYSTIC spectra at 25 degrees, excluded from table.
    assert from_elevation(25)["lux"] == pytest.approx(45790.20849665, rel=0.01)
