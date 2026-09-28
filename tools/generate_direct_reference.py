"""Reduce retained direct-horizontal spectra into a direct-normal lookup.

Run offline with numpy and colour-science after generating reference-spectra.csv.
The integration loads only the resulting small JSON table.
"""

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import colour
import numpy as np
from melanopic import melanopic_edi

ROOT = Path(__file__).resolve().parents[1]
SPECTRA = ROOT / "tools/reference-spectra.csv"
HORIZON_SPECTRUM = ROOT / "tools/horizon-direct-spectrum.csv"
OUTPUT = ROOT / "custom_components/physical_lights/daylight/direct_reference.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon-result", type=Path)
    args = parser.parse_args()
    spectra = defaultdict(list)
    with SPECTRA.open() as stream:
        for row in csv.DictReader(stream):
            spectra[(float(row["elevation"]), int(row["seed"]))].append(row)
    waves = np.arange(360, 831)
    color_matching = (
        colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]
        .copy()
        .align(colour.SpectralShape(360, 830, 1))
        .values
    )
    if args.horizon_result:
        data = np.loadtxt(args.horizon_result)
        if not np.array_equal(data[:, 0], waves):
            raise ValueError("Unexpected horizon direct-normal wavelength grid")
        with HORIZON_SPECTRUM.open("w", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["wavelength_nm", "direct_normal_W_m2_nm"])
            writer.writerows(
                (int(wave), format(value / 1000, ".12g"))
                for wave, value in zip(waves, data[:, 4], strict=True)
            )
    with HORIZON_SPECTRUM.open() as stream:
        horizon_rows = list(csv.DictReader(stream))
    if not np.array_equal([float(row["wavelength_nm"]) for row in horizon_rows], waves):
        raise ValueError("Incomplete horizon direct-normal spectrum")
    horizon = np.array([float(row["direct_normal_W_m2_nm"]) for row in horizon_rows])
    horizon_xyz = np.trapezoid(horizon[:, None] * color_matching, waves, axis=0)
    nodes = [
        {
            "elevation": 0.0,
            "xyz": [round(float(value), 9) for value in horizon_xyz],
            "melanopic_edi": round(melanopic_edi(waves, horizon), 6),
        }
    ]
    for angle in sorted({key[0] for key in spectra if key[0] > 0}):
        samples = []
        for seed in (21, 42):
            selected = sorted(spectra[(angle, seed)], key=lambda row: float(row["wavelength_nm"]))
            assert np.array_equal([float(row["wavelength_nm"]) for row in selected], waves)
            samples.append(
                np.array([float(row["direct_horizontal_W_m2_nm"]) for row in selected])
                / math.sin(math.radians(angle))
            )
        direct = np.mean(samples, axis=0)
        xyz = np.trapezoid(direct[:, None] * color_matching, waves, axis=0)
        nodes.append(
            {
                "elevation": angle,
                "xyz": [round(float(value), 9) for value in xyz],
                "melanopic_edi": round(melanopic_edi(waves, direct), 6),
            }
        )
    OUTPUT.write_text(
        json.dumps(
            {
                "description": "Direct-normal spectra from a separate MYSTIC run at the horizon and retained direct-horizontal reference spectra above it.",
                "nodes": nodes,
            },
            separators=(",", ":"),
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
