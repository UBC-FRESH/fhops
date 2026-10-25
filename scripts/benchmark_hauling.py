#!/usr/bin/env python
"""Benchmark the Phase I/II/III hauling stack and optionally run a Taguchi-style SA sweep.

Examples
--------
Run the example day with both the exact MIP and the SA solver::

    python scripts/benchmark_hauling.py --solver both --day 1

Run a small Taguchi L9 sweep of the SA parameters::

    python scripts/benchmark_hauling.py --solver sa --calibrate --out-dir tmp/hauling-calibration
"""

from __future__ import annotations

import argparse
import csv
import itertools
import time
from pathlib import Path

from fhops.hauling.flow import build_flow_problem, solve_flow
from fhops.hauling.heuristic import SAConfig, solve_sa
from fhops.hauling.network import build_schedule_problem
from fhops.hauling.schedule import solve_schedule, validate_schedule
from fhops.scenario.io import load_scenario

# A compact Taguchi-style L9 subset. The full thesis grid is 3 levels for four factors; this
# script uses the same factor levels but caps the move count so a sweep finishes quickly.
TAGUCHI_LEVELS = {
    "initial_temperature": (300.0, 350.0, 400.0),
    "min_temperature_ratio": (0.00025, 0.0005, 0.00075),
    "cooling_rate": (0.85, 0.9, 0.95),
    "iterations_per_temperature": (50, 70, 90),
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, default=Path("examples/hauling/scenario.yaml"))
    parser.add_argument("--day", type=int, default=1)
    parser.add_argument("--solver", choices=("mip", "sa", "both"), default="both")
    parser.add_argument("--time-limit", type=float, default=60.0)
    parser.add_argument("--sa-iters", type=int, default=200)
    parser.add_argument("--sa-seed", type=int, default=42)
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/hauling-benchmark"))
    return parser.parse_args()


def main() -> int:
    """Run the benchmark or calibration sweep."""
    args = _parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    scenario = load_scenario(args.scenario)
    flow_start = time.perf_counter()
    flow = solve_flow(
        build_flow_problem(scenario),
        time_limit=args.time_limit,
    )
    flow_runtime = time.perf_counter() - flow_start
    print(f"Phase I: status={flow.status} cost={flow.cost_objective} runtime={flow_runtime:.3f}s")
    if flow.status not in {"optimal", "feasible"}:
        print(flow.solver_error or "Phase I did not produce a flow plan")
        return 1

    problem = build_schedule_problem(scenario, flow, args.day)
    print(f"Phase II day {args.day}: loads={len(problem.loads)}")

    if args.solver in {"mip", "both"}:
        start = time.perf_counter()
        mip = solve_schedule(problem, time_limit=args.time_limit)
        runtime = time.perf_counter() - start
        violations = validate_schedule(problem, mip.schedule) if mip.status == "optimal" else []
        print(
            f"MIP: status={mip.status} objective={mip.objective} "
            f"violations={len(violations)} runtime={runtime:.3f}s"
        )

    if args.solver in {"sa", "both"}:
        start = time.perf_counter()
        sa = solve_sa(
            problem,
            SAConfig(
                max_iterations=args.sa_iters, iterations_per_temperature=20, seed=args.sa_seed
            ),
        )
        runtime = time.perf_counter() - start
        violations = validate_schedule(problem, sa.schedule) if sa.status == "feasible" else []
        print(
            f"SA: status={sa.status} objective={sa.objective} "
            f"violations={len(violations)} iterations={sa.iterations} runtime={runtime:.3f}s"
        )

    if args.calibrate:
        _run_calibration(problem, args)
    return 0


def _run_calibration(problem, args: argparse.Namespace) -> None:
    """Run a compact L9 sweep and write the result table."""
    rows = []
    combos = list(
        itertools.product(
            TAGUCHI_LEVELS["initial_temperature"],
            TAGUCHI_LEVELS["min_temperature_ratio"],
            TAGUCHI_LEVELS["cooling_rate"],
            TAGUCHI_LEVELS["iterations_per_temperature"],
        )
    )[:9]
    for index, (t0, ratio, alpha, iterations) in enumerate(combos, start=1):
        start = time.perf_counter()
        result = solve_sa(
            problem,
            SAConfig(
                initial_temperature=t0,
                min_temperature_ratio=ratio,
                cooling_rate=alpha,
                iterations_per_temperature=iterations,
                max_iterations=args.sa_iters,
                seed=args.sa_seed,
            ),
        )
        rows.append(
            {
                "run": index,
                "initial_temperature": t0,
                "min_temperature_ratio": ratio,
                "cooling_rate": alpha,
                "iterations_per_temperature": iterations,
                "objective": result.objective,
                "runtime_seconds": time.perf_counter() - start,
                "iterations": result.iterations,
            }
        )
        print(
            f"calibration {index}/{len(combos)}: objective={result.objective} "
            f"runtime={rows[-1]['runtime_seconds']:.3f}s"
        )

    best = min(row["objective"] for row in rows if row["objective"] is not None)
    for row in rows:
        row["rpd"] = (
            (row["objective"] - best) / best
            if row["objective"] is not None and best not in {0, None}
            else 0.0
        )
    csv_path = args.out_dir / "hauling_sa_calibration.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    raise SystemExit(main())
