"""Screen one FHOPS assignments schedule against a FEMIC hydrology bundle.

The screen is a one-schedule, read-only planning check. It uses an explicit
crosswalk and a schedule-bound exposure table; it does not run a process model,
create a flood map, or feed the optimizer.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fhops.scenario.hydrology import (
    FemicHydrologyBundle,
    FemicHydrologyError,
    FemicHydrologyReadiness,
    assess_femic_hydrology_readiness,
    load_femic_hydrology_bundle,
    read_femic_hydrology_domain,
    read_femic_hydrology_flood_risk,
    read_femic_hydrology_response_surface,
)
from fhops.scenario.hydrology_exposure import (
    FemicHydrologyExposureError,
    load_hydrology_exposure,
)
from fhops.scenario.hydrology_mapping import (
    FemicHydrologyMappingError,
    load_hydrology_mapping,
)
from fhops.scenario.io import load_scenario

HYDROLOGY_SCREEN_SCHEMA = "fhops.hydrology.screen.v1"
HYDROLOGY_READINESS_POLICIES: tuple[str, ...] = (
    "allow_provisional",
    "require_reviewed",
    "require_ready",
)

__all__ = [
    "FemicHydrologyScreenError",
    "HYDROLOGY_READINESS_POLICIES",
    "HydrologyScreen",
    "enforce_hydrology_readiness",
    "screen_fhops_hydrology",
    "write_hydrology_screen",
]


class FemicHydrologyScreenError(RuntimeError):
    """A schedule cannot be screened against the hydrology evidence."""


@dataclass(frozen=True)
class HydrologyScreen:
    """One-schedule hydrology screening result.

    Attributes
    ----------
    screen_id : str
        Deterministic screening identifier.
    generated_utc : str
        Screening timestamp.
    scenario_path : Path
        Scenario YAML.
    bundle_id : str
        FEMIC bundle identifier.
    bundle_version : str
        FEMIC bundle version.
    manifest_sha256 : str
        FEMIC manifest digest.
    mapping_id : str
        Crosswalk mapping identifier.
    exposure_id : str
        Exposure table identifier.
    schedule_sha256 : str
        Assignments CSV digest.
    readiness_status : str
        Bundle readiness state at screening time.
    policy : str
        Readiness policy applied.
    rows : tuple[dict[str, object], ...]
        Inside-domain screening rows.
    refusals : tuple[dict[str, object], ...]
        Refused schedule/watershed/return-period combinations.
    coverage : dict[str, object]
        Period, watershed, block, and row coverage.
    warnings : tuple[str, ...]
        Non-fatal observations.
    caveats : tuple[str, ...]
        Screening-only caveats.
    """

    screen_id: str
    generated_utc: str
    scenario_path: Path
    bundle_id: str
    bundle_version: str
    manifest_sha256: str
    mapping_id: str
    exposure_id: str
    schedule_sha256: str
    readiness_status: str
    policy: str
    rows: tuple[dict[str, object], ...]
    refusals: tuple[dict[str, object], ...]
    coverage: dict[str, object]
    warnings: tuple[str, ...]
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the screening manifest as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Identity, readiness, rows, refusals, coverage, and caveats.
        """
        return {
            "schema_version": HYDROLOGY_SCREEN_SCHEMA,
            "screen_id": self.screen_id,
            "generated_utc": self.generated_utc,
            "scenario_path": str(self.scenario_path),
            "bundle_id": self.bundle_id,
            "bundle_version": self.bundle_version,
            "manifest_sha256": self.manifest_sha256,
            "mapping_id": self.mapping_id,
            "exposure_id": self.exposure_id,
            "schedule_sha256": self.schedule_sha256,
            "readiness_status": self.readiness_status,
            "policy": self.policy,
            "row_count": len(self.rows),
            "refusal_count": len(self.refusals),
            "rows": list(self.rows),
            "refusals": list(self.refusals),
            "coverage": self.coverage,
            "warnings": list(self.warnings),
            "caveats": list(self.caveats),
        }


