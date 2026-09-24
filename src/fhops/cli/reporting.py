"""Report-generation CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from fhops.planning.tactical_operational.scenario import write_tactical_report

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
