"""Scenario overlay, diff, and batch CLI commands for tactical–operational planning."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from fhops.planning.tactical_operational.io import load_tactical_operational_scenario
from fhops.planning.tactical_operational.scenario import (
    diff_tactical_scenarios,
    load_tactical_overlay_scenario,
    solve_tactical_batch_manifest,
    write_tactical_scenario_yaml,
)

console = Console()
scenario_app = typer.Typer(add_completion=False, no_args_is_help=True)


@scenario_app.command("overlay")
def overlay_scenario(
    base: Path = typer.Argument(..., help="Base tactical–operational scenario YAML."),
    overlay: Path = typer.Argument(..., help="Sparse overlay YAML."),
    out: Path = typer.Option(..., "--out", help="Merged scenario YAML output path."),
) -> None:
    """Apply a sparse overlay to a tactical scenario and write the merged bundle."""
    scenario = load_tactical_overlay_scenario(base, overlay)
    write_tactical_scenario_yaml(scenario, out)
    console.print(f"Wrote overlaid tactical scenario to {out}")


@scenario_app.command("diff")
def diff_scenarios(
    base: Path = typer.Argument(..., help="Base tactical–operational scenario YAML."),
    candidate: Path = typer.Argument(..., help="Candidate tactical–operational scenario YAML."),
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Optional CSV path for the scenario diff."),
    ] = None,
) -> None:
    """Compare two tactical scenarios field-by-field."""
    base_scenario = load_tactical_operational_scenario(base)
    candidate_scenario = load_tactical_operational_scenario(candidate)
    frame = diff_tactical_scenarios(base_scenario, candidate_scenario)
    console.print(f"Scenario diff rows: {len(frame)}")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(out, index=False)
        console.print(f"Wrote scenario diff to {out}")


@scenario_app.command("batch")
def batch_scenarios(
    manifest: Path = typer.Argument(..., help="Batch manifest YAML with a `cases` list."),
    out_dir: Path = typer.Option(
        ...,
        "--out-dir",
        help="Directory for per-case reports and comparison tables.",
    ),
) -> None:
    """Solve a batch of tactical scenarios/overlays and write comparison reports."""
    summary = solve_tactical_batch_manifest(manifest, out_dir=out_dir)
    console.print(f"Solved {len(summary)} tactical cases; comparison written to {out_dir}")
