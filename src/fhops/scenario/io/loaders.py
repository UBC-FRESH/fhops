"""Scenario loading utilities (YAML metadata + CSV tables)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml
from pydantic import TypeAdapter

from fhops.scenario.contract.models import (
    Block,
    CalendarEntry,
    CrewAssignment,
    GeoMetadata,
    Landing,
    Machine,
    ProductionRate,
    Scenario,
)
from fhops.scenario.io.mobilisation import populate_mobilisation_distances
from fhops.scheduling.timeline.models import TimelineConfig

__all__ = ["load_scenario", "read_csv"]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def load_scenario(yaml_path: str | Path) -> Scenario:
    base_path = Path(yaml_path).resolve()
    with base_path.open("r", encoding="utf-8") as handle:
        meta = yaml.safe_load(handle)
    root = base_path.parent
    data_section = meta.get("data", {})

    def require(name: str) -> Path:
        candidate = root / data_section[name]
        if not candidate.exists():  # pragma: no cover - defensive
            raise FileNotFoundError(candidate)
        return candidate

    blocks = TypeAdapter(list[Block]).validate_python(
        read_csv(require("blocks")).to_dict("records")
    )
    machines = TypeAdapter(list[Machine]).validate_python(
        read_csv(require("machines")).to_dict("records")
    )
    landings = TypeAdapter(list[Landing]).validate_python(
        read_csv(require("landings")).to_dict("records")
    )
    calendar = TypeAdapter(list[CalendarEntry]).validate_python(
        read_csv(require("calendar")).to_dict("records")
    )
    rates = TypeAdapter(list[ProductionRate]).validate_python(
        read_csv(require("prod_rates")).to_dict("records")
    )

    scenario = Scenario(
        name=meta["name"],
        num_days=int(meta["num_days"]),
        start_date=meta.get("start_date"),
        blocks=blocks,
        machines=machines,
        landings=landings,
        calendar=calendar,
        production_rates=rates,
    )

    mobilisation = populate_mobilisation_distances(
        root,
        scenario.name,
        data_section,
        scenario.mobilisation,
    )
    if mobilisation is not None and mobilisation != scenario.mobilisation:
        scenario = scenario.model_copy(update={"mobilisation": mobilisation})

    if "timeline" in meta:
        timeline = TypeAdapter(TimelineConfig).validate_python(meta["timeline"])
        scenario = scenario.model_copy(update={"timeline": timeline})

    if "crew_assignments" in data_section:
        crew_df = read_csv(require("crew_assignments"))
        crew_assignments = TypeAdapter(list[CrewAssignment]).validate_python(
            crew_df.to_dict("records")
        )
        scenario = scenario.model_copy(update={"crew_assignments": crew_assignments})

    if "geo" in data_section:
        geo_path = root / data_section["geo"]
        try:
            geo_ref = str(geo_path.relative_to(root))
        except ValueError:  # pragma: no cover - fallback for absolute paths
            geo_ref = str(geo_path)
        geo_metadata = GeoMetadata(block_geojson=geo_ref, crs=meta.get("geo_crs"))
        scenario = scenario.model_copy(update={"geo": geo_metadata})

    return scenario
