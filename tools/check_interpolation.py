"""Compare interpolation with independent spectral runs at withheld elevations."""

import argparse
import json
import sys
from pathlib import Path

import colour
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from custom_components.daylight.model import chromaticity, from_elevation  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("runs", type=Path)
args = parser.parse_args()
wl = np.arange(360.0, 831.0)
cmf = (
    colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]
    .copy()
    .align(colour.SpectralShape(360, 830, 1))
    .values
)
rows = []
for e in (-3, 0.5, 4, 25, 52.5, 82.5):
    if e > 0:
        p = args.runs / f"mystic_e{e:g}_p1000_s21_w1_r0_a0.1_o300_g0.2_i0_edir/result.flx.spc"
        direct = np.loadtxt(p)[:, 4] / 1000 * np.sin(np.deg2rad(e))
    else:
        direct = np.zeros_like(wl)
    samples = []
    for seed in (21, 42):
        p = (
            args.runs
            / f"mystic_e{e:g}_p10000000_s{seed}_w1_r0_a0.1_o300_g0.2_i0_edn/result.flx.spc"
        )
        sky = np.loadtxt(p)[:, 5] / 1000
        samples.append(np.trapezoid((sky + direct)[:, None] * cmf, wl, axis=0))
    actual = np.mean(samples, axis=0)
    interp = from_elevation(e)
    delta = abs(interp["lux"] / (683 * actual[1]) - 1)
    uv = chromaticity(actual)[1]
    uv_delta = float(np.linalg.norm(np.array(chromaticity(interp["xyz"])[1]) - uv))
    rows.append(
        {
            "elevation": e,
            "direct_simulation_lux": float(683 * actual[1]),
            "interpolated_lux": interp["lux"],
            "relative_lux_difference": delta,
            "uv_difference": uv_delta,
        }
    )
out = {
    "method": "Paired independent-wavelength MYSTIC runs at nodes excluded from the table; includes Monte Carlo noise.",
    "samples": rows,
    "maximum_relative_lux_difference": max(r["relative_lux_difference"] for r in rows),
    "maximum_uv_difference": max(r["uv_difference"] for r in rows),
}
(ROOT / "docs/interpolation-check.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(out, indent=2))
