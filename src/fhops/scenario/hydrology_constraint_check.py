"""Check one FHOPS schedule for flood-aware operational exposure.

The check uses fixed hazard windows and explicit assets. It does not run a
hydrology model or change the scheduler.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fhops.scenario.hydrology_assets import (
    FemicHydrologyAssetError,
    map_hydrology_assets,
)
from fhops.scenario.hydrology_hazard import (
    FemicHydrologyHazardError,
    load_hydrology_hazard,
)
from fhops.scenario.hydrology_mapping import (
    FemicHydrologyMappingError,
    load_hydrology_mapping,
)

HYDROLOGY_CONSTRAINT_SCHEMA = "fhops.hydrology.constraint_check.v1"

__all__ = [
    "FemicHydrologyConstraintError",
    "HydrologyConstraintCheck",
    "HydrologyConstraintEvent",
    "check_fhops_hydrology_constraints",
    "write_hydrology_constraint_check",
]


class FemicHydrologyConstraintError(RuntimeError):
    """A schedule cannot be checked against hazard evidence."""


@dataclass(frozen=True)
class _Assignment:
    block_id: str
    day: int
    machine_id: str | None
    shift_id: str | None


@dataclass(frozen=True)
class HydrologyConstraintEvent:
    """One operational activity inside a hazard window.

    Attributes
    ----------
    day : int
        One-indexed schedule day.
    shift_id : str | None
        Optional shift label.
    machine_id : str | None
        Optional machine identifier.
    block_id : str
        Scheduled block identifier.
    watershed_id : str
        FEMIC watershed identifier.
    severity : str
        ``watch``, ``warning``, or ``closure``.
    asset_ids : tuple[str, ...]
        Assets in the same watershed.
    reason : str
        Human-readable exposure reason.
    """

    day: int
    shift_id: str | None
    machine_id: str | None
    block_id: str
    watershed_id: str
    severity: str
    asset_ids: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, object]:
        """Return the event as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Event fields.
        """
        return {
            "day": self.day,
            "shift_id": self.shift_id,
            "machine_id": self.machine_id,
            "block_id": self.block_id,
            "watershed_id": self.watershed_id,
            "severity": self.severity,
            "asset_ids": list(self.asset_ids),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class HydrologyConstraintCheck:
    """Result of checking one schedule against hazard windows.

    Attributes
    ----------
    check_id : str
        Deterministic check identifier.
    generated_utc : str
        Check timestamp.
    scenario_path : Path
        Scenario YAML.
    hazard_id : str
        Hazard table identifier.
    mapping_id : str
        Hydrology mapping identifier.
    schedule_sha256 : str
        Assignments CSV digest.
    events : tuple[HydrologyConstraintEvent, ...]
        All watch/warning/closure events.
    failed : bool
        Whether the selected policy treats an event as a failure.
    failure_reasons : tuple[str, ...]
        Reasons the check failed.
    coverage : dict[str, object]
        Assignment, day, block, and event coverage.
    warnings : tuple[str, ...]
        Non-fatal observations.
    caveats : tuple[str, ...]
        Operational-only caveats.
    """

    check_id: str
    generated_utc: str
    scenario_path: Path
    hazard_id: str
    mapping_id: str
    schedule_sha256: str
    events: tuple[HydrologyConstraintEvent, ...]
    failed: bool
    failure_reasons: tuple[str, ...]
    coverage: dict[str, object]
    warnings: tuple[str, ...]
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the check result as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Identity, events, failure state, coverage, and caveats.
        """
        return {
            "schema_version": HYDROLOGY_CONSTRAINT_SCHEMA,
            "check_id": self.check_id,
            "generated_utc": self.generated_utc,
            "scenario_path": str(self.scenario_path),
            "hazard_id": self.hazard_id,
            "mapping_id": self.mapping_id,
            "schedule_sha256": self.schedule_sha256,
            "event_count": len(self.events),
            "events": [event.to_dict() for event in self.events],
            "failed": self.failed,
            "failure_reasons": list(self.failure_reasons),
            "coverage": self.coverage,
            "warnings": list(self.warnings),
            "caveats": list(self.caveats),
        }


