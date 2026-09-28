"""Exposure-first planner behavior with a representative calibrated source."""

import pytest

from custom_components.physical_lights.melanopic.planner import plan_edi
from custom_components.physical_lights.melanopic.spectral import melanopic_der


class SampleCalibratedLight:
    """A plausible measured photopic CCT curve, independent of the WiZ code."""

    points = ((2700, 81), (3000, 97), (4000, 173), (4500, 149), (5000, 116), (6000, 97), (6500, 89))

    def max_lux(self, kelvin):
        for (left_k, left_lux), (right_k, right_lux) in zip(self.points, self.points[1:]):
            if left_k <= kelvin <= right_k:
                return left_lux + (right_lux - left_lux) * (kelvin - left_k) / (right_k - left_k)
        raise ValueError("outside sample CCT range")

    def min_lux(self, kelvin):
        return self.max_lux(kelvin) * 0.036


@pytest.mark.parametrize(
    ("kelvin", "expected"),
    [(2700, 0.45), (3000, 0.49), (4000, 0.66), (6500, 0.94)],
)
def test_der_proxy_knots(kelvin, expected):
    assert melanopic_der(kelvin) == pytest.approx(expected)


def test_no_unsupported_spectral_extrapolation():
    with pytest.raises(ValueError):
        melanopic_der(2200)


def test_keeps_preferred_cct_when_exposure_fits():
    result = plan_edi(SampleCalibratedLight(), 60, 6500, 2500)
    assert result.kelvin == 6500
    assert result.requested_lux == pytest.approx(60 / 0.94)
    assert result.clipped is None


def test_moves_cct_only_as_far_as_needed():
    result = plan_edi(SampleCalibratedLight(), 100, 6500, 2500)
    assert 4500 < result.kelvin < 5000
    assert result.requested_lux == pytest.approx(100 / melanopic_der(result.kelvin))
    assert result.clipped is None


def test_fixed_cct_clips_but_preserves_request():
    result = plan_edi(SampleCalibratedLight(), 100, 6500, 0)
    assert result.kelvin == 6500
    assert result.requested_lux == pytest.approx(100 / 0.94)
    assert result.target_edi == 100
    assert result.clipped == "above_maximum"
    assert result.max_edi == pytest.approx(89 * 0.94)


def test_capacity_envelope_and_off():
    result = plan_edi(SampleCalibratedLight(), 0, 6500, 2500)
    assert result.kelvin == 6500
    assert result.requested_lux == 0
    assert result.min_edi > 0
    assert result.max_edi > 110