def enforce_hydrology_readiness(
    readiness: FemicHydrologyReadiness,
    *,
    policy: str = "require_reviewed",
) -> None:
    """Enforce a readiness policy for one-schedule screening.

    Parameters
    ----------
    readiness : FemicHydrologyReadiness
        Bundle readiness report.
    policy : str, optional
        ``allow_provisional``, ``require_reviewed``, or ``require_ready``.

    Raises
    ------
    FemicHydrologyScreenError
        If the policy is unknown or the evidence is insufficient.
    """
    if policy not in HYDROLOGY_READINESS_POLICIES:
        raise FemicHydrologyScreenError(f"Unsupported readiness policy {policy!r}.")
    if readiness.status == "blocked":
        raise FemicHydrologyScreenError(
            "Tail-check failures block hydrology screening; an explicit policy "
            "override is not supported."
        )
    if policy == "allow_provisional":
        return
    if policy == "require_reviewed" and readiness.status not in (
        "ready",
        "conditionally_ready",
    ):
        raise FemicHydrologyScreenError(f"Readiness status {readiness.status!r} is not reviewed.")
    if policy == "require_ready" and readiness.status != "ready":
        raise FemicHydrologyScreenError(
            f"Readiness status {readiness.status!r} is not fully ready."
        )


def screen_fhops_hydrology(
    scenario_path: str | Path,
    bundle_dir: str | Path,
    mapping_path: str | Path,
    schedule_path: str | Path,
    exposure_path: str | Path,
    *,
    policy: str = "require_reviewed",
    scenario_tolerance: float = 0.05,
    allow_refused: bool = False,
    generated_utc: str | None = None,
) -> HydrologyScreen:
    """Screen one FHOPS assignments schedule against a hydrology bundle.

    Parameters
    ----------
    scenario_path : str | Path
        FHOPS scenario YAML with a hydrology pin and block geometry.
    bundle_dir : str | Path
        FEMIC hydrology bundle directory or manifest.
    mapping_path : str | Path
        Mapping directory or manifest from ``scenario hydrology map``.
    schedule_path : str | Path
        FHOPS assignments CSV with ``block_id`` and ``day``.
    exposure_path : str | Path
        Schedule-bound exposure JSON.
    policy : str, optional
        Readiness policy. Defaults to ``require_reviewed``.
    scenario_tolerance : float, optional
        Maximum feature difference for response-scenario selection.
    allow_refused : bool, optional
        Return inside-domain rows plus refusals instead of failing.
    generated_utc : str | None, optional
        Screening timestamp.

    Returns
    -------
    HydrologyScreen
        Screening rows, refusals, coverage, warnings, and caveats.

    Raises
    ------
    FemicHydrologyScreenError
        If evidence is missing, the policy fails, the schedule is invalid, or a
        refusal occurs without ``allow_refused``.
    """
    if scenario_tolerance <= 0 or not math.isfinite(scenario_tolerance):
        raise FemicHydrologyScreenError("Scenario tolerance must be positive and finite.")
    scenario_file = Path(scenario_path).expanduser().resolve()
    schedule_file = Path(schedule_path).expanduser().resolve()
    try:
        scenario = load_scenario(scenario_file)
        bundle = load_femic_hydrology_bundle(Path(bundle_dir))
        mapping = load_hydrology_mapping(Path(mapping_path))
        exposure = load_hydrology_exposure(
            Path(exposure_path),
            schedule_path=schedule_file,
        )
    except (
        FemicHydrologyError,
        FemicHydrologyExposureError,
        FemicHydrologyMappingError,
        ValueError,
        FileNotFoundError,
    ) as exc:
        raise FemicHydrologyScreenError(str(exc)) from exc
    _require_scenario_pin(scenario, bundle)
    if (
        mapping.bundle_id != bundle.bundle_id
        or mapping.bundle_version != bundle.bundle_version
        or mapping.manifest_sha256 != bundle.manifest_sha256
    ):
        raise FemicHydrologyScreenError(
            "Hydrology mapping was built from a different FEMIC bundle pin."
        )
    readiness = assess_femic_hydrology_readiness(bundle)
    enforce_hydrology_readiness(readiness, policy=policy)
    if policy != "allow_provisional":
        if mapping.review_status != "reviewed":
            raise FemicHydrologyScreenError(
                f"Mapping review status {mapping.review_status!r} is not reviewed."
            )
        if exposure.review_status != "reviewed":
            raise FemicHydrologyScreenError(
                f"Exposure review status {exposure.review_status!r} is not reviewed."
            )
    schedule = _read_schedule(schedule_file)
    block_areas = _block_areas(scenario, scenario_file)
    block_mapping = {row.support_id: row for row in mapping.rows if row.support_unit == "block"}
    watershed_areas = _watershed_areas(bundle)
    scenarios = _response_scenarios(bundle)
    surface_rows = _surface_rows(bundle)
    risk_rows = _risk_rows(bundle)
    risk_by_watershed: dict[str, list[dict[str, object]]] = {}
    for row in risk_rows:
        risk_by_watershed.setdefault(str(row["watershed_id"]), []).append(row)
    warnings: list[str] = []
    if mapping.review_status != "reviewed":
        warnings.append("Mapping is not reviewed; screening is provisional.")
    if exposure.review_status != "reviewed":
        warnings.append("Exposure is not reviewed; screening is provisional.")
    if readiness.status != "ready":
        warnings.append(f"Bundle readiness is {readiness.status!r}.")
    rows: list[dict[str, object]] = []
    refusals: list[dict[str, object]] = []
    screened_watersheds: set[str] = set()
    valid_blocks: set[str] = set()
    invalid_blocks: set[str] = set()
    for day in sorted(schedule):
        period = day - 1
        for block_id in sorted(schedule[day]):
            if block_id in valid_blocks or block_id in invalid_blocks:
                continue
            mapping_row = block_mapping.get(block_id)
            if mapping_row is None:
                invalid_blocks.add(block_id)
                refusals.append(
                    _refusal(
                        period,
                        day,
                        None,
                        None,
                        None,
                        f"Scheduled block {block_id!r} has no hydraulic mapping.",
                        block_id=block_id,
                    )
                )
                continue
            area = block_areas.get(block_id)
            if area is None or area <= 0:
                invalid_blocks.add(block_id)
                refusals.append(
                    _refusal(
                        period,
                        day,
                        mapping_row.watershed_id,
                        None,
                        None,
                        f"Block {block_id!r} has no positive area evidence.",
                        block_id=block_id,
                    )
                )
                continue
            valid_blocks.add(block_id)
        area_by_watershed: dict[str, float] = {}
        for block_id in valid_blocks:
            mapping_row = block_mapping[block_id]
            area = block_areas[block_id]
            area_by_watershed[mapping_row.watershed_id] = (
                area_by_watershed.get(mapping_row.watershed_id, 0.0) + area
            )
        for watershed_id in sorted(area_by_watershed):
            screened_watersheds.add(watershed_id)
            watershed_area = watershed_areas.get(watershed_id)
            if watershed_area is None or watershed_area <= 0:
                refusals.append(
                    _refusal(
                        period,
                        day,
                        watershed_id,
                        None,
                        None,
                        "FEMIC domain has no positive watershed area.",
                    )
                )
                continue
            harvest_fraction = area_by_watershed[watershed_id] / watershed_area
            if harvest_fraction > 1.0:
                refusals.append(
                    _refusal(
                        period,
                        day,
                        watershed_id,
                        None,
                        None,
                        "Cumulative harvest fraction exceeds 1.0.",
                    )
                )
                continue
            if watershed_id not in exposure.watershed_ids or period not in exposure.periods:
                refusals.append(
                    _refusal(
                        period,
                        day,
                        watershed_id,
                        None,
                        None,
                        "Exposure has no declared row for this watershed/period.",
                    )
                )
                continue
            features = exposure.features_for(
                watershed_id,
                period,
                watershed_area_ha=watershed_area,
            )
            features["harvest_fraction"] = harvest_fraction
            selected = _select_scenario(scenarios, features, scenario_tolerance)
            if selected is None:
                refusals.append(
                    _refusal(
                        period,
                        day,
                        watershed_id,
                        None,
                        None,
                        "No response-surface scenario is inside the feature tolerance.",
                    )
                )
                continue
            scenario_name, scenario_covariates = selected
            watershed_risk = risk_by_watershed.get(watershed_id, [])
            if not watershed_risk:
                refusals.append(
                    _refusal(
                        period,
                        day,
                        watershed_id,
                        None,
                        None,
                        "No flood-risk row exists for this watershed.",
                    )
                )
                continue
            for risk in watershed_risk:
                return_period = _float(risk.get("return_period"), "return_period")
                surface = surface_rows.get((scenario_name, return_period))
                if surface is None:
                    refusals.append(
                        _refusal(
                            period,
                            day,
                            watershed_id,
                            str(risk.get("receptor_id")),
                            return_period,
                            "Response surface has no row for the selected scenario/period.",
                        )
                    )
                    continue
                ratio = _float(surface.get("ratio"), "surface ratio")
                baseline = _float(risk.get("baseline_peak_flow_m3s"), "baseline_peak_flow_m3s")
                rows.append(
                    {
                        "period": period,
                        "day": day,
                        "watershed_id": watershed_id,
                        "receptor_id": str(risk.get("receptor_id")),
                        "return_period": return_period,
                        "harvested_area_ha": area_by_watershed[watershed_id],
                        "watershed_area_ha": watershed_area,
                        "harvest_fraction": harvest_fraction,
                        "scenario_name": scenario_name,
                        "scenario_covariates": dict(scenario_covariates),
                        **{
                            key: value
                            for key, value in features.items()
                            if key
                            in (
                                "road_built_km",
                                "road_used_km",
                                "road_decommissioned_km",
                                "culvert_count",
                                "culvert_exposed_count",
                                "road_built_density_km_per_km2",
                                "road_used_density_km_per_km2",
                                "road_decommissioned_density_km_per_km2",
                                "culvert_exposure_per_km2",
                            )
                        },
                        "response_ratio": ratio,
                        "baseline_peak_flow_m3s": baseline,
                        "screening_peak_flow_m3s": baseline * ratio,
                        "bundle_scenario_peak_flow_m3s": _optional_float(
                            risk.get("scenario_peak_flow_m3s")
                        ),
                        "exceedance_probability": _optional_float(
                            risk.get("exceedance_probability")
                        ),
                        "expected_annual_damage": _optional_float(
                            risk.get("expected_annual_damage")
                        ),
                    }
                )
    if refusals and not allow_refused:
        reasons = "; ".join(str(item["reason"]) for item in refusals[:3])
        raise FemicHydrologyScreenError(
            f"Schedule screening refused {len(refusals)} row(s): {reasons}"
        )
    if refusals:
        warnings.append(f"{len(refusals)} screening row(s) were refused.")
    timestamp = generated_utc or datetime.now(UTC).isoformat()
    material = {
        "bundle_id": bundle.bundle_id,
        "mapping_id": mapping.mapping_id,
        "exposure_id": exposure.exposure_id,
        "schedule_sha256": exposure.schedule_sha256,
        "rows": rows,
        "refusals": refusals,
        "policy": policy,
        "scenario_tolerance": scenario_tolerance,
    }
    screen_id = (
        "fhops-hydro-screen-"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
    )
    coverage = {
        "days": sorted(schedule),
        "periods": sorted({day - 1 for day in schedule}),
        "watersheds": sorted(screened_watersheds),
        "scheduled_blocks": sorted({block for blocks in schedule.values() for block in blocks}),
        "mapped_blocks": len(block_mapping),
        "screened_rows": len(rows),
        "refused_rows": len(refusals),
        "exposure_used": True,
    }
    return HydrologyScreen(
        screen_id=screen_id,
        generated_utc=timestamp,
        scenario_path=scenario_file,
        bundle_id=bundle.bundle_id,
        bundle_version=bundle.bundle_version,
        manifest_sha256=bundle.manifest_sha256,
        mapping_id=mapping.mapping_id,
        exposure_id=exposure.exposure_id,
        schedule_sha256=exposure.schedule_sha256,
        readiness_status=readiness.status,
        policy=policy,
        rows=tuple(rows),
        refusals=tuple(refusals),
        coverage=coverage,
        warnings=tuple(warnings),
        caveats=(
            "One-schedule screening only; not a process simulation or flood map.",
            "Response ratios and baseline flows come from the pinned FEMIC bundle.",
            "Exposure is an explicit schedule-bound input, not inferred from geometry.",
            "Hydrologist review and a real-watershed pilot remain required.",
        ),
    )


