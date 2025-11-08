"""CLI helpers for geospatial preprocessing."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from fhops.scheduling.geospatial import compute_distance_matrix, load_block_geometries

geospatial_app = typer.Typer(help="Geospatial preprocessing utilities.")


@geospatial_app.command("distances")
def compute_distances(
    geojson: Annotated[Path, typer.Argument(help="Path to block GeoJSON with 'block_id' column.")],
    output: Annotated[Path, typer.Option("--out", help="CSV file to write distance matrix")],
) -> None:
    """Compute centroid-to-centroid distances between blocks (metres)."""
    geometries = load_block_geometries(geojson)
    matrix = compute_distance_matrix(geometries)
    records = [
        {"from_block": src, "to_block": dst, "distance_m": dist}
        for (src, dst), dist in matrix.items()
        if src != dst
    ]
    df = pd.DataFrame(records)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    typer.echo(f"Wrote {len(df)} distance entries to {output}")
