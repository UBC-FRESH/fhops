"""Benchmark harness for FHOPS solvers."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from fhops.evaluation import compute_kpis
from fhops.optimization.heuristics import solve_sa
from fhops.optimization.mip import build_model, solve_mip
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario

console = Console()


@dataclass(frozen=True)
class BenchmarkScenario:
    name: str
    path: Path


DEFAULT_SCENARIOS: tuple[BenchmarkScenario, ...] = (
    BenchmarkScenario("minitoy", Path("examples/minitoy/scenario.yaml")),
    BenchmarkScenario("med42", Path("examples/med42/scenario.yaml")),
    BenchmarkScenario("large84", Path("examples/large84/scenario.yaml")),
)


def _resolve_scenarios(user_paths: Sequence[Path] | None) -> list[BenchmarkScenario]:
    if not user_paths:
        return list(DEFAULT_SCENARIOS)

    scenarios: list[BenchmarkScenario] = []
    for idx, scenario_path in enumerate(user_paths, start=1):
        scenarios.append(BenchmarkScenario(f"user-{idx}", scenario_path))
    return scenarios


def _record_metrics(
    *,
    scenario: BenchmarkScenario,
    solver: str,
    objective: float,
    assignments: pd.DataFrame,
    kpis: Mapping[str, object],
    runtime_s: float,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "scenario": scenario.name,
        "scenario_path": str(scenario.path),
        "solver": solver,
        "objective": float(objective),
        "runtime_s": runtime_s,
        "assignments": len(assignments),
    }
    for key, value in kpis.items():
        payload[f"kpi_{key}"] = value
    if extra:
        payload.update(extra)
    return payload


def run_benchmark_suite(
    scenario_paths: Sequence[Path] | None,
    out_dir: Path,
    *,
    time_limit: int = 300,
    sa_iters: int = 5000,
    sa_seed: int = 42,
    driver: str = "auto",
    include_mip: bool = True,
    include_sa: bool = True,
    debug: bool = False,
) -> pd.DataFrame:
    """Execute the benchmark suite and return the summary DataFrame."""
    scenarios = _resolve_scenarios(scenario_paths)
    if not scenarios:
        raise typer.BadParameter("No scenarios resolved for benchmarking.")

    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    for bench in scenarios:
        resolved_path = bench.path.expanduser()
        if not resolved_path.exists():
            raise FileNotFoundError(f"Scenario not found: {resolved_path}")
        sc = load_scenario(str(resolved_path))
        pb = Problem.from_scenario(sc)
        scenario_out = out_dir / bench.name
        scenario_out.mkdir(parents=True, exist_ok=True)

        if include_mip:
            build_start = time.perf_counter()
            # Use builder explicitly to measure build time; solve_mip will rebuild but cost is small.
            build_model(pb)
            build_time = time.perf_counter() - build_start

            start = time.perf_counter()
            mip_res = solve_mip(pb, time_limit=time_limit, driver=driver, debug=debug)
            mip_runtime = time.perf_counter() - start
            mip_assign = cast(pd.DataFrame, mip_res["assignments"]).copy()
            mip_assign.to_csv(scenario_out / "mip_assignments.csv", index=False)
            mip_kpis = compute_kpis(pb, mip_assign)
            rows.append(
                _record_metrics(
                    scenario=bench,
                    solver="mip",
                    objective=cast(float, mip_res.get("objective", 0.0)),
                    assignments=mip_assign,
                    kpis=mip_kpis,
                    runtime_s=mip_runtime,
                    extra={"build_time_s": build_time},
                )
            )

        if include_sa:
            start = time.perf_counter()
            sa_res = solve_sa(pb, iters=sa_iters, seed=sa_seed)
            sa_runtime = time.perf_counter() - start
            sa_assign = cast(pd.DataFrame, sa_res["assignments"]).copy()
            sa_assign.to_csv(scenario_out / "sa_assignments.csv", index=False)
            sa_kpis = compute_kpis(pb, sa_assign)
            rows.append(
                _record_metrics(
                    scenario=bench,
                    solver="sa",
                    objective=cast(float, sa_res.get("objective", 0.0)),
                    assignments=sa_assign,
                    kpis=sa_kpis,
                    runtime_s=sa_runtime,
                    extra={"iters": sa_iters, "seed": sa_seed},
                )
            )

    summary = pd.DataFrame(rows)
    summary_csv = out_dir / "summary.csv"
    summary_json = out_dir / "summary.json"
    summary.sort_values(["scenario", "solver"]).to_csv(summary_csv, index=False)
    summary.to_json(summary_json, orient="records", indent=2)

    table = Table(title="FHOPS Benchmark Summary")
    for column in ["scenario", "solver", "objective", "runtime_s", "assignments"]:
        table.add_column(column)
    for record in summary.sort_values(["scenario", "solver"]).to_dict(orient="records"):
        table.add_row(
            str(record["scenario"]),
            str(record["solver"]),
            f"{record.get('objective', 0.0):.3f}",
            f"{record.get('runtime_s', 0.0):.2f}",
            str(record.get("assignments", 0)),
        )
    console.print(table)

    return summary


benchmark_app = typer.Typer(add_completion=False, help="Benchmark FHOPS solvers.")


@benchmark_app.command("suite")
def bench_suite(
    scenario: list[Path] | None = typer.Option(
        None,
        "--scenario",
        "-s",
        help="Scenario YAML path(s) to benchmark. Defaults to built-in sample scenarios.",
    ),
    out_dir: Path = typer.Option(
        Path("tmp/benchmarks"), "--out-dir", dir_okay=True, file_okay=False
    ),
    time_limit: int = typer.Option(300, help="MIP time limit (seconds)"),
    sa_iters: int = typer.Option(5000, help="Simulated annealing iterations"),
    sa_seed: int = typer.Option(42, help="Simulated annealing RNG seed"),
    driver: str = typer.Option("auto", help="HiGHS driver: auto|appsi|exec"),
    include_mip: bool = typer.Option(True, help="Include MIP solver in benchmarks"),
    include_sa: bool = typer.Option(True, help="Include simulated annealing in benchmarks"),
    debug: bool = typer.Option(False, help="Forward debug flag to solvers"),
):
    """Run the full benchmark suite and emit summary CSV/JSON outputs."""
    run_benchmark_suite(
        scenario_paths=scenario,
        out_dir=out_dir,
        time_limit=time_limit,
        sa_iters=sa_iters,
        sa_seed=sa_seed,
        driver=driver,
        include_mip=include_mip,
        include_sa=include_sa,
        debug=debug,
    )
