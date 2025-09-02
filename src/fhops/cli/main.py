# src/fhops/cli/main.py
from __future__ import annotations
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table
import pandas as pd

from fhops.data.loaders import load_scenario
from fhops.core.types import Problem
from fhops.solve.highs_mip import solve_mip
from fhops.solve.heuristics.sa import solve_sa
from fhops.eval.kpis import compute_kpis

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


def _enable_rich_tracebacks():
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
        console.print(f"[dim]types → scenario={type(scenario).__name__}, out={type(out).__name__}[/]")

    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)

    out.parent.mkdir(parents=True, exist_ok=True)
    res = solve_mip(pb, time_limit=time_limit, driver=driver, debug=debug)

    # Always pass a string path to pandas
    res["assignments"].to_csv(str(out), index=False)
    console.print(f"Objective: {res['objective']:.3f}. Saved to {out}")


@app.command("solve-heur")
def solve_heur_cmd(
    scenario: Path,
    out: Path = typer.Option(..., "--out", help="Output CSV path"),
    iters: int = 2000,
    seed: int = 42,
    debug: bool = False,
):
    """Solve with Simulated Annealing (heuristic)."""
    if debug:
        _enable_rich_tracebacks()
        console.print(f"[dim]types → scenario={type(scenario).__name__}, out={type(out).__name__}[/]")

    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    res = solve_sa(pb, iters=iters, seed=seed)

    out.parent.mkdir(parents=True, exist_ok=True)
    res["assignments"].to_csv(str(out), index=False)
    console.print(f"Objective (heuristic): {res['objective']:.3f}. Saved to {out}")


@app.command()
def evaluate(scenario: Path, assignments_csv: Path):
    """Evaluate a schedule CSV against the scenario."""
    sc = load_scenario(str(scenario))
    pb = Problem.from_scenario(sc)
    df = pd.read_csv(str(assignments_csv))
    kpis = compute_kpis(pb, df)
    for k, v in kpis.items():
        console.print(f"{k}: {v}")


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
    res_mip["assignments"].to_csv(str(mip_csv), index=False)

    res_sa = solve_sa(pb, iters=iters)
    sa_csv = out_dir / "sa_solution.csv"
    res_sa["assignments"].to_csv(str(sa_csv), index=False)

    console.print(f"MIP obj={res_mip['objective']:.3f}, SA obj={res_sa['objective']:.3f}")
    console.print(f"Saved: {mip_csv}, {sa_csv}")


if __name__ == "__main__":
    app()