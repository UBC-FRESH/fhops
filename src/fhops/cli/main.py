from __future__ import annotations
from pathlib import Path
import sys
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

@app.command()
def validate(scenario: str):
    """Validate a scenario YAML and print summary."""
    sc = load_scenario(scenario)
    pb = Problem.from_scenario(sc)
    t = Table(title=f"Scenario: {sc.name}")
    t.add_column("Entities"); t.add_column("Count")
    t.add_row("Days", str(len(pb.days)))
    t.add_row("Blocks", str(len(sc.blocks)))
    t.add_row("Machines", str(len(sc.machines)))
    t.add_row("Landings", str(len(sc.landings)))
    console.print(t)

@app.command()
def build_mip(scenario: str):
    """Build the MIP and print basic stats."""
    sc = load_scenario(scenario)
    pb = Problem.from_scenario(sc)
    try:
        from fhops.model.pyomo_builder import build_model
        m = build_model(pb)
        console.print(f"Model built with |M|={len(m.M)} |B|={len(m.B)} |D|={len(m.D)}; vars={len(list(m.component_objects()))}")
    except Exception as e:
        console.print(f"[red]Build failed:[/red] {e}")
        raise typer.Exit(1)

@app.command()
def solve_mip(scenario: str, out: str = typer.Option(..., help="Output CSV path"), time_limit: int = 60):
    sc = load_scenario(scenario)
    pb = Problem.from_scenario(sc)
    res = solve_mip(pb, time_limit=time_limit)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    res["assignments"].to_csv(out, index=False)
    console.print(f"Objective: {res['objective']:.3f}. Saved to {out}")

@app.command()
def solve_heur(scenario: str, out: str = typer.Option(..., help="Output CSV path"), iters: int = 2000, seed: int = 42):
    sc = load_scenario(scenario)
    pb = Problem.from_scenario(sc)
    res = solve_sa(pb, iters=iters, seed=seed)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    res["assignments"].to_csv(out, index=False)
    console.print(f"Objective (heuristic): {res['objective']:.3f}. Saved to {out}")

@app.command()
def evaluate(scenario: str, assignments_csv: str):
    sc = load_scenario(scenario)
    pb = Problem.from_scenario(sc)
    df = pd.read_csv(assignments_csv)
    kpis = compute_kpis(pb, df)
    for k, v in kpis.items():
        console.print(f"{k}: {v}")

@app.command()
def benchmark(scenario: str, out_dir: str = "bench_out", time_limit: int = 60, iters: int = 5000):
    sc = load_scenario(scenario)
    pb = Problem.from_scenario(sc)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    res_mip = solve_mip(pb, time_limit=time_limit)
    mip_csv = str(Path(out_dir) / "mip_solution.csv")
    res_mip["assignments"].to_csv(mip_csv, index=False)
    res_sa = solve_sa(pb, iters=iters)
    sa_csv = str(Path(out_dir) / "sa_solution.csv")
    res_sa["assignments"].to_csv(sa_csv, index=False)
    console.print(f"MIP obj={res_mip['objective']:.3f}, SA obj={res_sa['objective']:.3f}")
    console.print(f"Saved: {mip_csv}, {sa_csv}")

if __name__ == "__main__":
    app()
