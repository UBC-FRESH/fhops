"""Scenario overlay, diff, and batch CLI commands for tactical–operational planning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from fhops.planning.tactical_operational.io import load_tactical_operational_scenario
from fhops.planning.tactical_operational.scale import (
    TacticalScaleConfig,
    run_tactical_scale_benchmark,
    write_tactical_scale_benchmark,
)
from fhops.planning.tactical_operational.scenario import (
    diff_tactical_scenarios,
    load_tactical_overlay_scenario,
    solve_tactical_batch_manifest,
    write_tactical_scenario_yaml,
)
from fhops.scenario.lidar import (
    FemicLidarError,
    validate_femic_lidar_bundle,
)
from fhops.scenario.lidar_registration import (
    FemicLidarRegistrationError,
    register_femic_lidar_bundle,
)

console = Console()
scenario_app = typer.Typer(add_completion=False, no_args_is_help=True)
lidar_app = typer.Typer(add_completion=False, no_args_is_help=True)
scenario_app.add_typer(lidar_app, name="lidar", help="Register and validate FEMIC LidarBC bundles.")


@lidar_app.command("validate")
def lidar_validate(
    bundle: Path = typer.Argument(..., help="FEMIC LidarBC bundle directory."),
    verify_checksums: bool = typer.Option(
        True,
        "--verify-checksums/--no-verify-checksums",
        help="Verify every product SHA-256 and byte size.",
    ),
) -> None:
    """Validate a FEMIC bundle without modifying a scenario."""
    report = validate_femic_lidar_bundle(bundle, verify_checksums=verify_checksums)
    typer.echo(json.dumps(report.to_dict(), indent=2))
    if not report.is_valid:
        raise typer.Exit(1)


@lidar_app.command("register")
def lidar_register(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML to pin the bundle in."),
    bundle: Path = typer.Argument(..., help="FEMIC LidarBC bundle directory."),
    expected_bundle_id: str | None = typer.Option(
        None, "--expected-bundle-id", help="Require this FEMIC bundle id."
    ),
    expected_bundle_version: str | None = typer.Option(
        None, "--expected-bundle-version", help="Require this FEMIC bundle version."
    ),
    verify_checksums: bool = typer.Option(
        True,
        "--verify-checksums/--no-verify-checksums",
        help="Verify every product SHA-256 and byte size.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print the pin without writing the scenario."
    ),
) -> None:
    """Validate a FEMIC bundle, check the scenario AOI, and write its bundle pin."""
    try:
        result = register_femic_lidar_bundle(
            scenario,
            bundle,
            expected_bundle_id=expected_bundle_id,
            expected_bundle_version=expected_bundle_version,
            verify_checksums=verify_checksums,
            dry_run=dry_run,
        )
    except (FemicLidarError, FemicLidarRegistrationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result.to_dict(), indent=2))


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


@scenario_app.command("benchmark")
def benchmark_tactical(
    blocks: Annotated[
        list[int] | None, typer.Option("--blocks", help="Repeatable block counts.")
    ] = None,
    years: Annotated[int, typer.Option("--years", min=1)] = 1,
    periods_per_year: Annotated[int, typer.Option("--periods-per-year", min=1, max=13)] = 4,
    products: Annotated[int, typer.Option("--products", min=1)] = 2,
    facilities: Annotated[int, typer.Option("--facilities", min=1)] = 2,
    systems: Annotated[int, typer.Option("--systems", min=1)] = 2,
    seed: Annotated[int, typer.Option("--seed")] = 44,
    demand_fraction: Annotated[float, typer.Option("--demand-fraction", min=0.0, max=1.0)] = 0.25,
    solver: Annotated[str, typer.Option("--solver")] = "highs",
    time_limit: Annotated[int | None, typer.Option("--time-limit")] = None,
    gap: Annotated[float | None, typer.Option("--gap", min=0.0)] = None,
    out_dir: Path = typer.Option(
        ...,
        "--out-dir",
        help="Directory for tactical scale benchmark CSV/JSON/Markdown outputs.",
    ),
) -> None:
    """Run deterministic tactical scale benchmarks across one or more block counts."""
    block_counts = blocks or [100]
    configs = [
        TacticalScaleConfig(
            num_blocks=count,
            years=years,
            periods_per_year=periods_per_year,
            num_products=products,
            num_facilities=facilities,
            num_systems=systems,
            seed=seed,
            demand_fraction=demand_fraction,
        )
        for count in block_counts
    ]
    frame = run_tactical_scale_benchmark(configs, solver=solver, time_limit=time_limit, gap=gap)
    written = write_tactical_scale_benchmark(frame, out_dir)
    console.print(
        f"Wrote tactical scale benchmark for {len(frame)} cases to {written['markdown'].parent}"
    )
