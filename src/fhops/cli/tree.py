"""Tree-inventory CLI commands for tree-scale FHOPS workflows."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from fhops.tree_inventory import validate_tree_inventory

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
