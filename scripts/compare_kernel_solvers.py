#!/usr/bin/env python3
"""Compare the existing FHOPS solvers with the kernel-backed paths.

The comparison uses the same scenario, seed, and iteration budget for each pair. It reports the
fresh objective and wall-clock seconds. This is parity/performance evidence, not a claim that the
two implementations follow the same trajectory.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fhops.optimization.heuristics import solve_ils, solve_sa, solve_tabu
from fhops.optimization.meta import (
    solve_kernel_ils,
    solve_kernel_ils_like,
    solve_kernel_sa_incremental,
    solve_kernel_tabu,
)
from fhops.scenario.contract import Problem
from fhops.scenario.io.loaders import load_scenario

Runner = Callable[[Problem, int, int], dict[str, Any]]


def _timed(runner: Runner, pb: Problem, iterations: int, seed: int) -> dict[str, Any]:
    """Run one solver and return its objective and wall-clock seconds."""
    started = time.perf_counter()
    result = runner(pb, iterations, seed)
    seconds = time.perf_counter() - started
    return {"objective": float(result["objective"]), "seconds": round(seconds, 3)}


def main() -> int:
    """Run the parity ladder and print or write its JSON records."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios",
        default="tiny7,small21,med42",
        help="Comma-separated scenario names or scenario.yaml paths.",
    )
    parser.add_argument(
        "--scenario-root",
        type=Path,
        default=Path("examples"),
        help="Directory holding <name>/scenario.yaml for the named scenarios.",
    )
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument(
        "--solvers",
        default="",
        help="Optional comma-separated solver pairs (sa,tabu,ils,ils_like).",
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    pairs: dict[str, tuple[Runner, Runner]] = {
        "sa": (
            lambda pb, it, seed: solve_sa(pb, iters=it, seed=seed),
            lambda pb, it, seed: solve_kernel_sa_incremental(pb, iters=it, seed=seed),
        ),
        "tabu": (
            lambda pb, it, seed: solve_tabu(pb, iters=it, seed=seed),
            lambda pb, it, seed: solve_kernel_tabu(pb, iters=it, seed=seed),
        ),
        "ils": (
            lambda pb, it, seed: solve_ils(pb, iters=it, seed=seed),
            lambda pb, it, seed: solve_kernel_ils(pb, iters=it, seed=seed),
        ),
        "ils_like": (
            lambda pb, it, seed: solve_ils(pb, iters=it, seed=seed),
            lambda pb, it, seed: solve_kernel_ils_like(pb, iters=it, seed=seed),
        ),
    }
    records: list[dict[str, Any]] = []
    allowed = {item.strip() for item in args.solvers.split(",") if item.strip()}
    for name in [item.strip() for item in args.scenarios.split(",") if item.strip()]:
        candidate = Path(name)
        path = candidate if candidate.is_file() else args.scenario_root / name / "scenario.yaml"
        pb = Problem.from_scenario(load_scenario(str(path)))
        for solver, (existing, kernel) in pairs.items():
            if allowed and solver not in allowed:
                continue
            old = _timed(existing, pb, args.iterations, args.seed)
            new = _timed(kernel, pb, args.iterations, args.seed)
            records.append(
                {
                    "scenario": name,
                    "solver": solver,
                    "iterations": args.iterations,
                    "seed": args.seed,
                    "existing": old,
                    "kernel": new,
                    "objective_delta": round(new["objective"] - old["objective"], 6),
                    "speed_ratio": round(new["seconds"] / old["seconds"], 3)
                    if old["seconds"]
                    else None,
                }
            )
    text = json.dumps(records, indent=2, sort_keys=True)
    print(text)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