def write_hydrology_screen(screen: HydrologyScreen, out_dir: Path) -> dict[str, Path]:
    """Write screening rows and manifest.

    Parameters
    ----------
    screen : HydrologyScreen
        Screening result.
    out_dir : Path
        Output directory.

    Returns
    -------
    dict[str, Path]
        Paths keyed by ``rows`` and ``manifest``.
    """
    output = out_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows_path = output / "hydrology_screen.csv"
    columns = (
        "period",
        "day",
        "watershed_id",
        "receptor_id",
        "return_period",
        "harvested_area_ha",
        "watershed_area_ha",
        "harvest_fraction",
        "scenario_name",
        "road_built_km",
        "road_used_km",
        "road_decommissioned_km",
        "culvert_count",
        "culvert_exposed_count",
        "road_built_density_km_per_km2",
        "road_used_density_km_per_km2",
        "road_decommissioned_density_km_per_km2",
        "culvert_exposure_per_km2",
        "response_ratio",
        "baseline_peak_flow_m3s",
        "screening_peak_flow_m3s",
        "bundle_scenario_peak_flow_m3s",
        "exceedance_probability",
        "expected_annual_damage",
    )
    with rows_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(screen.rows)
    manifest_path = output / "hydrology_screen.json"
    manifest_path.write_text(
        json.dumps(screen.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"rows": rows_path, "manifest": manifest_path}


def _require_scenario_pin(scenario: object, bundle: FemicHydrologyBundle) -> None:
    pins = getattr(scenario, "hydrology_products", None) or []
    for pin in pins:
        if (pin.bundle_id, pin.bundle_version) == (bundle.bundle_id, bundle.bundle_version):
            if pin.manifest_sha256 == bundle.manifest_sha256:
                return
            raise FemicHydrologyScreenError(
                "Scenario hydrology pin has a different manifest checksum."
            )
    raise FemicHydrologyScreenError(
        f"Bundle {bundle.bundle_id}@{bundle.bundle_version} is not pinned in the scenario."
    )


def _read_schedule(path: Path) -> dict[int, set[str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not {"block_id", "day"} <= set(reader.fieldnames):
                raise FemicHydrologyScreenError(
                    "Assignments CSV requires block_id and day columns."
                )
            schedule: dict[int, set[str]] = {}
            for index, row in enumerate(reader, start=2):
                block_id = (row.get("block_id") or "").strip()
                day_text = (row.get("day") or "").strip()
                if not block_id:
                    raise FemicHydrologyScreenError(f"Assignments row {index} has no block_id.")
                try:
                    day = int(day_text)
                except ValueError as exc:
                    raise FemicHydrologyScreenError(
                        f"Assignments row {index} has an invalid day."
                    ) from exc
                if day < 1:
                    raise FemicHydrologyScreenError(f"Assignments row {index} day must be >= 1.")
                schedule.setdefault(day, set()).add(block_id)
    except OSError as exc:
        raise FemicHydrologyScreenError(f"Unable to read assignments CSV: {exc}") from exc
    if not schedule:
        raise FemicHydrologyScreenError("Assignments CSV contains no schedule rows.")
    return schedule


def _block_areas(scenario: object, scenario_path: Path) -> dict[str, float]:
    areas: dict[str, float] = {}
    geo = getattr(scenario, "geo", None)
    if geo is not None and getattr(geo, "block_geojson", None):
        path = Path(str(geo.block_geojson))
        if not path.is_absolute():
            path = scenario_path.parent / path
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FemicHydrologyScreenError(f"Unable to read block GeoJSON: {exc}") from exc
        for feature in payload.get("features", []):
            if not isinstance(feature, Mapping):
                continue
            props = feature.get("properties") or {}
            if not isinstance(props, Mapping):
                continue
            block_id = props.get("block_id") or feature.get("id")
            area = props.get("area_ha") or props.get("AREA_HA")
            if isinstance(block_id, str) and isinstance(area, (int, float)):
                areas[block_id] = float(area)
    for support in getattr(scenario, "lidar_support", None) or []:
        if support.support_unit != "block" or support.support_area_m2 is None:
            continue
        areas.setdefault(support.support_id, support.support_area_m2 / 10000.0)
    if not areas:
        raise FemicHydrologyScreenError(
            "Screening requires block area evidence from GeoJSON area_ha or LiDAR support."
        )
    return areas


def _watershed_areas(bundle: FemicHydrologyBundle) -> dict[str, float]:
    domain = read_femic_hydrology_domain(bundle)
    watersheds = domain.get("watersheds")
    if not isinstance(watersheds, list):
        raise FemicHydrologyScreenError("FEMIC domain watersheds must be a list.")
    result: dict[str, float] = {}
    for item in watersheds:
        if not isinstance(item, Mapping):
            continue
        watershed_id = item.get("watershed_id")
        area = item.get("area_km2")
        if isinstance(watershed_id, str) and isinstance(area, (int, float)) and area > 0:
            result[watershed_id] = float(area) * 100.0
    return result


def _response_scenarios(
    bundle: FemicHydrologyBundle,
) -> tuple[tuple[str, dict[str, float]], ...]:
    surface = read_femic_hydrology_response_surface(bundle)
    scenarios = surface.get("scenarios")
    if not isinstance(scenarios, list):
        raise FemicHydrologyScreenError("Response surface scenarios must be a list.")
    result: list[tuple[str, dict[str, float]]] = []
    for item in scenarios:
        if not isinstance(item, Mapping):
            continue
        name = item.get("name")
        covariates = item.get("covariates")
        if not isinstance(name, str) or not isinstance(covariates, Mapping):
            continue
        result.append(
            (
                name,
                {
                    str(key): _float(value, f"scenario {name} {key}")
                    for key, value in covariates.items()
                },
            )
        )
    if not result:
        raise FemicHydrologyScreenError("Response surface has no scenarios.")
    return tuple(result)


def _surface_rows(
    bundle: FemicHydrologyBundle,
) -> dict[tuple[str, float], dict[str, object]]:
    surface = read_femic_hydrology_response_surface(bundle)
    rows = surface.get("rows")
    if not isinstance(rows, list):
        raise FemicHydrologyScreenError("Response surface rows must be a list.")
    result: dict[tuple[str, float], dict[str, object]] = {}
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        name = item.get("scenario_name")
        period = item.get("return_period")
        if isinstance(name, str) and isinstance(period, (int, float)):
            result[(name, float(period))] = {str(key): value for key, value in item.items()}
    return result


def _risk_rows(bundle: FemicHydrologyBundle) -> list[dict[str, object]]:
    flood = read_femic_hydrology_flood_risk(bundle)
    rows = flood.get("rows")
    if not isinstance(rows, list):
        raise FemicHydrologyScreenError("Flood-risk rows must be a list.")
    return [
        {str(key): value for key, value in item.items()}
        for item in rows
        if isinstance(item, Mapping)
    ]


def _select_scenario(
    scenarios: tuple[tuple[str, dict[str, float]], ...],
    features: Mapping[str, float],
    tolerance: float,
) -> tuple[str, dict[str, float]] | None:
    best: tuple[float, str, dict[str, float]] | None = None
    for name, covariates in scenarios:
        if "harvest_fraction" not in covariates:
            continue
        if any(key not in features for key in covariates):
            continue
        distance = max(abs(features[key] - value) for key, value in covariates.items())
        if distance <= tolerance and (best is None or distance < best[0]):
            best = (distance, name, covariates)
    return None if best is None else (best[1], best[2])


def _refusal(
    period: int,
    day: int,
    watershed_id: str | None,
    receptor_id: str | None,
    return_period: float | None,
    reason: str,
    *,
    block_id: str | None = None,
) -> dict[str, object]:
    return {
        "period": period,
        "day": day,
        "watershed_id": watershed_id,
        "receptor_id": receptor_id,
        "return_period": return_period,
        "block_id": block_id,
        "reason": reason,
    }


def _float(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FemicHydrologyScreenError(f"{field} must be numeric.")
    number = float(value)
    if not math.isfinite(number):
        raise FemicHydrologyScreenError(f"{field} must be finite.")
    return number


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None
