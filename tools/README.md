# Reproducing the reference

Build [libRadtran 2.0.6](https://www.libradtran.org/doku.php?id=download) with MYSTIC support and its scientific dependencies. The build is separate from the HA installation; the runtime does not need it.

Generate all release nodes and aggregate them:

```sh
uv run --with colour-science==0.4.7 tools/generate_reference.py \
  --libradtran /path/to/libRadtran-2.0.6 \
  --work ./work/reference-runs --workers 4
```

This is a substantial offline calculation. The directory contains per-run inputs, spectral fluxes, seeds, and timing. Completed runs are reused. Delete a failed run's directory before retrying.

To rebuild only the derived artifact from completed runs:

```sh
uv run --with colour-science==0.4.7 tools/build_reference.py ./work/reference-runs
```

Outputs:

- `custom_components/physical_lights/daylight/reference.json`: runtime XYZ and melanopic EDI nodes and Planckian locus.
- `docs/reference-provenance.json`: retained/rejected node diagnostics and hashes of source flux files.
- `tools/reference-spectra.csv`: direct-horizontal and diffuse-horizontal spectra for both seeds at every sampled elevation, in W m⁻² nm⁻¹.

To rebuild the small direct-normal lookup for tilted receiving surfaces from that retained CSV:

```sh
uv run --with colour-science==0.4.7 tools/generate_direct_reference.py
```

This writes `custom_components/physical_lights/daylight/direct_reference.json`. It divides direct-horizontal spectra by sin(geometric elevation) at positive elevations, averages both seeds, then reduces XYZ and melanopic EDI. At 0°, division is undefined, so it uses the separately simulated [horizon direct-normal spectrum](horizon-direct-spectrum.csv). That spectrum comes from `run_spectrum.py` with `--elev 0 --quantity edir --step 1 --photons 1000 --seed 21 --aod 0.1 --ozone 300 --albedo 0.2`; column 5 of `result.flx.spc` is converted from mW to W m⁻² nm⁻¹. The runtime interpolates the resulting lookup without scientific Python packages.

To reproduce the horizon spectrum and direct table from the solver:

```sh
uv run --with colour-science==0.4.7 tools/run_spectrum.py \
  --libradtran /path/to/libRadtran-2.0.6 --output ./work/horizon-direct \
  --elev 0 --quantity edir --step 1 --photons 1000 --seed 21 \
  --aod 0.1 --ozone 300 --albedo 0.2
uv run --with colour-science==0.4.7 tools/generate_direct_reference.py \
  --horizon-result ./work/horizon-direct/mystic_e0_p1000_s21_w1_r0_a0.1_o300_g0.2_i0_edir/result.flx.spc
```

Generate the directional diffuse-sky-plus-ground reference for configured receiver angles:

```sh
uv run --with colour-science==0.4.7 tools/run_directional_grid.py \
  --libradtran /path/to/libRadtran-2.0.6 \
  --output ./work/directional-runs --workers 4
uv run --with colour-science==0.4.7 tools/generate_directional_reference.py \
  --runs-root ./work/directional-runs
```

The 384 independent runs sample 45° and 90° tilt and relative solar azimuths 0°, 45°, 90°, 135°, and 180° at the reference elevations (one azimuth suffices at a zenith sun). The horizontal reference supplies the 0° anchor. Wavelength steps are 1 nm from −10° through −4°, then 5 nm; twilight photon counts are increased where paired-run color differences were large. Each node uses seeds 21 and 42. The reducer writes `custom_components/physical_lights/daylight/directional_reference.json` and `docs/daylight/directional-provenance.json`. The runtime interpolates XYZ and melanopic EDI without libRadtran or scientific Python packages.

See [the model documentation](../docs/model.md) for the exact assumptions and limitations. Generated spectra are numerical model outputs, not observations. Paths and location-specific information from the HA installation are not included.

To add or rebuild melanopic EDI from the retained CSV without rerunning libRadtran:

```sh
uv run --with colour-science==0.4.7 tools/melanopic.py
```

`build_reference.py` also invokes this reduction, so full regeneration includes mEDI. The original CIE action-spectrum CSV and metadata are retained under `tools/data/`; their SHA-256 is checked before use. See [data notices](../custom_components/physical_lights/daylight/NOTICE.md). Scientific packages and the action-spectrum CSV are not runtime dependencies.
