"""Reduce independent-wavelength MYSTIC spectra to a portable runtime artifact.

Run using `uv run --with colour-science==0.4.7 tools/build_reference.py RUN_DIRECTORY`.
Only matching fixed-atmosphere 1 nm, independent-wavelength runs are accepted.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import colour
import numpy as np
from melanopic import enrich_reference

ROOT = Path(__file__).resolve().parents[1]
NODES = [
    -18,
    -15,
    -12,
    -10,
    -8,
    -6,
    -4,
    -2,
    -1,
    0,
    1,
    2,
    3.5,
    5,
    7.5,
    10,
    15,
    20,
    30,
    45,
    60,
    75,
    90,
]


def main():
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

    def spectrum(folder, quantity):
        path = folder / "result.flx.spc"
        data = np.loadtxt(path, ndmin=2)
        assert len(data) == 471 and np.array_equal(data[:, 0], wl), folder
        values = data[:, 5 if quantity == "edn" else 4] / 1000
        assert np.isfinite(values).all() and (values >= 0).all(), folder
        return values, hashlib.sha256(path.read_bytes()).hexdigest()

    def xyz(values):
        return np.trapezoid(values[:, None] * cmf, wl, axis=0)

    all_rows = []
    provenance = []
    spectra = []
    for e in NODES:
        photons = 100_000_000 if e <= -8 else 50_000_000 if e <= -4 else 10_000_000
        if e > 0:
            folder = args.runs / f"mystic_e{e:g}_p1000_s21_w1_r0_a0.1_o300_g0.2_i0_edir"
            direct, checksum = spectrum(folder, "edir")
            direct *= np.sin(np.deg2rad(e))
            provenance.append(
                {
                    "elevation": e,
                    "quantity": "direct_horizontal",
                    "source": folder.name,
                    "sha256": checksum,
                }
            )
        else:
            direct = np.zeros_like(wl)
        runs = []
        for seed in (21, 42):
            folder = args.runs / f"mystic_e{e:g}_p{photons}_s{seed}_w1_r0_a0.1_o300_g0.2_i0_edn"
            meta = json.loads((folder / "run.json").read_text())
            assert meta["returncode"] == 0
            diffuse, checksum = spectrum(folder, "edn")
            total = diffuse + direct
            runs.append(xyz(total))
            spectra.extend((e, seed, w, float(d), float(s)) for w, d, s in zip(wl, direct, diffuse))
            provenance.append(
                {
                    "elevation": e,
                    "quantity": "diffuse_horizontal",
                    "source": folder.name,
                    "sha256": checksum,
                    "photons": photons,
                    "seed": seed,
                }
            )
        mean = np.mean(runs, axis=0)
        if min(mean) <= 0 or min(r[1] for r in runs) <= 0:
            all_rows.append({"elevation": e, "resolved": False, "reason": "zero_sample"})
            continue
        uv = [colour.UCS_to_uv(colour.XYZ_to_UCS(r)) for r in runs]
        spread = abs(runs[0][1] - runs[1][1]) / mean[1]
        uv_spread = float(np.linalg.norm(uv[0] - uv[1]))
        resolved = bool(spread <= 0.25 and e >= -12)
        all_rows.append(
            {
                "elevation": e,
                "xyz": mean.tolist(),
                "relative_lux_spread": float(spread),
                "uv_spread": uv_spread,
                "resolved": resolved,
            }
        )
    # Keep a contiguous resolved suffix so unreliable points cannot create holes.
    start = next(i for i in range(len(all_rows)) if all(r["resolved"] for r in all_rows[i:]))
    rows = all_rows[start:]
    assert rows[0]["elevation"] <= -6, "Civil twilight must be resolved"
    assert rows[-1]["elevation"] == 90
    locus = []
    for kelvin in np.geomspace(1500, 25000, 1000):
        uv = colour.temperature.CCT_to_uv_Planck1900(kelvin)
        locus.append([float(kelvin), *map(float, uv)])
    table = {
        "model": "mystic-fixed-atmosphere-v1",
        "schema_version": 1,
        "assumptions": {
            "solver": "libRadtran 2.0.6 spherical MYSTIC",
            "geometry": "horizontal, sea level, no refraction",
            "atmosphere": "US standard",
            "aerosol_optical_depth_500nm": 0.1,
            "angstrom_exponent": 1.14,
            "ozone_du": 300,
            "albedo": 0.2,
            "clouds": False,
            "solar_distance_au": 1,
            "wavelength_nm": [360, 830, 1],
            "gas_absorption": "REPTRAN coarse",
            "polarization": False,
        },
        "nodes": rows,
        "planckian_locus": locus,
    }
    dest = ROOT / "custom_components/physical_lights/daylight/reference.json"
    (ROOT / "docs/reference-provenance.json").write_text(
        json.dumps({"nodes": all_rows, "sources": provenance}, indent=2, allow_nan=False) + "\n"
    )
    with (ROOT / "tools/reference-spectra.csv").open("w") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "elevation",
                "seed",
                "wavelength_nm",
                "direct_horizontal_W_m2_nm",
                "diffuse_horizontal_W_m2_nm",
            ]
        )
        writer.writerows(spectra)
    with (ROOT / "tools/reference-spectra.csv").open() as stream:
        enrich_reference(table, list(csv.DictReader(stream)))
    dest.write_text(json.dumps(table, separators=(",", ":"), allow_nan=False) + "\n")
    print("Reference spans", rows[0]["elevation"], "to 90 degrees; bytes", dest.stat().st_size)
    for r in all_rows:
        print(r)


if __name__ == "__main__":
    main()
