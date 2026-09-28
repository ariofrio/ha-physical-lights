"""Reduce offline MYSTIC tilted-plane spectra to the runtime directional table.

The input directory contains manifest.json and the corresponding MYSTIC run
folders. It is produced by run_directional_grid.py or an equivalent run with
the documented fixed atmosphere. Scientific packages are offline-only.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import colour
import numpy as np
from melanopic import melanopic_edi

ROOT = Path(__file__).resolve().parents[1]
ELEVATIONS = [-10, -8, -6, -4, -2, -1, 0, 1, 2, 3.5, 5, 7.5, 10, 15, 20, 30, 45, 60, 75, 90]
TILTS = [45, 90]
AZIMUTHS = [0, 45, 90, 135, 180]


def uv(value):
    x, y, z = value
    divisor = x + 15 * y + 3 * z
    return np.array([4 * x / divisor, 6 * y / divisor])


def reduce_runs(runs_root):
    """Average independent seeds after separate spectral integration."""
    manifest = json.loads((runs_root / "manifest.json").read_text())
    grouped = defaultdict(list)
    provenance = []
    for entry in manifest:
        run = runs_root / entry["path"]
        meta = json.loads((run / "run.json").read_text())
        if meta["returncode"]:
            raise ValueError(f"MYSTIC failed: {run}")
        path = run / "result.flx.spc"
        data = np.loadtxt(path)
        waves = data[:, 0]
        if not np.array_equal(waves, np.arange(360, 831, entry["step_nm"])):
            raise ValueError(f"Unexpected wavelength grid: {run}")
        spectrum = data[:, 5] / 1000
        cmf = (
            colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]
            .copy()
            .align(colour.SpectralShape(360, 830, entry["step_nm"]))
            .values
        )
        xyz = np.trapezoid(spectrum[:, None] * cmf, waves, axis=0)
        edi = melanopic_edi(waves, spectrum)
        key = (entry["elevation"], entry["tilt"], entry["delta"])
        grouped[key].append((entry["seed"], xyz, edi))
        provenance.append(
            {
                **{
                    k: entry[k]
                    for k in ("elevation", "tilt", "delta", "seed", "step_nm", "photons")
                },
                "input_sha256": hashlib.sha256((run / "input.inp").read_bytes()).hexdigest(),
                "spectrum_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    nodes = []
    for elevation in ELEVATIONS:
        for tilt in TILTS:
            for delta in AZIMUTHS if elevation != 90 else [0]:
                samples = sorted(grouped[elevation, tilt, delta], key=lambda row: row[0])
                if [row[0] for row in samples] != [21, 42]:
                    raise ValueError(f"Missing independent seeds at {elevation}, {tilt}, {delta}")
                xyz = np.mean([row[1] for row in samples], axis=0)
                edi = float(np.mean([row[2] for row in samples]))
                if np.any(xyz <= 0) or edi <= 0:
                    raise ValueError(
                        f"Unresolved directional spectrum at {elevation}, {tilt}, {delta}"
                    )
                nodes.append(
                    {
                        "elevation": elevation,
                        "tilt": tilt,
                        "relative_azimuth": delta,
                        "xyz": xyz.tolist(),
                        "melanopic_edi": edi,
                        "relative_lux_spread": float(
                            abs(samples[0][1][1] - samples[1][1][1]) / xyz[1]
                        ),
                        "relative_melanopic_spread": float(
                            abs(samples[0][2] - samples[1][2]) / edi
                        ),
                        "uv_spread": float(np.linalg.norm(uv(samples[0][1]) - uv(samples[1][1]))),
                    }
                )
    if len(grouped) != len(nodes) or len(manifest) != 2 * len(nodes):
        raise ValueError("Unexpected or duplicate directional grid runs")
    reference = {
        "schema_version": 1,
        "description": "MYSTIC diffuse sky and ground irradiance on tilted receiving planes",
        "elevations": ELEVATIONS,
        "tilts": [0, *TILTS],
        "relative_azimuths": AZIMUTHS,
        "nodes": nodes,
    }
    return reference, provenance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-root", type=Path, required=True)
    args = parser.parse_args()
    reference, provenance = reduce_runs(args.runs_root)
    (ROOT / "custom_components/physical_lights/daylight/directional_reference.json").write_text(
        json.dumps(reference, separators=(",", ":"), allow_nan=False) + "\n"
    )
    (ROOT / "docs/daylight/directional-provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
