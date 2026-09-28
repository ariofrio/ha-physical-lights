import argparse
import json
import subprocess
import sys
import time
from bisect import bisect_left
from pathlib import Path

p = Path(__file__).resolve().parent

a = argparse.ArgumentParser()
a.add_argument("--libradtran", type=Path, required=True)
a.add_argument("--output", type=Path, required=True)
a.add_argument("--elev", type=float, default=-6)
a.add_argument("--photons", type=int, default=100000)
a.add_argument("--seed", type=int, default=21)
a.add_argument("--step", type=int, default=10)
a.add_argument("--mono", type=int)
a.add_argument("--refraction", action="store_true")
a.add_argument("--aod", type=float)
a.add_argument("--ozone", type=int)
a.add_argument("--albedo", type=float, default=0)
a.add_argument("--alis", action="store_true")
a.add_argument("--quantity", default="edn")
a.add_argument("--sample", type=int, default=550)
a.add_argument("--g", type=float)
args = a.parse_args()
root = args.libradtran.resolve()
p = args.output.resolve()
p.mkdir(parents=True, exist_ok=True)
name = f"mystic_e{args.elev:g}_p{args.photons}_s{args.seed}_w{args.mono or args.step}_r{int(args.refraction)}_a{args.aod}_o{args.ozone}_g{args.albedo}_i{int(args.alis)}_{args.quantity}"
name += f"_l{args.sample}" if args.sample != 550 else ""
name += f"_h{args.g}" if args.g is not None else ""
out = p / name
out.mkdir(exist_ok=True)
wl = [args.mono] if args.mono else list(range(360, 831, args.step))
# Exact solar values at requested grid, linearly interpolated from the shipped spectrum.
spec = []
for line in (
    (
        root
        / (
            "data/solar_flux/atlas_plus_modtran"
            if args.mono
            else "data/solar_flux/kurudz_1.0nm.dat"
        )
    )
    .read_text()
    .splitlines()
):
    if line.strip() and not line.lstrip().startswith("#"):
        spec.append(tuple(map(float, line.split()[:2])))

waves = [r[0] for r in spec]
solar = []
for w in wl:
    i = bisect_left(waves, w)
    lo, hi = spec[i - 1], spec[i]
    value = lo[1] + (hi[1] - lo[1]) * (w - lo[0]) / (hi[0] - lo[0])
    solar.append(f"{w} {value:.10g}")
(out / "solar.dat").write_text("\n".join(solar) + "\n")
(out / "grid.dat").write_text("\n".join(map(str, wl)) + "\n")
lines = [
    f"data_files_path {root}/data",
    "atmosphere_file us-standard",
    f"source solar {out}/solar.dat",
    f"wavelength_grid_file {out}/grid.dat",
    "mol_abs_param reptran coarse",
    f"sza {90 - args.elev}",
    "earth_radius 6370",
    "zout 0",
    f"albedo {args.albedo}",
    "rte_solver mystic",
    "mc_spherical 1D",
    "mc_vroom on",
    "mc_backward",
    f"mc_backward_output {args.quantity}",
    f"mc_photons {args.photons}",
    f"mc_randomseed {args.seed}",
    "mc_std",
    "mc_basename result",
    "quiet",
]
if args.alis:
    lines += [f"mc_spectral_is {args.sample}"]
if args.refraction:
    lines += ["mc_refraction"]
if args.aod is not None:
    lines += ["aerosol_default", f"aerosol_angstrom 1.14 {args.aod * 0.5**1.14}"]
if args.g is not None:
    lines += [f"aerosol_modify gg set {args.g}"]
if args.ozone is not None:
    lines += [f"mol_modify O3 {args.ozone} DU"]
input = "\n".join(lines) + "\n"
(out / "input.inp").write_text(input)
t = time.monotonic()
with (out / "stdout.txt").open("w") as stdout, (out / "stderr.txt").open("w") as stderr:
    r = subprocess.run(
        [str(root / "bin/uvspec")], input=input, text=True, stdout=stdout, stderr=stderr, cwd=out
    )
(out / "run.json").write_text(
    json.dumps(
        {
            "arguments": {k: v for k, v in vars(args).items() if k not in ("libradtran", "output")},
            "seconds": time.monotonic() - t,
            "returncode": r.returncode,
        },
        indent=2,
    )
    + "\n"
)
print(name, "rc", r.returncode, "seconds", round(time.monotonic() - t, 2), flush=True)
print((out / "stdout.txt").read_text()[:150] if args.mono else "")
print((out / "stderr.txt").read_text()[-1500:])

sys.exit(r.returncode)
