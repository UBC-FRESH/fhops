"""Tree-inventory CLI commands for tree-scale FHOPS workflows."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from fhops.stem import (
    DEFAULT_FORM_FACTOR,
    DEFAULT_LOG_LENGTH_M,
    DEFAULT_SAWLOG_MIN_DBH_CM,
    DEFAULT_STUMP_HEIGHT_M,
    ReferenceStemModel,
    StemModelError,
    build_stem_inventory,
    write_stem_inventory,
)
from fhops.tree_inventory import validate_tree_inventory
from fhops.tree_mapping import (
    DEFAULT_RECONCILIATION_TOLERANCE,
    TreeInventoryMappingError,
    TreeInventoryRegistrationError,
    map_tree_inventory,
    register_tree_inventory,
    write_tree_mapping,
)

tree_app = typer.Typer(add_completion=False, no_args_is_help=True)
inventory_app = typer.Typer(add_completion=False, no_args_is_help=True)
tree_app.add_typer(
    inventory_app,
    name="inventory",
    help="Validate individual-tree inventories for tree-scale simulation.",
)


@inventory_app.command("validate")
def tree_inventory_validate(
    inventory: Path = typer.Argument(..., help="Tree inventory CSV."),
    metadata: Path | None = typer.Option(None, "--metadata", help="Tree inventory metadata JSON."),
    block: list[str] | None = typer.Option(
        None, "--block", help="Known block id. Repeat for multiple blocks."
    ),
) -> None:
    """Validate a tree inventory without modifying it."""
    report = validate_tree_inventory(
        inventory,
        metadata_path=metadata,
        block_ids=set(block) if block else None,
    )
    typer.echo(json.dumps(report.to_dict(), indent=2))
    if not report.is_valid:
        raise typer.Exit(1)


@tree_app.command("register")
def tree_register(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML."),
    inventory: Path = typer.Argument(..., help="Tree inventory CSV."),
    metadata: Path | None = typer.Option(None, "--metadata", help="Tree inventory metadata JSON."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print the pin without writing the scenario."
    ),
) -> None:
    """Validate and pin a tree inventory in a scenario."""
    try:
        result = register_tree_inventory(
            scenario,
            inventory,
            metadata_path=metadata,
            dry_run=dry_run,
        )
    except TreeInventoryRegistrationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result.to_dict(), indent=2))


@tree_app.command("map")
def tree_map(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML with a tree-inventory pin."),
    out: Path | None = typer.Option(
        None, "--out", help="Mapping output directory. Print only when omitted."
    ),
    tolerance: float = typer.Option(
        DEFAULT_RECONCILIATION_TOLERANCE,
        "--tolerance",
        help="Relative tolerance for stem-density and volume reconciliation.",
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Refuse when any block reconciliation warns."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print the map without writing outputs."
    ),
) -> None:
    """Map a pinned tree inventory to blocks and reconcile block evidence."""
    try:
        mapping = map_tree_inventory(
            scenario,
            tolerance=tolerance,
            require_reconciled=strict,
        )
        paths = None if dry_run or out is None else write_tree_mapping(mapping, out)
    except TreeInventoryMappingError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    payload = mapping.to_dict()
    if paths is not None:
        payload["paths"] = {key: str(value) for key, value in paths.items()}
    typer.echo(json.dumps(payload, indent=2))


@tree_app.command("stems")
def tree_stems(
    scenario: Path = typer.Argument(..., help="FHOPS scenario YAML with a tree-inventory pin."),
    out: Path | None = typer.Option(
        None, "--out", help="Stem output directory. Print only when omitted."
    ),
    tolerance: float = typer.Option(
        DEFAULT_RECONCILIATION_TOLERANCE,
        "--tolerance",
        help="Relative tolerance for merchantable-volume reconciliation.",
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Refuse when a block volume reconciliation warns."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print the manifest without writing outputs."
    ),
    form_factor: float = typer.Option(
        DEFAULT_FORM_FACTOR, "--form-factor", help="Reference model form factor."
    ),
    log_length: float = typer.Option(
        DEFAULT_LOG_LENGTH_M, "--log-length", help="Target log length in metres."
    ),
    stump_height: float = typer.Option(
        DEFAULT_STUMP_HEIGHT_M, "--stump-height", help="Stump height in metres."
    ),
    sawlog_min_dbh: float = typer.Option(
        DEFAULT_SAWLOG_MIN_DBH_CM,
        "--sawlog-min-dbh",
        help="Minimum DBH in centimetres for the sawlog product class.",
    ),
) -> None:
    """Derive stem volumes and bucked logs for a pinned tree inventory."""
    try:
        model = ReferenceStemModel(
            form_factor=form_factor,
            log_length_m=log_length,
            stump_height_m=stump_height,
            sawlog_min_dbh_cm=sawlog_min_dbh,
        )
        result = build_stem_inventory(
            scenario,
            model=model,
            tolerance=tolerance,
            require_reconciled=strict,
        )
        paths = None if dry_run or out is None else write_stem_inventory(result, out)
    except StemModelError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    payload = result.to_dict()
    if paths is not None:
        payload["paths"] = {key: str(value) for key, value in paths.items()}
    typer.echo(json.dumps(payload, indent=2))
