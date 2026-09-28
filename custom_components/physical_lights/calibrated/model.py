"""Pure-Python evaluation of measured white-light curves."""

import math
from bisect import bisect_right
from dataclasses import dataclass

from .curve_data import CURVE_DATA


def _polynomial(table: dict, value: float) -> float:
    knots = table["knots"]
    if not knots[0] <= value <= knots[-1]:
        raise ValueError("Outside measured curve")
    segment = min(bisect_right(knots, value) - 1, len(knots) - 2)
    delta = value - knots[segment]
    a, b, c, d = (row[segment] for row in table["coefficients"])
    return ((a * delta + b) * delta + c) * delta + d


class A23:
    """Philips WiZ 21 W A23, retail model 9290034999."""

    model_id = "9290034999"
    name = "Philips WiZ A23 21 W (9290034999)"
    min_kelvin = 2200
    max_kelvin = 6500
    reference_kelvin = 4001
    min_dim = 10
    max_dim = 100

    @classmethod
    def lux(cls, dim: int, kelvin: int, reference_lux: float) -> float:
        if not math.isfinite(reference_lux) or reference_lux <= 0:
            raise ValueError("Reference lux must be positive and finite")
        if not cls.min_dim <= dim <= cls.max_dim:
            raise ValueError("Dimming outside supported range")
        if not cls.min_kelvin <= kelvin <= cls.max_kelvin:
            raise ValueError("CCT outside measured range")
        data = CURVE_DATA
        fraction = _polynomial(data["shared_dimming"], dim)
        peak = _polynomial(data["peak_lux"], kelvin)
        reference_peak = _polynomial(data["peak_lux"], cls.reference_kelvin)
        return reference_lux * fraction * peak / reference_peak


@dataclass(frozen=True)
class Command:
    requested_lux: float
    estimated_lux: float
    dim: int | None
    clipped: str | None = None

    @property
    def ha_brightness(self) -> int | None:
        return None if self.dim is None else round(self.dim * 255 / 100)


def plan_target(
    model: type[A23], requested_lux: float, kelvin: int, reference_lux: float
) -> Command:
    """Quantize desired lamp-only lux to a supported WiZ dim level."""
    if not math.isfinite(requested_lux) or requested_lux < 0:
        raise ValueError("Target lux must be nonnegative and finite")
    minimum = model.lux(model.min_dim, kelvin, reference_lux)
    maximum = model.lux(model.max_dim, kelvin, reference_lux)
    if requested_lux == 0:
        return Command(requested_lux, 0, None)
    if requested_lux < minimum:
        return Command(requested_lux, minimum, model.min_dim, "below_minimum")
    if requested_lux > maximum:
        return Command(requested_lux, maximum, model.max_dim, "above_maximum")
    dim = min(
        range(model.min_dim, model.max_dim + 1),
        key=lambda value: abs(model.lux(value, kelvin, reference_lux) - requested_lux),
    )
    return Command(requested_lux, model.lux(dim, kelvin, reference_lux), dim)


def map_brightness(model: type[A23], brightness: int, kelvin: int, reference_lux: float) -> float:
    """HA brightness 1..255 linearly spans the current CCT's on range."""
    if not 1 <= brightness <= 255:
        raise ValueError("Brightness must be 1..255")
    minimum = model.lux(model.min_dim, kelvin, reference_lux)
    maximum = model.lux(model.max_dim, kelvin, reference_lux)
    return minimum + (brightness - 1) / 254 * (maximum - minimum)


def brightness_for_lux(
    model: type[A23], actual_lux: float, kelvin: int, reference_lux: float
) -> int:
    minimum = model.lux(model.min_dim, kelvin, reference_lux)
    maximum = model.lux(model.max_dim, kelvin, reference_lux)
    return round(1 + 254 * (min(max(actual_lux, minimum), maximum) - minimum) / (maximum - minimum))
