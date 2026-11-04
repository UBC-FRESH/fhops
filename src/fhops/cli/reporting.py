"""Report-generation CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from fhops.planning.tactical_operational.scenario import write_tactical_report
from fhops.salvage import DEFAULT_CURVE_ID, build_salvage_report, write_salvage_report

console = Console()
report_app = typer.Typer(add_completion=False, no_args_is_help=True)


@report_app.command("tactical")
def tactical_report(
    result_json: Path = typer.Argument(
        ..., help="JSON summary from `fhops plan tactical-operational`."
    ),
    out_dir: Path = typer.Option(
        ...,
        "--out-dir",
        help="Directory for normalized report tables.",
    ),
    formats: Annotated[
        str,
        typer.Option("--formats", help="Comma-separated report formats: csv,markdown,parquet."),
    ] = "csv,markdown",
) -> None:
    """Write normalized CSV/Parquet/Markdown tables from a tactical solve summary."""
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    written = write_tactical_report(payload, out_dir, formats=formats)
    console.print(f"Wrote {len(written)} tactical report artifacts to {out_dir}")


@report_app.command("salvage-shelf-life")
def salvage_shelf_life(
    scenario: Path = typer.Argument(..., help="FHOPS scenario.yaml defining the blocks to report."),
    storage_table: Path = typer.Argument(
        ...,
        help="CSV with block_id and years_since_disturbance (years since fire or tree death).",
    ),
    curve_id: str = typer.Option(
        DEFAULT_CURVE_ID,
        "--curve",
        help="Published retention curve id from the packaged salvage decay library.",
    ),
    value_per_m3: float | None = typer.Option(
        None,
        "--value-per-m3",
        help=(
            "Optional caller-supplied value per retained cubic metre. Omit to report volume only; "
            "this is not a price forecast."
        ),
    ),
    out_dir: Path | None = typer.Option(
        None,
        "--out-dir",
        help="Optional directory for salvage_shelf_life.csv and salvage_shelf_life.md.",
    ),
) -> None:
    """Report salvage volume retention and advisory product windows by block age.

    The command joins an explicit age table to scenario blocks and applies a
    published retention curve. It is read-only: no schedule, objective,
    constraint, heuristic, or solver is changed. ``Block.work_required`` is used
    as the original volume, and any ``--value-per-m3`` is labelled as a caller
    assumption rather than a price forecast.
    """

    try:
        report = build_salvage_report(
            scenario,
            storage_table,
            curve_id=curve_id,
            value_per_m3=value_per_m3,
        )
    except (ValueError, KeyError, FileNotFoundError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    display_columns = [
        "block_id",
        "years_since_disturbance",
        "salvage_processing_mode",
        "retention_fraction",
        "original_volume_m3",
        "retained_volume_m3",
        "eligible_products",
        "retained_value",
    ]
    console.print(report.frame.loc[:, display_columns].to_string(index=False))
    console.print(
        f"\nCurve: {report.curve.curve_id} — {report.curve.name}\n"
        f"Source: {report.curve.source.citation} <{report.curve.source.url}>\n"
        f"Boundary: {report.curve.source.boundary}\n"
        f"Totals: {report.total_original_volume_m3:.2f} m³ original, "
        f"{report.total_retained_volume_m3:.2f} m³ retained."
    )
    if report.blocks_without_salvage_mode:
        console.print(
            "\n[yellow]Caveat:[/yellow] blocks without salvage_processing_mode: "
            + ", ".join(report.blocks_without_salvage_mode)
        )
    console.print(
        "\nRead-only report. No objective, constraint, schedule, heuristic, or solver was changed. "
        "The curve is a published reference curve, not a BC-specific or species-specific "
        "operational curve."
    )

    if out_dir is not None:
        written = write_salvage_report(report, out_dir)
        console.print(f"Wrote {written['csv']} and {written['markdown']}")
