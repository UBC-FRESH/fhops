#!/usr/bin/env python3
"""Benchmark the FHOPS simulated-annealing solver on the example ladder.

Runs ``solve_sa`` on each of the bundled scenarios (tiny7, small21, med42, large84) with a fixed
iteration budget and seed, and reports wall time, evaluations per second, the objective, and peak
memory. Use ``--profile`` to cProfile one scenario and print the hot functions.

Usage
-----
    python scripts/benchmark_sa.py
    python scripts/benchmark_sa.py --iters 500 --scenarios med42 large84
    python scripts/benchmark_sa.py --profile med42
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import resource
import time
from pathlib import Path

from fhops.optimization.heuristics import solve_sa
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario

ROOT = Path(__file__).resolve().parents[1]
LADDER = ["tiny7", "small21", "med42", "large84"]


def run_one(name: str, iters: int, seed: int, local_repairs: bool) -> dict[str, float]:
    """Solve one scenario and return its timing and objective.

    Parameters
    ----------
    name : str
        Scenario directory name under ``examples/``.
    iters : int
        Simulated-annealing iteration budget.
    seed : int
        RNG seed.
    local_repairs : bool
        Whether to repair only dirty slots between moves.

    Returns
    -------
    dict of str to float
        ``scenario``, ``iters``, ``seconds``, ``evals_per_s``, ``objective`` and ``peak_mib``.
    """
    scenario = load_scenario(str(ROOT / "examples" / name / "scenario.yaml"))
    problem = Problem.from_scenario(scenario)
    start = time.perf_counter()
    result = solve_sa(problem, iters=iters, seed=seed, use_local_repairs=local_repairs)
    seconds = time.perf_counter() - start
    peak_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "scenario": name,
        "iters": float(iters),
        "seconds": seconds,
        "evals_per_s": iters / seconds,
        "objective": float(result["objective"]),
        "peak_mib": peak_kib / 1024.0,
    }


def main() -> int:
    """Run the benchmark and print a table.

    Returns
    -------
    int
        Always 0.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--iters", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenarios", nargs="*", default=LADDER)
    parser.add_argument("--local-repairs", action="store_true")
    parser.add_argument("--profile", metavar="SCENARIO", help="cProfile one scenario and exit")
    args = parser.parse_args()

    if args.profile:
        scenario = load_scenario(str(ROOT / "examples" / args.profile / "scenario.yaml"))
        problem = Problem.from_scenario(scenario)
        profiler = cProfile.Profile()
        profiler.enable()
        solve_sa(problem, iters=args.iters, seed=args.seed, use_local_repairs=args.local_repairs)
        profiler.disable()
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats("cumulative").print_stats(20)
        print("\n".join(stream.getvalue().splitlines()[:28]))
        return 0

    rows = [run_one(name, args.iters, args.seed, args.local_repairs) for name in args.scenarios]
    print(
        f"{'scenario':<12}{'iters':>7}{'seconds':>10}{'evals/s':>10}{'objective':>16}{'peak MiB':>10}"
    )
    for row in rows:
        print(
            f"{row['scenario']:<12}{int(row['iters']):>7}{row['seconds']:>10.2f}"
            f"{row['evals_per_s']:>10.1f}{row['objective']:>16.1f}{row['peak_mib']:>10.0f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
