"""Estimated melanopic daylight efficacy ratios for generic CRI 90 LEDs."""

from bisect import bisect_right
from math import isfinite

# Typical TRILUX CRI 90 LED spectra, not measurements of a particular bulb.
DER_KNOTS = ((2700, 0.45), (3000, 0.49), (4000, 0.66), (6500, 0.94))
MIN_KELVIN = DER_KNOTS[0][0]
MAX_KELVIN = DER_KNOTS[-1][0]


def melanopic_der(kelvin: int | float) -> float:
    """Interpolate the generic LED proxy without spectral extrapolation."""
    if not isfinite(kelvin) or not MIN_KELVIN <= kelvin <= MAX_KELVIN:
        raise ValueError("CCT outside generic LED spectral model")
    index = min(bisect_right(DER_KNOTS, (kelvin, float("inf"))) - 1, len(DER_KNOTS) - 2)
    (left_k, left_der), (right_k, right_der) = DER_KNOTS[index : index + 2]
    return left_der + (kelvin - left_k) * (right_der - left_der) / (right_k - left_k)
