"""Run the offline spherical MYSTIC grid used for oriented daylight.

Example: python tools/run_directional_grid.py --libradtran /path/to/libRadtran-2.0.6 \
  --output /path/to/runs
Then run generate_directional_reference.py against that output directory.
"""

import argparse
import json
import math
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from generate_directional_reference import AZIMUTHS, ELEVATIONS, TILTS


def receiver_normal(tilt, relative_azimuth):
    t, a = math.radians(tilt), math.radians(relative_azimuth)
    return tuple(
        round(value, 8)
        for value in (math.sin(t) * math.sin(a), -math.sin(t) * math.cos(a), math.cos(t))
    )


def run_one(libradtran, output, elevation, tilt, delta, seed):
    normal = receiver_normal(tilt, delta)
    step = 1 if elevation <= -4 else 5
    photons = (
        20000000
        if elevation == -6 or (elevation == -4 and tilt == 90 and delta == 180)
        else 5000000
        if elevation <= -4
        else 1000000
    )
    tag = f"e{elevation:g}_n" + "_".join(map(str, normal)) + f"_p{photons}_s{seed}_w{step}_a0.2_edn"
    folder = output / "runs" / tag
    folder.mkdir(parents=True, exist_ok=True)
    waves = np.arange(360.0, 831.0, step)
    solar = np.loadtxt(libradtran / "data/solar_flux/kurudz_1.0nm.dat")
    np.savetxt(
        folder / "solar.dat", np.column_stack([waves, np.interp(waves, solar[:, 0], solar[:, 1])])
    )
    np.savetxt(folder / "grid.dat", waves)
    lines = [
        f"data_files_path {libradtran}/data",
        "atmosphere_file us-standard",
        f"source solar {folder}/solar.dat",
        f"wavelength_grid_file {folder}/grid.dat",
        "mol_abs_param reptran coarse",
        f"sza {90 - elevation}",
        "phi0 0",
        "earth_radius 6370",
        "albedo 0.2",
        "rte_solver mystic",
        "mc_vroom on",
        "mc_backward",
        "mc_backward_output edn",
        f"mc_sensordirection {normal[0]} {normal[1]} {normal[2]}",
        f"mc_photons {photons}",
        f"mc_randomseed {seed}",
        "mc_std",
        "mc_basename result",
        "quiet",
        "mc_spherical 1D",
        "aerosol_default",
        f"aerosol_angstrom 1.14 {0.1 * 0.5**1.14}",
        "mol_modify O3 300 DU",
    ]
    source = "\n".join(lines) + "\n"
    input_path = folder / "input.inp"
    meta_path = folder / "run.json"
    cached = (
        input_path.exists()
        and input_path.read_text() == source
        and meta_path.exists()
        and json.loads(meta_path.read_text())["returncode"] == 0
        and (folder / "result.flx.spc").exists()
    )
    if not cached:
        input_path.write_text(source)
        start = time.monotonic()
        with (
            (folder / "stdout.txt").open("w") as stdout,
            (folder / "stderr.txt").open("w") as stderr,
        ):
            result = subprocess.run(
                [str(libradtran / "bin/uvspec")],
                input=source,
                text=True,
                stdout=stdout,
                stderr=stderr,
                cwd=folder,
                check=False,
            )
        meta_path.write_text(
            json.dumps({"returncode": result.returncode, "seconds": time.monotonic() - start})
        )
        if result.returncode:
            raise RuntimeError((folder / "stderr.txt").read_text()[-2000:])
    return {
        "elevation": elevation,
        "tilt": tilt,
        "delta": delta,
        "seed": seed,
        "step_nm": step,
        "photons": photons,
        "path": str(folder.relative_to(output)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--libradtran", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    libradtran, output = args.libradtran.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    jobs = [
        (e, tilt, delta, seed)
        for e in ELEVATIONS
        for tilt in TILTS
        for delta in (AZIMUTHS if e != 90 else [0])
        for seed in (21, 42)
    ]
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, libradtran, output, *job): job for job in jobs}
        for future in as_completed(futures):
            results.append(future.result())
            (output / "manifest.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"Completed {len(results)} spectral simulations")


if __name__ == "__main__":
    main()
