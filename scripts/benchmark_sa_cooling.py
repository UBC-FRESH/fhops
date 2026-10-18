#!/usr/bin/env python3
"""Benchmark the simulated-annealing temperature schedule (geometric vs adaptive).

Runs :func:`fhops.optimization.heuristics.solve_sa` for a set of scenarios, seeds, and cooling
configurations, capturing the best-so-far objective every iteration through the ``watch_sink`` API.
Reports quality at fixed iterations and interpolates quality at equal wall-clock, so the geometric
and adaptive schedules can be compared on the axis that matters for a time budget.

Examples
--------
Compare the defaults on two scenarios::

    python scripts/benchmark_sa_cooling.py --scenarios med42 large84 --seeds 1 7 42 --iters 200

Tune the adaptive rule on a smaller scenario::

    python scripts/benchmark_sa_cooling.py --scenarios small21 --iterations 300 \\
        --windows 8 16 32 64 --acceptances 0.5 0.7 0.9 --deltas 0.05 0.1

Output
------
A per-scenario table (mean final objective, mean wall-clock, and mean best-so-far at a grid of
wall-clock budgets) plus an optional JSON dump of the raw per-seed curves.
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from fhops.optimization.heuristics import solve_sa
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from fhops.telemetry.watch import Snapshot


@dataclass
class Curve:
    """One run's best-so-far trajectory: iteration, wall-clock, best objective, temperature."""

    iterations: list[int] = field(default_factory=list)
    times: list[float] = field(default_factory=list)
    best: list[float] = field(default_factory=list)
    temperature: list[float] = field(default_factory=list)


def _run(pb: Problem, iters: int, seed: int, kwargs: dict) -> Curve:
    curve = Curve()

    def sink(snap: Snapshot) -> None:
        curve.iterations.append(snap.iteration)
        curve.times.append(snap.runtime_seconds)
        curve.best.append(snap.objective)
        curve.temperature.append(snap.temperature if snap.temperature is not None else 0.0)

    solve_sa(pb, iters=iters, seed=seed, watch_sink=sink, watch_interval=1, **kwargs)
    return curve


def _interp(xs: list[float], ys: list[float], x: float) -> float:
    """Linear interpolation of ``ys`` over increasing ``xs``; clamp outside the range."""
    if not xs:
        return float("nan")
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    span = xs[hi] - xs[lo]
    if span <= 0:
        return ys[hi]
    frac = (x - xs[lo]) / span
    return ys[lo] + frac * (ys[hi] - ys[lo])


def _best_vs_time(curves: list[Curve], target: float) -> tuple[float, float] | None:
    """Mean interpolation of the best-so-far at a wall-clock ``target`` across seeds."""
    values = [_interp(c.times, c.best, target) for c in curves]
    return (statistics.fmean(values), target) if values else None


def _iterations_to_target(curve: Curve, target: float) -> int | None:
    for iteration, best in zip(curve.iterations, curve.best):
        if best >= target:
            return iteration
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--examples", default="examples", help="Directory holding scenario folders."
    )
    parser.add_argument(
        "--scenarios", nargs="+", default=["med42", "large84"], help="Scenario folder names."
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=[1, 7, 42, 123, 2026])
    parser.add_argument("--iters", type=int, default=200)
    parser.add_argument("--windows", nargs="*", type=int, default=[])
    parser.add_argument("--acceptances", nargs="*", type=float, default=[])
    parser.add_argument("--deltas", nargs="*", type=float, default=[])
    parser.add_argument(
        "--time-grid", nargs="*", type=float, default=[], help="Wall-clock budgets to interpolate."
    )
    parser.add_argument("--out", type=Path, default=None, help="Optional JSON output path.")
    return parser.parse_args()


def build_configs(args: argparse.Namespace) -> list[tuple[str, dict]]:
    configs: list[tuple[str, dict]] = [("geometric", {})]
    if not args.windows:
        configs.append(("adaptive", {"adaptive_cooling": True}))
        return configs
    windows = args.windows
    acceptances = args.acceptances or [0.9]
    deltas = args.deltas or [0.1]
    for window in windows:
        for chi in acceptances:
            for delta in deltas:
                label = f"adapt w={window} chi={chi:g} d={delta:g}"
                configs.append(
                    (
                        label,
                        {
                            "adaptive_cooling": True,
                            "cooling_window": window,
                            "cooling_initial_acceptance": chi,
                            "cooling_delta": delta,
                        },
                    )
                )
    return configs


def main() -> None:
    args = parse_args()
    configs = build_configs(args)
    payload: dict[str, dict] = {}
    for name in args.scenarios:
        root = Path(args.examples) / name / "scenario.yaml"
        pb = Problem.from_scenario(load_scenario(str(root)))
        results: dict[str, dict] = {}
        for label, kwargs in configs:
            curves = [_run(pb, args.iters, seed, kwargs) for seed in args.seeds]
            results[label] = {
                "final_mean": statistics.fmean(c.best[-1] for c in curves if c.best),
                "wall_seconds": statistics.fmean(c.times[-1] for c in curves if c.times),
                "temp_final": statistics.fmean(c.temperature[-1] for c in curves if c.temperature),
                "curves": [
                    {"iteration": c.iterations, "time": c.times, "best": c.best} for c in curves
                ],
            }
        payload[name] = results

        geo = results["geometric"]
        geo_final = geo["final_mean"]
        time_grid = args.time_grid or [
            round(f * geo["wall_seconds"], 1) for f in (0.25, 0.5, 0.75, 1.0)
        ]
        print(f"\n=== {name}: iters={args.iters} seeds={args.seeds} ===")
        print(f"  time budget grid (s): {time_grid}")
        header = f"  {'config':28s} {'final':>12s} {'wall(s)':>8s}"
        for t in time_grid:
            header += f" {'@' + str(t) + 's':>12s}"
        print(header)
        for label in results:
            row = results[label]
            cells = []
            for t in time_grid:
                curves = [Curve(c["iteration"], c["time"], c["best"], []) for c in row["curves"]]
                value = _best_vs_time(curves, t)
                cells.append(f"{value[0]:12.0f}" if value else f"{'-':>12s}")
            print(
                f"  {label:28s} {row['final_mean']:12.0f} {row['wall_seconds']:8.1f}"
                + "".join(cells)
            )
        # Iterations for the default adaptive config to match the geometric final (seed-wise).
        problems = 0
        if "adaptive" in results:
            targets = [
                _iterations_to_target(Curve(c["iteration"], c["time"], c["best"], []), geo_final)
                for c in results["adaptive"]["curves"]
            ]
            reached = [t for t in targets if t is not None]
            problems = len(targets) - len(reached)
            if reached:
                print(
                    f"  adaptive reaches the geometric final (mean {geo_final:.0f}) at "
                    f"iteration mean {statistics.fmean(reached):.0f} in {len(reached)}/"
                    f"{len(targets)} seeds"
                )
            if problems:
                print(
                    f"  adaptive did not reach it in {problems} seed(s) within {args.iters} iters"
                )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
