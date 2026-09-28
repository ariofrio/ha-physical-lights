"""Clear-sky daylight on an oriented receiver from directional spectral runs."""

import json
import math
from bisect import bisect_right
from functools import lru_cache
from pathlib import Path

from .model import (
    DARK_ELEVATION,
    _pchip_slopes,
    chromaticity,
    color_temperature,
    from_elevation,
    load_table,
    number,
)

DEFAULT_OPTIONS = {"tilt": 0, "facing_mode": "fixed", "bearing": 90}
FACING_MODES = ("fixed", "follow_sun")


def validate_options(options):
    """Return a complete, validated receiver configuration."""
    tilt = number(options.get("tilt", 0), "tilt", 0, 90)
    bearing = number(options.get("bearing", 90), "bearing", 0, 359)
    mode = options.get("facing_mode", "fixed")
    if mode not in FACING_MODES:
        raise ValueError("facing_mode must be fixed or follow_sun")
    return {"tilt": tilt, "facing_mode": mode, "bearing": bearing}


@lru_cache(maxsize=1)
def _direct_nodes():
    return json.loads(Path(__file__).with_name("direct_reference.json").read_text())["nodes"]


def _direct_normal(elevation):
    if elevation < 0:
        return [0.0, 0.0, 0.0], 0.0
    nodes = _direct_nodes()
    angles = [row["elevation"] for row in nodes]
    index = max(0, min(len(nodes) - 2, bisect_right(angles, elevation) - 1))
    low, high = nodes[index : index + 2]
    fraction = max(
        0.0,
        min(1.0, (elevation - low["elevation"]) / (high["elevation"] - low["elevation"])),
    )
    xyz = [(1 - fraction) * a + fraction * b for a, b in zip(low["xyz"], high["xyz"], strict=True)]
    edi = (1 - fraction) * low["melanopic_edi"] + fraction * high["melanopic_edi"]
    return xyz, edi


def _pchip(x, y, value, slopes=None):
    """Evaluate shape-preserving cubic interpolation within a tabulated domain."""
    i = max(0, min(len(x) - 2, bisect_right(x, value) - 1))
    h = x[i + 1] - x[i]
    t = (value - x[i]) / h
    derivatives = slopes if slopes is not None else _pchip_slopes(x, y)
    return (
        (2 * t**3 - 3 * t**2 + 1) * y[i]
        + (t**3 - 2 * t**2 + t) * h * derivatives[i]
        + (-2 * t**3 + 3 * t**2) * y[i + 1]
        + (t**3 - t**2) * h * derivatives[i + 1]
    )


@lru_cache(maxsize=1)
def load_directional_table():
    """Load reduced spectral irradiance for the simulated receiver directions."""
    table = json.loads(Path(__file__).with_name("directional_reference.json").read_text())
    nodes = {
        (row["elevation"], row["tilt"], row["relative_azimuth"]): row for row in table["nodes"]
    }
    table["node_map"] = nodes
    curves = {}
    for tilt in table["tilts"][1:]:
        for delta in table["relative_azimuths"]:
            values = []
            for elevation in table["elevations"]:
                row = nodes[elevation, tilt, 0 if elevation == 90 else delta]
                values.append([*row["xyz"], row["melanopic_edi"]])
            channels = []
            for channel in range(4):
                logs = [math.log(row[channel]) for row in values]
                channels.append((logs, _pchip_slopes(table["elevations"], logs)))
            curves[tilt, delta] = channels
    table["curves"] = curves
    return table


def _diffuse(elevation, tilt, relative, horizontal):
    """Interpolate simulated diffuse sky plus ground on the requested plane.

    The horizontal reference supplies the 0° tilt anchor at the requested
    elevation. The 45° and 90° anchors come from spherical MYSTIC runs.
    """
    table = load_directional_table()
    azimuths = list(reversed(table["relative_azimuths"]))
    cosines = [math.cos(math.radians(delta)) for delta in azimuths]
    relative_cosine = math.cos(relative)
    result = []
    for channel in range(4):
        by_tilt = [horizontal[channel]]
        for sampled_tilt in table["tilts"][1:]:
            by_azimuth = [
                math.exp(
                    _pchip(
                        table["elevations"],
                        table["curves"][sampled_tilt, delta][channel][0],
                        elevation,
                        table["curves"][sampled_tilt, delta][channel][1],
                    )
                )
                for delta in azimuths
            ]
            by_tilt.append(
                math.exp(
                    _pchip(cosines, [math.log(value) for value in by_azimuth], relative_cosine)
                )
            )
        result.append(max(0.0, _pchip(table["tilts"], by_tilt, tilt)))
    return result


