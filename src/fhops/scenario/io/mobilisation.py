"""Helpers for populating mobilisation distances when loading scenarios."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from fhops.scheduling.mobilisation import BlockDistance, MobilisationConfig


def populate_mobilisation_distances(
    base_path: Path,
    scenario_name: str,
    data_section: Mapping[str, str] | None,
    mobilisation: MobilisationConfig | None,
) -> MobilisationConfig | None:
    """Ensure mobilisation config has distances loaded from CSV when available."""

    if mobilisation is None:
        return None
    if mobilisation.distances:
        return mobilisation

    candidate_paths: list[Path] = []

    if mobilisation.distance_csv:
        candidate_paths.append(base_path / mobilisation.distance_csv)

    if data_section and "mobilisation_distances" in data_section:
        candidate_paths.append(base_path / data_section["mobilisation_distances"])

    slug = scenario_name.lower().replace(" ", "_")
    candidate_paths.append(base_path / f"{slug}_block_distances.csv")
    candidate_paths.append(base_path / "mobilisation_distances.csv")

    path_to_use: Path | None = None
    for path in candidate_paths:
        if path is not None and path.exists():
            path_to_use = path
            break

    if path_to_use is None:
        return mobilisation

    df = pd.read_csv(path_to_use)
    required = {"from_block", "to_block", "distance_m"}
    if not required.issubset(df.columns):
        raise ValueError(
            f"Mobilisation distance file {path_to_use} is missing required columns {required}."
        )

    distances = [
        BlockDistance(
            from_block=str(row["from_block"]),
            to_block=str(row["to_block"]),
            distance_m=float(row["distance_m"]),
        )
        for _, row in df.iterrows()
    ]

    try:
        relative_path = str(path_to_use.relative_to(base_path))
    except ValueError:  # pragma: no cover - path not relative
        relative_path = str(path_to_use)

    return mobilisation.model_copy(update={"distances": distances, "distance_csv": relative_path})


__all__ = ["populate_mobilisation_distances"]
