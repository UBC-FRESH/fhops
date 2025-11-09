from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import cast

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from fhops.cli._utils import (
    format_operator_presets,
    operator_preset_help,
    parse_operator_weights,
    resolve_operator_presets,
)
from fhops.cli.benchmarks import benchmark_app
from fhops.cli.geospatial import geospatial_app
from fhops.evaluation import compute_kpis
from fhops.optimization.heuristics import (
    build_exploration_plan,
    run_multi_start,
    solve_sa,
)
from fhops.optimization.mip import solve_mip
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario
from fhops.telemetry import append_jsonl

app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(geospatial_app, name="geo")
app.add_typer(benchmark_app, name="bench")
console = Console()


def _enable_rich_tracebacks():
    """Enable rich tracebacks with local variables and customized formatting."""
    try:
        import rich.traceback as _rt

        _rt.install(show_locals=True, width=140, extra_lines=2)
    except Exception:
        pass


@app.command()
def validate(scenario: Path):
    """Validate a scenario YAML and print summary."""
    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    t = Table(title=f"Scenario: {sc.name}")
    t.add_column("Entities")
    t.add_column("Count")
    t.add_row("Days", str(len(pb.days)))
    t.add_row("Blocks", str(len(sc.blocks)))
    t.add_row("Machines", str(len(sc.machines)))
    t.add_row("Landings", str(len(sc.landings)))
    console.print(t)


@app.command()
def build_mip(scenario: Path):
    """Build the MIP and print basic stats (no solve)."""
    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    try:
        from fhops.model.pyomo_builder import build_model

        m = build_model(pb)
        console.print(
            f"Model built with |M|={len(m.M)} |B|={len(m.B)} |D|={len(m.D)}; "
            f"components={len(list(m.component_objects()))}"
        )
    except Exception as e:
        console.print(f"[red]Build failed:[/red] {e}")
        raise typer.Exit(1)


@app.command("solve-mip")
def solve_mip_cmd(
    scenario: Path,
    out: Path = typer.Option(..., "--out", help="Output CSV path"),
    time_limit: int = 60,
    driver: str = typer.Option("auto", help="HiGHS driver: auto|appsi|exec"),
    debug: bool = typer.Option(False, "--debug", help="Verbose tracebacks & solver logs"),
):
    """Solve with HiGHS (exact)."""
    if debug:
        _enable_rich_tracebacks()
        console.print(
            f"[dim]types → scenario={type(scenario).__name__}, out={type(out).__name__}[/]"
        )

    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)

    out.parent.mkdir(parents=True, exist_ok=True)
    res = solve_mip(pb, time_limit=time_limit, driver=driver, debug=debug)
    assignments = cast(pd.DataFrame, res["assignments"])
    objective = cast(float, res.get("objective", 0.0))

    assignments.to_csv(str(out), index=False)
    console.print(f"Objective: {objective:.3f}. Saved to {out}")
    metrics = compute_kpis(pb, assignments)
    for key, value in metrics.items():
        console.print(f"{key}: {value:.3f}" if isinstance(value, float) else f"{key}: {value}")