def check_fhops_hydrology_constraints(
    scenario_path: str | Path,
    mapping_path: str | Path,
    schedule_path: str | Path,
    hazard_path: str | Path,
    *,
    assets_path: str | Path | None = None,
    fail_on_closure: bool = True,
    fail_on_warning: bool = False,
    generated_utc: str | None = None,
) -> HydrologyConstraintCheck:
    """Check one schedule for operational hazard-window exposure.

    Parameters
    ----------
    scenario_path : str | Path
        FHOPS scenario YAML.
    mapping_path : str | Path
        Hydrology mapping directory or manifest.
    schedule_path : str | Path
        FHOPS assignments CSV.
    hazard_path : str | Path
        Operational hazard JSON.
    assets_path : str | Path | None, optional
        Explicit road/culvert asset JSON.
    fail_on_closure : bool, optional
        Treat closure events as failures. Defaults to True.
    fail_on_warning : bool, optional
        Treat warning events as failures. Defaults to False.
    generated_utc : str | None, optional
        Check timestamp.

    Returns
    -------
    HydrologyConstraintCheck
        Events, failure state, coverage, warnings, and caveats.

    Raises
    ------
    FemicHydrologyConstraintError
        If evidence is missing or a scheduled block has no mapping.
    """
    scenario = Path(scenario_path).expanduser().resolve()
    schedule_file = Path(schedule_path).expanduser().resolve()
    try:
        mapping = load_hydrology_mapping(Path(mapping_path))
        hazard = load_hydrology_hazard(Path(hazard_path))
    except (FemicHydrologyMappingError, FemicHydrologyHazardError, ValueError) as exc:
        raise FemicHydrologyConstraintError(str(exc)) from exc
    asset_ids_by_watershed: dict[str, tuple[str, ...]] = {}
    warnings: list[str] = []
    if assets_path is not None:
        try:
            assets = map_hydrology_assets(scenario, Path(mapping_path), Path(assets_path))
        except (FemicHydrologyAssetError, ValueError) as exc:
            raise FemicHydrologyConstraintError(str(exc)) from exc
        for asset in assets.assets:
            asset_ids_by_watershed.setdefault(asset.watershed_id, ())
            asset_ids_by_watershed[asset.watershed_id] = (
                *asset_ids_by_watershed[asset.watershed_id],
                asset.asset_id,
            )
        warnings.extend(assets.warnings)
    if hazard.review_status != "reviewed":
        warnings.append("Hazard table is not reviewed; check is provisional.")
    if mapping.review_status != "reviewed":
        warnings.append("Hydrology mapping is not reviewed; check is provisional.")
    assignments = _read_assignments(schedule_file)
    block_watershed = {
        row.support_id: row.watershed_id for row in mapping.rows if row.support_unit == "block"
    }
    events: list[HydrologyConstraintEvent] = []
    missing_blocks: set[str] = set()
    for assignment in assignments:
        watershed_id = block_watershed.get(assignment.block_id)
        if watershed_id is None:
            missing_blocks.add(assignment.block_id)
            continue
        severity = hazard.severity_for(watershed_id, assignment.day)
        if severity is None:
            continue
        events.append(
            HydrologyConstraintEvent(
                day=assignment.day,
                shift_id=assignment.shift_id,
                machine_id=assignment.machine_id,
                block_id=assignment.block_id,
                watershed_id=watershed_id,
                severity=severity,
                asset_ids=asset_ids_by_watershed.get(watershed_id, ()),
                reason=(
                    f"{severity.capitalize()} window for watershed {watershed_id!r} "
                    f"on day {assignment.day}."
                ),
            )
        )
    if missing_blocks:
        raise FemicHydrologyConstraintError(
            "Scheduled blocks have no hydrology mapping: " + ", ".join(sorted(missing_blocks))
        )
    failure_reasons: list[str] = []
    if fail_on_closure and any(event.severity == "closure" for event in events):
        failure_reasons.append("Closure-window activity is prohibited.")
    if fail_on_warning and any(event.severity == "warning" for event in events):
        failure_reasons.append("Warning-window activity is prohibited by policy.")
    timestamp = generated_utc or datetime.now(UTC).isoformat()
    schedule_sha = hashlib.sha256(schedule_file.read_bytes()).hexdigest()
    material = {
        "scenario_path": str(scenario),
        "hazard_id": hazard.hazard_id,
        "mapping_id": mapping.mapping_id,
        "schedule_sha256": schedule_sha,
        "events": [event.to_dict() for event in events],
        "fail_on_closure": fail_on_closure,
        "fail_on_warning": fail_on_warning,
    }
    check_id = (
        "fhops-hydro-constraint-"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
    )
    coverage = {
        "assignments": len(assignments),
        "days": sorted({assignment.day for assignment in assignments}),
        "blocks": sorted({assignment.block_id for assignment in assignments}),
        "watersheds": sorted({event.watershed_id for event in events}),
        "watch_events": sum(event.severity == "watch" for event in events),
        "warning_events": sum(event.severity == "warning" for event in events),
        "closure_events": sum(event.severity == "closure" for event in events),
    }
    return HydrologyConstraintCheck(
        check_id=check_id,
        generated_utc=timestamp,
        scenario_path=scenario,
        hazard_id=hazard.hazard_id,
        mapping_id=mapping.mapping_id,
        schedule_sha256=schedule_sha,
        events=tuple(events),
        failed=bool(failure_reasons),
        failure_reasons=tuple(failure_reasons),
        coverage=coverage,
        warnings=tuple(warnings),
        caveats=(
            "Operational exposure check only; not a watershed flood model.",
            "Hazard windows are fixed external evidence, not recomputed per schedule.",
            "No flood map, design flood, or regulatory determination is produced.",
        ),
    )


