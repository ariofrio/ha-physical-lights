"""Offline reduction checked against standard illuminants, not the daylight model."""

import colour
import pytest

from tools.melanopic import melanopic_edi


@pytest.mark.parametrize("illuminant,expected", [("D65", 100), ("A", 49.585)])
def test_standard_spectra_at_100_photopic_lux(illuminant, expected):
    spectrum = colour.SDS_ILLUMINANTS[illuminant].copy().align(colour.SpectralShape(360, 830, 1))
    xyz = colour.sd_to_XYZ(spectrum, method="Integration", k=1)
    spectrum *= 100 / (683 * xyz[1])
    assert melanopic_edi(spectrum.wavelengths, spectrum.values) == pytest.approx(
        expected, rel=0.001
    )