@app.command("solve-heur")
def solve_heur_cmd(
    scenario: Path,
    out: Path = typer.Option(..., "--out", help="Output CSV path"),
    iters: int = 2000,
    seed: int = 42,
    debug: bool = False,
    operator: list[str] | None = typer.Option(
        None,
        "--operator",
        "-o",
        help="Enable specific heuristic operators (repeatable). Defaults to all.",
    ),
    operator_weight: list[str] | None = typer.Option(
        None,
        "--operator-weight",
        "-w",
        help="Set operator weight as name=value (e.g., --operator-weight swap=2). Repeatable.",
    ),
    operator_preset: list[str] | None = typer.Option(
        None,
        "--operator-preset",
        "-P",
        help=f"Apply operator preset ({operator_preset_help()}).",
    ),
    list_operator_presets: bool = typer.Option(
        False, "--list-operator-presets", help="Show available operator presets and exit."
    ),
    show_operator_stats: bool = typer.Option(
        False, "--show-operator-stats", help="Print per-operator stats after solving."
    ),
    telemetry_log: Path | None = typer.Option(
        None,
        "--telemetry-log",
        help="Append run telemetry to the given JSONL file.",
        writable=True,
        dir_okay=False,
    ),
    batch_neighbours: int = typer.Option(
        1,
        "--batch-neighbours",
        help="Number of neighbour candidates sampled per iteration (1 keeps sequential scoring).",
        min=1,
    ),
    parallel_workers: int = typer.Option(
        1,
        "--parallel-workers",
        help="Worker threads for batched evaluation or multi-start orchestration (1 keeps sequential).",
        min=1,
    ),
    multi_start: int = typer.Option(
        1,
        "--parallel-multistart",
        help="Run multiple SA instances in parallel and select the best objective (1 disables).",
        min=1,
    ),
):
    """Solve with Simulated Annealing (heuristic)."""
    if debug:
        _enable_rich_tracebacks()
        console.print(
            f"[dim]types → scenario={type(scenario).__name__}, out={type(out).__name__}[/]"
        )

    if list_operator_presets:
        console.print("Operator presets:")
        console.print(format_operator_presets())
        raise typer.Exit()

    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    try:
        preset_ops, preset_weights = resolve_operator_presets(operator_preset)
        weight_config = parse_operator_weights(operator_weight)
    except ValueError as exc:  # pragma: no cover - CLI validation
        raise typer.BadParameter(str(exc)) from exc

    explicit_ops = [op.lower() for op in operator] if operator else []
    combined_ops = list(dict.fromkeys((preset_ops or []) + explicit_ops)) or None
    combined_weights: dict[str, float] = {}
    combined_weights.update(preset_weights)
    combined_weights.update(weight_config)
    batch_arg = batch_neighbours if batch_neighbours > 1 else None
    worker_arg = parallel_workers if parallel_workers > 1 else None
    runs_meta = None
    seed_used = seed

    if multi_start > 1:
        seeds, auto_presets = build_exploration_plan(multi_start, base_seed=seed)
        if combined_ops:
            preset_plan = [None] * multi_start
        else:
            preset_plan = auto_presets
        try:
            res_container = run_multi_start(
                pb,
                seeds=seeds,
                presets=preset_plan,
                max_workers=worker_arg,
                sa_kwargs={
                    "iters": iters,
                    "operators": combined_ops,
                    "operator_weights": combined_weights if combined_weights else None,
                    "batch_size": batch_arg,
                    "max_workers": worker_arg,
                },
                telemetry_log=telemetry_log,
            )
            res = res_container.best_result
            runs_meta = res_container.runs_meta
            best_meta = max(
                (meta for meta in runs_meta if meta.get("status") == "ok"),
                key=lambda meta: meta.get("objective", float("-inf")),
                default=None,
            )
            if best_meta:
                seed_used = int(best_meta.get("seed", seed))
        except Exception as exc:  # pragma: no cover - guardrail path
            console.print(
                f"[yellow]Multi-start execution failed ({exc!r}); falling back to single run.[/]"
            )
            runs_meta = None
            res = solve_sa(
                pb,
                iters=iters,
                seed=seed,
                operators=combined_ops,
                operator_weights=combined_weights if combined_weights else None,
                batch_size=batch_arg,
                max_workers=worker_arg,
            )
    else:
        res = solve_sa(
            pb,
            iters=iters,
            seed=seed,
            operators=combined_ops,
            operator_weights=combined_weights if combined_weights else None,
            batch_size=batch_arg,
            max_workers=worker_arg,
        )
    assignments = cast(pd.DataFrame, res["assignments"])
    objective = cast(float, res.get("objective", 0.0))

    out.parent.mkdir(parents=True, exist_ok=True)
    assignments.to_csv(str(out), index=False)
    console.print(f"Objective (heuristic): {objective:.3f}. Saved to {out}")
    metrics = compute_kpis(pb, assignments)
    for key, value in metrics.items():
        console.print(f"{key}: {value:.3f}" if isinstance(value, float) else f"{key}: {value}")
    operators_meta = cast(dict[str, float], res.get("meta", {}).get("operators", {}))
    if operators_meta:
        console.print(f"Operators: {operators_meta}")
    if show_operator_stats:
        stats = res.get("meta", {}).get("operators_stats", {})
        if stats:
            console.print("Operator stats:")
            for name, payload in stats.items():
                console.print(
                    f"  {name}: proposals={payload.get('proposals', 0)}, "
                    f"accepted={payload.get('accepted', 0)}, "
                    f"accept_rate={payload.get('acceptance_rate', 0):.3f}, "
                    f"weight={payload.get('weight', 0)}"
                )
    if runs_meta:
        console.print(
            f"[dim]Parallel multi-start executed {len(runs_meta)} runs; best seed={seed_used}. See telemetry log for per-run details.[/]"
        )
    elif telemetry_log:
        stats = res.get("meta", {}).get("operators_stats", {}) or {}
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "source": "solve-heur",
            "scenario": sc.name,
            "scenario_path": str(scenario),
            "seed": seed_used,
            "iterations": iters,
            "objective": float(objective),
            "kpis": metrics,
            "operators_config": operators_meta or combined_weights,
            "operators_stats": stats,
            "batch_size": batch_neighbours,
            "max_workers": parallel_workers,
        }
        append_jsonl(telemetry_log, record)


@app.command()
def evaluate(scenario: Path, assignments_csv: Path):
    """Evaluate a schedule CSV against the scenario."""
    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    df = pd.read_csv(str(assignments_csv))
    kpis = compute_kpis(pb, df)
    for k, v in kpis.items():
        console.print(f"{k}: {v:.3f}" if isinstance(v, float) else f"{k}: {v}")


@app.command()
def benchmark(
    scenario: Path,
    out_dir: Path = Path("bench_out"),
    time_limit: int = 60,
    iters: int = 5000,
    driver: str = "auto",
    debug: bool = False,
):
    """Run both MIP and SA, save both outputs, and print objectives."""
    if debug:
        _enable_rich_tracebacks()
    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    out_dir.mkdir(parents=True, exist_ok=True)

    res_mip = solve_mip(pb, time_limit=time_limit, driver=driver, debug=debug)
    mip_csv = out_dir / "mip_solution.csv"
    mip_assignments = cast(pd.DataFrame, res_mip["assignments"])
    mip_assignments.to_csv(str(mip_csv), index=False)

    res_sa = solve_sa(pb, iters=iters)
    sa_csv = out_dir / "sa_solution.csv"
    sa_assignments = cast(pd.DataFrame, res_sa["assignments"])
    sa_assignments.to_csv(str(sa_csv), index=False)

    mip_metrics = compute_kpis(pb, mip_assignments)
    sa_metrics = compute_kpis(pb, sa_assignments)

    console.print(
        f"MIP obj={cast(float, res_mip['objective']):.3f}, "
        f"SA obj={cast(float, res_sa['objective']):.3f}"
    )
    console.print(f"Saved: {mip_csv}, {sa_csv}")
    console.print("MIP metrics:")
    for key, value in mip_metrics.items():
        console.print(f"  {key}: {value:.3f}" if isinstance(value, float) else f"  {key}: {value}")
    console.print("SA metrics:")
    for key, value in sa_metrics.items():
        console.print(f"  {key}: {value:.3f}" if isinstance(value, float) else f"  {key}: {value}")


if __name__ == "__main__":
    app()
