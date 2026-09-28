"""Add CIE S 026 melanopic EDI to the existing fixed-atmosphere reference.

Run directly to reduce the retained spectra without rerunning the solver.
Scientific dependencies are offline only; HA uses the generated scalar nodes.
"""

import csv
import hashlib
import json
from pathlib import Path

import colour
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ACTION_PATH = ROOT / "tools/data/CIE_a-opic_action_spectra.csv"
ACTION_SHA256 = "d69ff61bd49d63f530b4fcc7be9ba2db37bf31cba1bb50a8e87c1bc86f725250"
MIN_ELEVATION = -10


def melanopic_edi(wavelengths, irradiance):
    """Integrate absolute W m-2 nm-1 spectra, normalized to D65 per photopic lux."""
    if hashlib.sha256(ACTION_PATH.read_bytes()).hexdigest() != ACTION_SHA256:
        raise ValueError("CIE action-spectrum checksum mismatch")
    action = np.loadtxt(ACTION_PATH, delimiter=",")
    waves = np.arange(360, 831)
    weight = np.interp(waves, action[:, 0], action[:, 5], left=0, right=0)
    shape = colour.SpectralShape(360, 830, 1)
    y = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"].copy().align(shape).values[:, 1]
    d65 = colour.SDS_ILLUMINANTS["D65"].copy().align(shape).values
    normalization = np.trapezoid(d65 * weight, waves) / (683 * np.trapezoid(d65 * y, waves))
    spectrum = np.interp(waves, wavelengths, irradiance)
    return float(np.trapezoid(spectrum * weight, waves) / normalization)


def enrich_reference(table, spectra):
    """Attach independently integrated melanopic values to retained elevation nodes."""
    for node in table["nodes"]:
        if node["elevation"] < MIN_ELEVATION:
            continue
        values = []
        for seed in (21, 42):
            selected = sorted(
                (
                    row
                    for row in spectra
                    if float(row["elevation"]) == node["elevation"] and int(row["seed"]) == seed
                ),
                key=lambda row: float(row["wavelength_nm"]),
            )
            waves = [float(row["wavelength_nm"]) for row in selected]
            if waves != list(range(360, 831)):
                raise ValueError(f"Incomplete spectrum at {node['elevation']} degrees, seed {seed}")
            value = melanopic_edi(
                waves,
                [
                    float(row["direct_horizontal_W_m2_nm"])
                    + float(row["diffuse_horizontal_W_m2_nm"])
                    for row in selected
                ],
            )
            if not np.isfinite(value) or value <= 0:
                raise ValueError("Unresolved melanopic irradiance")
            values.append(value)
        node["melanopic_edi"] = float(np.mean(values))
        node["relative_melanopic_spread"] = abs(values[0] - values[1]) / node["melanopic_edi"]
    table["schema_version"] = 2
    table["melanopic_reference"] = {
        "standard": "CIE S 026:2018",
        "action_spectrum_doi": "https://doi.org/10.25039/CIE.DS.vqqhzp5a",
        "action_spectrum_sha256": ACTION_SHA256,
        "license": "CC BY-SA 4.0",
        "minimum_elevation": MIN_ELEVATION,
        "normalization": "D65 melanopic irradiance per photopic lux; approximately 0.0013262 W/lm",
    }
    return table


def main():
    path = ROOT / "custom_components/physical_lights/daylight/reference.json"
    with (ROOT / "tools/reference-spectra.csv").open() as stream:
        spectra = list(csv.DictReader(stream))
    table = enrich_reference(json.loads(path.read_text()), spectra)
    path.write_text(json.dumps(table, separators=(",", ":"), allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
