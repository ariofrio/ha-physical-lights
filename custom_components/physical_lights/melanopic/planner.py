"""Choose photopic lux and CCT for a requested melanopic EDI."""

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from .spectral import MAX_KELVIN, MIN_KELVIN, melanopic_der


class CalibratedRange(Protocol):
    """Read-only capabilities required from the photopic calibration layer."""

    def min_lux(self, kelvin: int) -> float: ...

    def max_lux(self, kelvin: int) -> float: ...


@dataclass(frozen=True)
class EdiPlan:
    target_edi: float
    requested_lux: float
    kelvin: int
    min_edi: float
    max_edi: float
    clipped: str | None


def plan_edi(source: CalibratedRange, target: float, preferred: int, max_delta: int) -> EdiPlan:
    """Prioritize EDI, then stay as close as possible to preferred CCT."""
    if not isfinite(target) or target < 0:
        raise ValueError("Target melanopic EDI must be nonnegative and finite")
    if not MIN_KELVIN <= preferred <= MAX_KELVIN or not 0 <= max_delta <= 3800:
        raise ValueError("Invalid preferred CCT or adjustment limit")
    lower = max(MIN_KELVIN, preferred - max_delta)
    upper = min(MAX_KELVIN, preferred + max_delta)
    minimum_edi = float("inf")
    maximum_edi = 0.0
    feasible: tuple[int, int] | None = None
    fallback: tuple[float, int, int, str | None] | None = None

    for kelvin in range(lower, upper + 1):
        der = melanopic_der(kelvin)
        minimum = source.min_lux(kelvin) * der
        maximum = source.max_lux(kelvin) * der
        minimum_edi = min(minimum_edi, minimum)
        maximum_edi = max(maximum_edi, maximum)
        distance = abs(kelvin - preferred)
        if minimum <= target <= maximum:
            candidate = (distance, kelvin)
            if feasible is None or candidate < feasible:
                feasible = candidate
        else:
            error = minimum - target if target < minimum else target - maximum
            candidate = (
                error,
                distance,
                kelvin,
                "below_minimum" if target < minimum else "above_maximum",
            )
            if fallback is None or candidate < fallback:
                fallback = candidate

    if target == 0:
        return EdiPlan(0, 0, preferred, minimum_edi, maximum_edi, None)
    if feasible is not None:
        return EdiPlan(
            target,
            target / melanopic_der(feasible[1]),
            feasible[1],
            minimum_edi,
            maximum_edi,
            None,
        )
    assert fallback is not None
    return EdiPlan(
        target,
        target / melanopic_der(fallback[2]),
        fallback[2],
        minimum_edi,
        maximum_edi,
        fallback[3],
    )
