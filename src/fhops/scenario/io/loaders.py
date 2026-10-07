"""Scenario loading utilities (YAML metadata + CSV tables)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import pandas as pd
import yaml
from pydantic import TypeAdapter

from fhops.scenario.contract.models import (
    Block,
    CalendarEntry,
    CrewAssignment,
    GeoMetadata,
    HarvestSystem,
    Landing,
    Machine,
    ObjectiveWeights,
    ProductionRate,
    RoadConstruction,
    Scenario,
    ScenarioInitialState,
    ScheduleLock,
    ShiftCalendarEntry,
)
from fhops.scenario.io.mobilisation import populate_mobilisation_distances
from fhops.scheduling.mobilisation import MobilisationConfig
from fhops.scheduling.timeline.models import TimelineConfig
from fhops.validation.ranges import validate_block_ranges

__all__ = ["load_scenario", "read_csv"]


def read_csv(path: Path) -> pd.DataFrame:
    """Load a CSV file using pandas with UTF-8 defaults."""
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


def _as_optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if pd.isna(cast("Any", value)):
        return None
    return str(value)


def _normalise_optional_block_fields(rows: list[dict[str, object]]) -> None:
    optional_fields = ("harvest_system_id", "salvage_processing_mode")
    for row in rows:
        for field in optional_fields:
            value = row.get(field)
            normalised = _as_optional_string(value)
            if normalised is None:
                row.pop(field, None)
            else:
                row[field] = normalised


def _normalise_road_rows(rows: list[dict[str, object]]) -> None:
    for row in rows:
        slug = _as_optional_string(row.get("machine_slug"))
        if slug is None:
            row.pop("machine_slug", None)
        else:
            row["machine_slug"] = slug
        profiles_value = row.get("soil_profile_ids")
        profiles_normalised = _as_optional_string(profiles_value)
        if profiles_normalised is None:
            row.pop("soil_profile_ids", None)
            continue
        parts = re.split(r"[|,]", profiles_normalised)
        cleaned = [part.strip() for part in parts if part.strip()]
        if cleaned:
            row["soil_profile_ids"] = cleaned
        else:
            row.pop("soil_profile_ids", None)


def load_scenario(yaml_path: str | Path) -> Scenario:
    """Load a Scenario from the YAML metadata + CSV bundle.

    Parameters
    ----------
    yaml_path:
        Path to the ``scenario.yaml`` file that references the component CSVs.

    Returns
    -------
    Scenario
        Fully validated Pydantic model ready to be converted into a
        :class:`fhops.scenario.contract.Problem`.

    Notes
    -----
    The loader performs several quality-of-life tasks that callers usually forget:

    * normalises optional string columns (e.g., ``harvest_system_id`` blanks → ``None``),
    * back-fills mobilisation distance matrices from ``*_block_distances.csv`` whenever present,
    * accepts inline YAML overrides for optional tables (road construction, shift calendar, crew map),
    * re-roots GeoJSON paths relative to the scenario directory,
    * ensures every optional extra (timeline, mobilisation config, objective weights) is copied into
      the resulting Scenario instance,
    * parses an optional inline ``initial_state`` mapping (see
      :class:`fhops.scenario.contract.ScenarioInitialState`) and validates it against the loaded
      blocks, machines, and harvest systems, and
    * re-validates the assembled scenario once all optional sections are attached, so YAML
      ``locked_assignments`` (machine/block/day/``shift_id`` checks, duplicates, day+shift mixes,
      blackout clashes), mobilisation, crew assignments, and ``initial_state`` get the same
      :class:`fhops.scenario.contract.Scenario` cross-validation as Python-constructed scenarios.
      Core tables (and the ``harvest_systems`` section, which block ``harvest_system_id``
      values are checked against together with the default registry) are validated first, so
      their errors are reported before optional-section errors.

    Examples
    --------
    An inline ``initial_state`` section in ``scenario.yaml``::

        initial_state:
          blocks:
            - block_id: B01
              role_remaining: {feller_buncher: 0.0}
              staged_inventory: {feller_buncher: 150.0}
          machines:
            - machine_id: H3
              last_block_id: B02

    Raises
    ------
    ValueError
        (Pydantic ``ValidationError``) when any table, the ``harvest_systems``,
        ``locked_assignments`` or ``initial_state`` section, or the scenario cross-validation
        fails (including a block ``harvest_system_id`` that is neither in ``harvest_systems`` nor
        in :func:`fhops.scheduling.systems.default_system_registry`).
    """
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

    blocks_raw = cast(list[dict[str, object]], read_csv(require("blocks")).to_dict("records"))
    _normalise_optional_block_fields(blocks_raw)
    blocks = TypeAdapter(list[Block]).validate_python(blocks_raw)
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
    road_construction = None
    if "road_construction" in data_section:
        road_rows = cast(
            list[dict[str, object]], read_csv(require("road_construction")).to_dict("records")
        )
        _normalise_road_rows(road_rows)
        road_construction = TypeAdapter(list[RoadConstruction]).validate_python(road_rows)
    elif "road_construction" in meta:
        road_construction = TypeAdapter(list[RoadConstruction]).validate_python(
            meta["road_construction"]
        )
    shift_calendar = None
    if "shift_calendar" in data_section:
        shift_calendar = TypeAdapter(list[ShiftCalendarEntry]).validate_python(
            read_csv(require("shift_calendar")).to_dict("records")
        )
    elif "shift_calendar" in meta:
        shift_calendar = TypeAdapter(list[ShiftCalendarEntry]).validate_python(
            meta["shift_calendar"]
        )

    harvest_systems_payload: dict[str, object] | None = None
    if "harvest_systems" in data_section:
        harvest_systems_path = require("harvest_systems")
        with harvest_systems_path.open("r", encoding="utf-8") as handle:
            harvest_systems_payload = yaml.safe_load(handle) or {}
    elif "harvest_systems" in meta:
        harvest_systems_payload = meta["harvest_systems"]

    base_fields: dict[str, object] = {
        "name": meta["name"],
        "num_days": int(meta["num_days"]),
        "start_date": meta.get("start_date"),
        "blocks": blocks,
        "machines": machines,
        "landings": landings,
        "calendar": calendar,
        "shift_calendar": shift_calendar,
        "production_rates": rates,
    }
    # Harvest systems are validated with the core tables: block ``harvest_system_id`` values are
    # checked against them (plus the default registry).
    if harvest_systems_payload is not None:
        base_fields["harvest_systems"] = TypeAdapter(dict[str, HarvestSystem]).validate_python(
            harvest_systems_payload
        )
    # Validate the core tables first so their errors surface before optional-section errors.
    base_scenario = Scenario.model_validate(base_fields)

    # Optional sections are collected and the Scenario is re-validated with all of them at once, so
    # YAML locks (incl. ``shift_id`` rules and blackout clashes), timeline, mobilisation, crew
    # maps, and the initial state go through ``Scenario`` cross-validation.
    # (Attaching them with ``model_copy(update=...)`` would skip validation, as FHOPS <= 1.0.0 did.)
    extras: dict[str, object] = {}
    if road_construction is not None:
        extras["road_construction"] = road_construction

    mobilisation = None
    if "mobilisation" in meta:
        mobilisation = TypeAdapter(MobilisationConfig).validate_python(meta["mobilisation"])

    mobilisation = populate_mobilisation_distances(
        root,
        base_scenario.name,
        data_section,
        mobilisation,
    )
    if mobilisation is not None:
        extras["mobilisation"] = mobilisation

    if "timeline" in meta:
        extras["timeline"] = TypeAdapter(TimelineConfig).validate_python(meta["timeline"])

    if "crew_assignments" in data_section:
        crew_df = read_csv(require("crew_assignments"))
        extras["crew_assignments"] = TypeAdapter(list[CrewAssignment]).validate_python(
            crew_df.to_dict("records")
        )

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
        extras["geo"] = GeoMetadata(
            block_geojson=block_geo_ref,
            landing_geojson=landing_geo_ref,
            crs=geo_crs,
        )

    if "locked_assignments" in meta:
        extras["locked_assignments"] = TypeAdapter(list[ScheduleLock]).validate_python(
            meta["locked_assignments"]
        )

    if "objective_weights" in meta:
        extras["objective_weights"] = TypeAdapter(ObjectiveWeights).validate_python(
            meta["objective_weights"]
        )

    if meta.get("initial_state") is not None:
        extras["initial_state"] = TypeAdapter(ScenarioInitialState).validate_python(
            meta["initial_state"]
        )

    scenario = base_scenario
    if extras:
        scenario = Scenario.model_validate({**base_fields, **extras})

    _emit_block_range_warnings(cast(list[dict[str, object]], blocks_raw), scenario.name)
    return scenario


def _emit_block_range_warnings(block_rows: list[dict[str, object]], scenario_name: str) -> None:
    for row in block_rows:
        block_id = str(row.get("id"))
        stem_size = row.get("avg_stem_size") or row.get("stem_size") or row.get("mean_stem_size")
        volume = row.get("volume_per_ha") or row.get("avg_volume_per_ha")
        density = row.get("stem_density")
        slope = row.get("ground_slope") or row.get("slope_percent") or row.get("slope")
        warnings = validate_block_ranges(
            block_id=block_id,
            stem_size=_coerce_float(stem_size),
            volume_per_ha=_coerce_float(volume),
            stem_density=_coerce_float(density),
            ground_slope=_coerce_float(slope),
        )
        for msg in warnings:
            print(f"[scenario:{scenario_name}] {msg}")


def _coerce_float(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None