def _directional_spread(elevation, tilt, relative):
    """Conservatively report paired-run disagreement at surrounding grid nodes."""
    table = load_directional_table()
    elevations = table["elevations"]
    i = max(0, min(len(elevations) - 2, bisect_right(elevations, elevation) - 1))
    e_values = [elevations[i], elevations[i + 1]]
    distance = math.degrees(math.acos(max(-1.0, min(1.0, math.cos(relative)))))
    azimuths = table["relative_azimuths"]
    j = max(0, min(len(azimuths) - 2, bisect_right(azimuths, distance) - 1))
    delta_values = [azimuths[j], azimuths[j + 1]]
    tilt_values = [45] if tilt <= 45 else [45, 90] if tilt < 90 else [90]
    rows = [
        table["node_map"][e, beta, 0 if e == 90 else delta]
        for e in e_values
        for beta in tilt_values
        for delta in delta_values
    ]
    return {
        key: max(row[key] for row in rows)
        for key in ("relative_lux_spread", "relative_melanopic_spread", "uv_spread")
    }


def oriented_daylight(elevation, azimuth, tilt, facing_mode, bearing):
    """Evaluate incident daylight on any upward-facing receiving plane."""
    options = validate_options({"tilt": tilt, "facing_mode": facing_mode, "bearing": bearing})
    base = from_elevation(elevation)
    elevation = base["geometric_elevation"]
    azimuth = number(azimuth, "azimuth", 0, 360)
    tilt = options["tilt"]
    bearing = azimuth if options["facing_mode"] == "follow_sun" else options["bearing"]
    e, beta, relative = map(math.radians, (elevation, tilt, azimuth - bearing))
    incidence = max(
        0.0, math.sin(e) * math.cos(beta) + math.cos(e) * math.sin(beta) * math.cos(relative)
    )
    if elevation < 0:
        incidence = 0.0
    direct_xyz, direct_edi = _direct_normal(elevation)
    result = {
        **base,
        "receiver_tilt": tilt,
        "receiver_facing_mode": options["facing_mode"],
        "receiver_bearing": bearing,
        "direct_lux": 683 * direct_xyz[1] * incidence,
        "orientation_model": "directional_spectral_reference",
    }
    if elevation <= DARK_ELEVATION:
        return result
    if base["xyz"] is None:
        edge = from_elevation(load_directional_table()["elevations"][0])
        horizontal = [*edge["xyz"], edge["melanopic_edi"]]
        diffuse = _diffuse(-10, tilt, relative, horizontal)
        result.update(
            lux=683 * diffuse[1] * base["lux"] / edge["lux"],
            quality="estimated_twilight",
            orientation_model="directional_twilight_tail",
        )
        return result
    horizontal_direct = max(0.0, math.sin(e))
    horizontal = [
        max(0.0, total - normal * horizontal_direct)
        for total, normal in zip(base["xyz"], direct_xyz, strict=True)
    ]
    horizontal.append(max(0.0, base["melanopic_edi"] - direct_edi * horizontal_direct))
    diffuse = _diffuse(elevation, tilt, relative, horizontal)
    xyz = [d + n * incidence for d, n in zip(diffuse[:3], direct_xyz, strict=True)]
    edi = diffuse[3] + direct_edi * incidence
    xy, uv = chromaticity(xyz)
    cct, duv = color_temperature(uv, load_table()["planckian_locus"]) if uv else (None, None)
    spread = _directional_spread(elevation, tilt, relative) if tilt else {}
    if elevation < -6 or base["cct_reason"] == "spectral_sampling_uncertain":
        cct = None
    if spread.get("uv_spread", 0) > 0.005:
        cct = None
    reason = None if cct is not None else base["cct_reason"] or "outside_cct_reporting_range"
    if spread.get("uv_spread", 0) > 0.005:
        reason = "spectral_sampling_uncertain"
    result.update(
        lux=683 * xyz[1],
        melanopic_edi=edi,
        cct_kelvin=cct,
        xyz=xyz,
        xy=xy,
        duv=duv,
        quality=base["quality"] if tilt == 0 else "estimated_orientation",
        cct_reason=reason,
        **spread,
    )
    return result
