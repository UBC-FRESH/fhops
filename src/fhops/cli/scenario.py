"""Scenario overlay, diff, and batch CLI commands for tactical–operational planning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

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
from fhops.scenario.hydrology import (
    FemicHydrologyError,
    validate_femic_hydrology_bundle,
)
from fhops.scenario.hydrology_mapping import (
    FemicHydrologyMappingError,
    map_femic_hydrology_to_scenario,
    write_hydrology_mapping,
)
from fhops.scenario.hydrology_registration import (
    FemicHydrologyRegistrationError,
    register_femic_hydrology_bundle,
)
from fhops.scenario.io import load_scenario
from fhops.scenario.lidar import (
    FemicLidarError,
    validate_femic_lidar_bundle,
)
from fhops.scenario.lidar_mapping import (
    FemicLidarMappingError,
    map_femic_lidar_to_scenario,
)
from fhops.scenario.lidar_operability import assess_scenario_operability
from fhops.scenario.lidar_registration import (
    FemicLidarRegistrationError,
    register_femic_lidar_bundle,
)

console = Console()
scenario_app = typer.Typer(add_completion=False, no_args_is_help=True)
lidar_app = typer.Typer(add_completion=False, no_args_is_help=True)
scenario_app.add_typer(lidar_app, name="lidar", help="Register and validate FEMIC LidarBC bundles.")
hydrology_app = typer.Typer(add_completion=False, no_args_is_help=True)
scenario_app.add_typer(
    hydrology_app,
    name="hydrology",
    help="Validate and consume FEMIC hydrology response bundles.",
)


@hydrology_app.command("validate")
def hydrology_validate(
    bundle: Path = typer.Argument(..., help="FEMIC hydrology bundle directory."),
    expected_bundle_id: str | None = typer.Option(
        None, "--expected-bundle-id", help="Require this FEMIC bundle id."
    ),
    expected_bundle_version: str | None = typer.Option(
        None, "--expected-bundle-version", help="Require this FEMIC bundle version."
    ),
    verify_checksums: bool = typer.Option(
        True,
        "--verify-checksums/--no-verify-checksums",
        help="Verify every artifact SHA-256 and byte size.",
    ),
) -> None:
    """Validate a FEMIC hydrology bundle without modifying a scenario."""
    try:
        report = validate_femic_hydrology_bundle(
            bundle,
            expected_bundle_id=expected_bundle_id,
            expected_bundle_version=expected_bundle_version,
            verify_checksums=verify_checksums,
        )
    except FemicHydrologyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(report.to_dict(), indent=2))
    if not report.is_valid:
        raise typer.Exit(1)


@hydrology_app.command("register")
def hydrology_register(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML to pin the bundle in."),
    bundle: Path = typer.Argument(..., help="FEMIC hydrology bundle directory."),
    expected_bundle_id: str | None = typer.Option(
        None, "--expected-bundle-id", help="Require this FEMIC bundle id."
    ),
    expected_bundle_version: str | None = typer.Option(
        None, "--expected-bundle-version", help="Require this FEMIC bundle version."
    ),
    verify_checksums: bool = typer.Option(
        True,
        "--verify-checksums/--no-verify-checksums",
        help="Verify every artifact SHA-256 and byte size.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print the pin without writing the scenario."
    ),
) -> None:
    """Validate a FEMIC hydrology bundle and write its scenario pin."""
    try:
        result = register_femic_hydrology_bundle(
            scenario,
            bundle,
            expected_bundle_id=expected_bundle_id,
            expected_bundle_version=expected_bundle_version,
            verify_checksums=verify_checksums,
            dry_run=dry_run,
        )
    except (FemicHydrologyError, FemicHydrologyRegistrationError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result.to_dict(), indent=2))


@hydrology_app.command("map")
def hydrology_map(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML with a hydrology pin."),
    bundle: Path = typer.Argument(..., help="FEMIC hydrology bundle directory."),
    crosswalk: Path = typer.Argument(..., help="Explicit crosswalk CSV."),
    metadata: Path | None = typer.Option(
        None, "--metadata", help="Crosswalk review metadata JSON."
    ),
    out: Path | None = typer.Option(
        None, "--out", help="Mapping output directory. Print only when omitted."
    ),
    allow_partial: bool = typer.Option(
        False, "--allow-partial", help="Record unmapped supports instead of failing."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print the mapping without writing outputs."
    ),
) -> None:
    """Map scenario support to FEMIC watersheds and receptors."""
    try:
        result = map_femic_hydrology_to_scenario(
            scenario,
            bundle,
            crosswalk,
            metadata_path=metadata,
            allow_partial=allow_partial,
        )
        paths = None if dry_run or out is None else write_hydrology_mapping(result, out)
    except FemicHydrologyMappingError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    payload = result.to_dict()
    if paths is not None:
        payload["paths"] = {key: str(value) for key, value in paths.items()}
    typer.echo(json.dumps(payload, indent=2))


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


@lidar_app.command("operability")
def lidar_operability(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML with LiDAR support."),
    block: list[str] | None = typer.Option(None, "--block", help="Repeatable block id filter."),
    json_output: bool = typer.Option(False, "--json", help="Print JSON instead of a table."),
) -> None:
    """Report advisory ground/cable/helicopter compatibility from terrain/canopy evidence."""
    try:
        loaded = load_scenario(scenario)
        rows = assess_scenario_operability(loaded)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    if block:
        selected = set(block)
        rows = tuple(row for row in rows if row.block_id in selected)
    if json_output:
        typer.echo(json.dumps([row.to_dict() for row in rows], indent=2))
        return
    table = Table(
        title="Advisory LiDAR operability",
        show_lines=False,
        header_style="bold",
    )
    table.add_column("Block")
    table.add_column("Landing")
    table.add_column("Class")
    table.add_column("Current")
    table.add_column("Compatible")
    table.add_column("Recommended")
    table.add_column("Slope %", justify="right")
    table.add_column("Roughness", justify="right")
    table.add_column("Canopy %", justify="right")
    table.add_column("Fallbacks")
    for row in rows:
        table.add_row(
            row.block_id,
            row.landing_id,
            row.terrain_class,
            row.current_system_id or "—",
            "—"
            if row.current_system_compatible is None
            else ("yes" if row.current_system_compatible else "NO"),
            row.recommended_system_id,
            f"{row.slope_percent:.1f}",
            f"{row.roughness_m:.3f}",
            "—" if row.canopy_cover_percent is None else f"{row.canopy_cover_percent:.1f}",
            ", ".join(row.fallbacks) or "—",
        )
    console.print(table)
    console.print("Cost multipliers are advisory and are not applied by the solver in P14.4.")


@lidar_app.command("map")
def lidar_map(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML with a pinned bundle."),
    bundle: Path = typer.Argument(..., help="FEMIC LidarBC bundle directory."),
    product: list[str] | None = typer.Option(
        None,
        "--product",
        help="Repeatable FIELD=PRODUCT mapping, e.g. slope_percent=slope. Known products map automatically when omitted.",
    ),
    statistic: str = typer.Option(
        "mean", "--statistic", help="Aggregation: mean, p95, min, or max."
    ),
    include_blocks: bool = typer.Option(True, "--include-blocks/--no-include-blocks"),
    include_landings: bool = typer.Option(True, "--include-landings/--no-include-landings"),
    roads_geojson: Path | None = typer.Option(
        None, "--roads-geojson", help="Optional road support polygons."
    ),
    road_id_field: str = typer.Option("road_id", "--road-id-field"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print rows without writing the scenario."
    ),
) -> None:
    """Summarize FEMIC terrain/canopy products into scenario lidar_support rows."""
    products: dict[str, str] | None = None
    if product:
        products = {}
        for item in product:
            if "=" not in item:
                typer.echo(f"Expected FIELD=PRODUCT, got {item!r}", err=True)
                raise typer.Exit(1)
            field, product_name = (part.strip() for part in item.split("=", 1))
            if not field or not product_name:
                typer.echo(f"Expected FIELD=PRODUCT, got {item!r}", err=True)
                raise typer.Exit(1)
            if product_name in products and products[product_name] != field:
                typer.echo(f"Product {product_name!r} mapped to two fields", err=True)
                raise typer.Exit(1)
            products[product_name] = field
    try:
        result = map_femic_lidar_to_scenario(
            scenario,
            bundle,
            products=products,
            statistic=statistic,
            include_blocks=include_blocks,
            include_landings=include_landings,
            roads_geojson=roads_geojson,
            road_id_field=road_id_field,
            dry_run=dry_run,
        )
    except FemicLidarMappingError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result.to_dict(), indent=2))


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
