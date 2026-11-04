#!/usr/bin/env python3
"""Compare the kernel full-repair and dirty-repair annealing paths.

The script is a reproduction aid, not a gate. It prints one JSON record with wall-clock
seconds, the exact returned objective, and the search metadata for each path.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from fhops.optimization.meta import (
    solve_kernel_sa,
    solve_kernel_sa_fast,
    solve_kernel_sa_incremental,
)
from fhops.scenario.contract import Problem
from fhops.scenario.io.loaders import load_scenario


def main() -> int:
    """Run both kernel annealing paths and print their measurements."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, default=Path("examples/tiny7/scenario.yaml"))
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    pb = Problem.from_scenario(load_scenario(args.scenario))
    records = []
    for name, solver in (
        ("full", solve_kernel_sa),
        ("fast", solve_kernel_sa_fast),
        ("incremental", solve_kernel_sa_incremental),
    ):
        started = time.perf_counter()
        result = solver(pb, iters=args.iterations, seed=args.seed)
        seconds = time.perf_counter() - started
        records.append(
            {
                "path": name,
                "seconds": round(seconds, 3),
                "objective": round(float(result["objective"]), 3),
                "solver": result["meta"]["solver"],
            }
        )
    print(json.dumps(records, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
