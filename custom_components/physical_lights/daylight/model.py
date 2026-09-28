"""Pure, local daylight calculations from a versioned spectral reference table."""

import json
import math
from bisect import bisect_right
from functools import lru_cache
from pathlib import Path

DARK_ELEVATION = -18.0


def number(value, name, minimum, maximum):
    """Reject invalid inputs instead of silently converting them to darkness."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as err:
        raise ValueError(f"{name} must be a finite number") from err
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return result


@lru_cache(maxsize=1)
def load_table():
    """Load once; HA calls this in its executor during setup."""
    table = json.loads(Path(__file__).with_name("reference.json").read_text())
    nodes = table["nodes"]
    angles = [n["elevation"] for n in nodes]
    table["log_slopes"] = list(
        zip(*[_pchip_slopes(angles, [math.log(n["xyz"][j]) for n in nodes]) for j in range(3)])
    )
    melanopic_nodes = [n for n in nodes if "melanopic_edi" in n]
    table["melanopic_nodes"] = melanopic_nodes
    table["melanopic_slopes"] = _pchip_slopes(
        [n["elevation"] for n in melanopic_nodes],
        [math.log(n["melanopic_edi"]) for n in melanopic_nodes],
    )
    return table


def _pchip_slopes(x, y):
    """Shape-preserving cubic Hermite derivatives (Fritsch–Butland)."""
    h = [b - a for a, b in zip(x, x[1:])]
    d = [(b - a) / step for a, b, step in zip(y, y[1:], h)]
    if len(x) == 2:
        return [d[0], d[0]]

    def endpoint(h0, h1, d0, d1):
        slope = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if slope * d0 <= 0:
            return 0.0
        if d0 * d1 <= 0 and abs(slope) > 3 * abs(d0):
            return 3 * d0
        return slope

    slopes = [endpoint(h[0], h[1], d[0], d[1])]
    for i in range(1, len(x) - 1):
        if d[i - 1] * d[i] <= 0:
            slopes.append(0.0)
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            slopes.append((w1 + w2) / (w1 / d[i - 1] + w2 / d[i]))
    slopes.append(endpoint(h[-1], h[-2], d[-1], d[-2]))
    return slopes


def chromaticity(xyz):
    total = sum(xyz)
    if total <= 0:
        return None, None
    x, y, z = xyz
    divisor = x + 15 * y + 3 * z
    return [x / total, y / total], [4 * x / divisor, 6 * y / divisor]


def color_temperature(uv, locus):
    """Nearest segment on a densely sampled CIE 1960 Planckian locus."""
    best = (math.inf, None, None, False)
    u, v = uv
    for i, (a, b) in enumerate(zip(locus, locus[1:])):
        du, dv = b[1] - a[1], b[2] - a[2]
        raw = ((u - a[1]) * du + (v - a[2]) * dv) / (du * du + dv * dv)
        t = max(0.0, min(1.0, raw))
        eu, ev = u - a[1] - t * du, v - a[2] - t * dv
        distance = math.hypot(eu, ev)
        if distance < best[0]:
            kelvin = 1 / ((1 - t) / a[0] + t / b[0])
            duv = math.copysign(distance, dv * eu - du * ev)
            boundary = (i == 0 and raw < 0) or (i == len(locus) - 2 and raw > 1)
            best = (distance, kelvin, duv, boundary)
    _, kelvin, duv, boundary = best
    if boundary or abs(duv) > 0.02:
        return None, duv
    return kelvin, duv


def from_elevation(geometric_elevation):
    """Evaluate total horizontal clear-sky daylight at a geometric angle, degrees."""
    angle = number(geometric_elevation, "geometric_elevation", -90, 90)
    table = load_table()
    result = {
        "geometric_elevation": angle,
        "model": table["model"],
        "lux": 0.0,
        "melanopic_edi": 0.0,
        "melanopic_edi_reason": "no_solar_reference",
        "relative_melanopic_spread": None,
        "cct_kelvin": None,
        "xyz": [0.0, 0.0, 0.0],
        "xy": None,
        "duv": None,
        "quality": "night",
        "cct_reason": "no_solar_reference",
        "relative_lux_spread": None,
        "uv_spread": None,
    }
    if angle <= DARK_ELEVATION:
        return result
    melanopic_nodes = table["melanopic_nodes"]
    if angle < melanopic_nodes[0]["elevation"]:
        result.update(
            melanopic_edi=None,
            melanopic_edi_reason="outside_numerically_resolved_table",
        )
    else:
        elevations = [n["elevation"] for n in melanopic_nodes]
        i = max(0, min(len(melanopic_nodes) - 2, bisect_right(elevations, angle) - 1))
        a, b = melanopic_nodes[i : i + 2]
        h = b["elevation"] - a["elevation"]
        t = (angle - a["elevation"]) / h
        slopes = table["melanopic_slopes"]
        result.update(
            melanopic_edi=math.exp(
                (2 * t**3 - 3 * t**2 + 1) * math.log(a["melanopic_edi"])
                + (t**3 - 2 * t**2 + t) * h * slopes[i]
                + (-2 * t**3 + 3 * t**2) * math.log(b["melanopic_edi"])
                + (t**3 - t**2) * h * slopes[i + 1]
            ),
            melanopic_edi_reason=None,
            relative_melanopic_spread=max(
                a["relative_melanopic_spread"], b["relative_melanopic_spread"]
            ),
        )
    rows = table["nodes"]
    # Below the numerically usable table, preserve a continuous, explicitly
    # estimated tail. Zero at -18 degrees is a reference convention, not a
    # statement about moonlight, airglow, or the measured night sky.
    if angle < rows[0]["elevation"]:
        a, b = rows[:2]
        delta = angle - a["elevation"]
        slope = math.log(b["xyz"][1] / a["xyz"][1]) / (b["elevation"] - a["elevation"])
        taper = (angle - DARK_ELEVATION) / (a["elevation"] - DARK_ELEVATION)
        factor = math.exp(slope * delta) * taper
        xyz = [v * factor for v in a["xyz"]]
        result.update(
            lux=683 * xyz[1],
            xyz=None,
            quality="estimated_twilight",
            cct_reason="outside_numerically_resolved_table",
        )
        return result
    elevations = [row["elevation"] for row in rows]
    i = max(0, min(len(rows) - 2, bisect_right(elevations, angle) - 1))
    a, b = rows[i : i + 2]
    t = (angle - a["elevation"]) / (b["elevation"] - a["elevation"])
    h = b["elevation"] - a["elevation"]
    slopes = table["log_slopes"]
    xyz = [
        math.exp(
            (2 * t**3 - 3 * t**2 + 1) * math.log(x)
            + (t**3 - 2 * t**2 + t) * h * slopes[i][j]
            + (-2 * t**3 + 3 * t**2) * math.log(y)
            + (t**3 - t**2) * h * slopes[i + 1][j]
        )
        for j, (x, y) in enumerate(zip(a["xyz"], b["xyz"]))
    ]
    xy, uv = chromaticity(xyz)
    kelvin, duv = color_temperature(uv, table["planckian_locus"])
    spread = max(a["relative_lux_spread"], b["relative_lux_spread"])
    uv_spread = max(a["uv_spread"], b["uv_spread"])
    reason = None
    if kelvin is None:
        reason = "outside_cct_reporting_range"
    if uv_spread > 0.005:
        kelvin, reason = None, "spectral_sampling_uncertain"
    result.update(
        lux=683 * xyz[1],
        cct_kelvin=kelvin,
        xyz=xyz,
        xy=xy,
        duv=duv,
        quality="approximate" if spread > 0.02 or uv_spread > 0.001 else "reference",
        cct_reason=reason,
        relative_lux_spread=spread,
        uv_spread=uv_spread,
    )
    return result


def level_from_elevation(geometric_elevation, noon_elevation):
    angle = number(geometric_elevation, "geometric_elevation", -90, 90)
    peak = number(noon_elevation, "noon_elevation", -90, 90)
    if peak <= DARK_ELEVATION:
        return 0.0
    return max(0.0, min(1.0, (angle - DARK_ELEVATION) / (peak - DARK_ELEVATION)))


def from_level(daylight_level, noon_elevation):
    """Map 0..1 from the dark reference to the supplied day's solar maximum."""
    level = number(daylight_level, "daylight_level", 0, 1)
    peak = number(noon_elevation, "noon_elevation", -90, 90)
    angle = DARK_ELEVATION + level * (max(DARK_ELEVATION, peak) - DARK_ELEVATION)
    return {**from_elevation(angle), "daylight_level": level, "noon_elevation": peak}