def write_hydrology_constraint_check(
    result: HydrologyConstraintCheck, out_dir: Path
) -> dict[str, Path]:
    """Write constraint-check events and manifest.

    Parameters
    ----------
    result : HydrologyConstraintCheck
        Check result.
    out_dir : Path
        Output directory.

    Returns
    -------
    dict[str, Path]
        Paths keyed by ``events`` and ``manifest``.
    """
    output = out_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    events_path = output / "hydrology_constraint_events.csv"
    columns = (
        "day",
        "shift_id",
        "machine_id",
        "block_id",
        "watershed_id",
        "severity",
        "asset_ids",
        "reason",
    )
    with events_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for event in result.events:
            writer.writerow(
                {
                    "day": event.day,
                    "shift_id": event.shift_id or "",
                    "machine_id": event.machine_id or "",
                    "block_id": event.block_id,
                    "watershed_id": event.watershed_id,
                    "severity": event.severity,
                    "asset_ids": "|".join(event.asset_ids),
                    "reason": event.reason,
                }
            )
    manifest_path = output / "hydrology_constraint_check.json"
    manifest_path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"events": events_path, "manifest": manifest_path}


def _read_assignments(path: Path) -> list[_Assignment]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not {"block_id", "day"} <= set(reader.fieldnames):
                raise FemicHydrologyConstraintError(
                    "Assignments CSV requires block_id and day columns."
                )
            assignments: list[_Assignment] = []
            seen: set[tuple[str, int, str | None, str | None]] = set()
            for index, row in enumerate(reader, start=2):
                block_id = (row.get("block_id") or "").strip()
                day_text = (row.get("day") or "").strip()
                if not block_id:
                    raise FemicHydrologyConstraintError(f"Assignments row {index} has no block_id.")
                try:
                    day = int(day_text)
                except ValueError as exc:
                    raise FemicHydrologyConstraintError(
                        f"Assignments row {index} has an invalid day."
                    ) from exc
                if day < 1:
                    raise FemicHydrologyConstraintError(
                        f"Assignments row {index} day must be >= 1."
                    )
                machine_id = (row.get("machine_id") or "").strip() or None
                shift_id = (row.get("shift_id") or "").strip() or None
                key = (block_id, day, machine_id, shift_id)
                if key in seen:
                    continue
                seen.add(key)
                assignments.append(
                    _Assignment(
                        block_id=block_id,
                        day=day,
                        machine_id=machine_id,
                        shift_id=shift_id,
                    )
                )
    except OSError as exc:
        raise FemicHydrologyConstraintError(f"Unable to read assignments: {exc}") from exc
    if not assignments:
        raise FemicHydrologyConstraintError("Assignments CSV contains no rows.")
    return assignments
