"""Scenario loading utilities (YAML metadata + CSV tables)."""

from __future__ import annotations

import json
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
    ObjectiveWeights,
    ProductionRate,
    Scenario,
    ScheduleLock,
)
from fhops.scenario.io.mobilisation import populate_mobilisation_distances
from fhops.scheduling.timeline.models import TimelineConfig

__all__ = ["load_scenario", "read_csv"]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _resolve_path(root: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _validate_geojson(path: Path, expected_key: str, expected_ids: set[str], root: Path) -> str:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("type") != "FeatureCollection":
        raise ValueError(f"GeoJSON {path} must be a FeatureCollection")
    features = data.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError(f"GeoJSON {path} must contain feature entries")
    seen: set[str] = set()
    for feature in features:
        props = feature.get("properties") or {}
        fid = props.get(expected_key) or feature.get("id")
        if fid is None:
            raise ValueError(f"GeoJSON {path} missing '{expected_key}' property on feature")
        if fid not in expected_ids:
            raise ValueError(f"GeoJSON {path} feature id '{fid}' not found in scenario IDs")
        seen.add(fid)
    missing = expected_ids - seen
    if missing:
        raise ValueError(f"GeoJSON {path} missing features for ids: {sorted(missing)}")
    try:
        return str(path.relative_to(root))
    except ValueError:  # pragma: no cover
        return str(path)


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

    block_geo = meta.get("geo_block_path") or data_section.get("geo_block_path")
    landing_geo = meta.get("geo_landing_path") or data_section.get("geo_landing_path")
    geo_crs = meta.get("geo_crs") or data_section.get("geo_crs")

    block_geo_path = _resolve_path(root, block_geo)
    landing_geo_path = _resolve_path(root, landing_geo)

    block_geo_ref = None
    landing_geo_ref = None
    if block_geo_path is not None:
        block_ids = {block.id for block in blocks}
        block_geo_ref = _validate_geojson(block_geo_path, "block_id", block_ids, root)
    if landing_geo_path is not None:
        landing_ids = {landing.id for landing in landings}
        landing_geo_ref = _validate_geojson(landing_geo_path, "landing_id", landing_ids, root)

    if block_geo_ref or landing_geo_ref or geo_crs:
        geo_metadata = GeoMetadata(
            block_geojson=block_geo_ref,
            landing_geojson=landing_geo_ref,
            crs=geo_crs,
        )
        scenario = scenario.model_copy(update={"geo": geo_metadata})

    if "locked_assignments" in meta:
        locks = TypeAdapter(list[ScheduleLock]).validate_python(meta["locked_assignments"])
        scenario = scenario.model_copy(update={"locked_assignments": locks})

    if "objective_weights" in meta:
        weights = TypeAdapter(ObjectiveWeights).validate_python(meta["objective_weights"])
        scenario = scenario.model_copy(update={"objective_weights": weights})

    return scenario
