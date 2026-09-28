"""Generate the release's fixed-atmosphere spectra, then build its lookup table."""

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from build_reference import NODES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--libradtran", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    tools = Path(__file__).resolve().parent
    jobs = [
        (e, 100_000_000 if e <= -8 else 50_000_000 if e <= -4 else 10_000_000, seed, "edn")
        for e in NODES
        for seed in (21, 42)
    ]
    jobs += [(e, 1000, 21, "edir") for e in NODES if e > 0]

    def run(job):
        e, photons, seed, quantity = job
        folder = args.work / f"mystic_e{e:g}_p{photons}_s{seed}_w1_r0_a0.1_o300_g0.2_i0_{quantity}"
        if (folder / "run.json").exists():
            return f"{folder.name}: cached"
        subprocess.run(
            [
                sys.executable,
                str(tools / "run_spectrum.py"),
                "--libradtran",
                str(args.libradtran),
                "--output",
                str(args.work),
                "--elev",
                str(e),
                "--photons",
                str(photons),
                "--seed",
                str(seed),
                "--step",
                "1",
                "--aod",
                "0.1",
                "--ozone",
                "300",
                "--albedo",
                "0.2",
                "--quantity",
                quantity,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return f"{folder.name}: complete"

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for message in pool.map(run, jobs):
            print(message, flush=True)
    subprocess.run([sys.executable, str(tools / "build_reference.py"), str(args.work)], check=True)


if __name__ == "__main__":
    main()
