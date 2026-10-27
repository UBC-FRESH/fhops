"""Map FHOPS blocks, landings, and roads to FEMIC hydrology support.

The mapping is an explicit, reviewed crosswalk. FHOPS never infers a watershed
or receptor from geometry.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fhops.scenario.hydrology import (
    FemicHydrologyBundle,
    FemicHydrologyError,
    load_femic_hydrology_bundle,
    read_femic_hydrology_domain,
    read_femic_hydrology_ledger,
)
from fhops.scenario.io import load_scenario

HYDROLOGY_CROSSWALK_SCHEMA = "fhops.hydrology.crosswalk.v1"
HYDROLOGY_MAPPING_SCHEMA = "fhops.hydrology.mapping.v1"
HYDROLOGY_CROSSWALK_REVIEW_STATUSES: tuple[str, ...] = (
    "not_reviewed",
    "review_pending",
    "reviewed",
)
SUPPORT_UNITS: tuple[str, ...] = ("block", "landing", "road")

__all__ = [
    "FemicHydrologyMappingError",
    "HydrologyCrosswalk",
    "HydrologyCrosswalkMetadata",
    "HydrologyCrosswalkRow",
    "HydrologyMapping",
    "HydrologyMappingRow",
    "load_hydrology_crosswalk",
    "load_hydrology_mapping",
    "map_femic_hydrology_to_scenario",
    "write_hydrology_mapping",
]


class FemicHydrologyMappingError(RuntimeError):
    """A hydrology crosswalk cannot be loaded or applied to a scenario."""


@dataclass(frozen=True)
class HydrologyCrosswalkMetadata:
    """Review metadata for an explicit hydrology crosswalk.

    Attributes
    ----------
    crosswalk_id : str
        Stable crosswalk identifier.
    created_utc : str
        Creation timestamp.
    review_status : str
        ``not_reviewed``, ``review_pending``, or ``reviewed``.
    reviewed_by : str | None
        Reviewer identifier when reviewed.
    method : str
        Mapping method or process.
    source : str
        Source document or process.
    caveats : tuple[str, ...]
        Review caveats.
    """

    crosswalk_id: str
    created_utc: str
    review_status: str
    reviewed_by: str | None
    method: str
    source: str
    caveats: tuple[str, ...]


@dataclass(frozen=True)
class HydrologyCrosswalkRow:
    """One explicit FHOPS support to FEMIC unit/watershed mapping.

    Attributes
    ----------
    block_id : str | None
        FHOPS block identifier, when the row is block-level.
    landing_id : str | None
        FHOPS landing identifier, when the row is landing-level.
    road_id : str | None
        FHOPS road-construction identifier, when the row is road-level.
    unit_id : str
        FEMIC disturbance-ledger unit identifier.
    watershed_id : str
        FEMIC watershed identifier.
    receptor_id : str | None
        Optional FEMIC flood-risk receptor identifier.
    notes : str
        Human review notes.
    """

    block_id: str | None
    landing_id: str | None
    road_id: str | None
    unit_id: str
    watershed_id: str
    receptor_id: str | None
    notes: str

    def support_key(self) -> tuple[str, str]:
        """Return the support unit and identifier.

        Returns
        -------
        tuple[str, str]
            ``("block"|"landing"|"road", id)``.
        """
        for unit, value in (
            ("block", self.block_id),
            ("landing", self.landing_id),
            ("road", self.road_id),
        ):
            if value is not None:
                return unit, value
        raise FemicHydrologyMappingError("Crosswalk row has no support key.")


@dataclass(frozen=True)
class HydrologyCrosswalk:
    """Loaded and checksummed explicit crosswalk.

    Attributes
    ----------
    path : Path
        Crosswalk CSV path.
    sha256 : str
        SHA-256 of the CSV bytes.
    rows : tuple[HydrologyCrosswalkRow, ...]
        Mapping rows.
    metadata : HydrologyCrosswalkMetadata
        Review metadata.
    """

    path: Path
    sha256: str
    rows: tuple[HydrologyCrosswalkRow, ...]
    metadata: HydrologyCrosswalkMetadata


@dataclass(frozen=True)
class HydrologyMappingRow:
    """One resolved support mapping.

    Attributes
    ----------
    support_unit : str
        ``block``, ``landing``, or ``road``.
    support_id : str
        FHOPS support identifier.
    unit_id : str
        FEMIC unit identifier.
    watershed_id : str
        FEMIC watershed identifier.
    receptor_id : str | None
        Optional FEMIC receptor identifier.
    notes : str
        Human review notes.
    """

    support_unit: str
    support_id: str
    unit_id: str
    watershed_id: str
    receptor_id: str | None
    notes: str

    def to_dict(self) -> dict[str, object]:
        """Return the mapping row as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Support unit/id, FEMIC IDs, receptor, and notes.
        """
        return {
            "support_unit": self.support_unit,
            "support_id": self.support_id,
            "unit_id": self.unit_id,
            "watershed_id": self.watershed_id,
            "receptor_id": self.receptor_id,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class HydrologyMapping:
    """Resolved scenario-to-FEMIC mapping and coverage.

    Attributes
    ----------
    mapping_id : str
        Deterministic mapping identifier.
    generated_utc : str
        Mapping timestamp.
    scenario_path : Path
        Scenario YAML.
    bundle_id : str
        FEMIC bundle identifier.
    bundle_version : str
        FEMIC bundle version.
    manifest_sha256 : str
        FEMIC manifest digest.
    crosswalk_id : str
        Crosswalk identifier.
    crosswalk_sha256 : str
        Crosswalk CSV digest.
    review_status : str
        Crosswalk review state.
    rows : tuple[HydrologyMappingRow, ...]
        Resolved rows.
    coverage : dict[str, object]
        Counts and unmapped support ids.
    warnings : tuple[str, ...]
        Non-fatal observations.
    caveats : tuple[str, ...]
        Mapping and screening caveats.
    """

    mapping_id: str
    generated_utc: str
    scenario_path: Path
    bundle_id: str
    bundle_version: str
    manifest_sha256: str
    crosswalk_id: str
    crosswalk_sha256: str
    review_status: str
    rows: tuple[HydrologyMappingRow, ...]
    coverage: dict[str, object]
    warnings: tuple[str, ...]
    caveats: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the mapping manifest as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Identity, row count, rows, coverage, warnings, and caveats.
        """
        return {
            "schema_version": HYDROLOGY_MAPPING_SCHEMA,
            "mapping_id": self.mapping_id,
            "generated_utc": self.generated_utc,
            "scenario_path": str(self.scenario_path),
            "bundle_id": self.bundle_id,
            "bundle_version": self.bundle_version,
            "manifest_sha256": self.manifest_sha256,
            "crosswalk_id": self.crosswalk_id,
            "crosswalk_sha256": self.crosswalk_sha256,
            "review_status": self.review_status,
            "row_count": len(self.rows),
            "rows": [row.to_dict() for row in self.rows],
            "coverage": self.coverage,
            "warnings": list(self.warnings),
            "caveats": list(self.caveats),
        }


def load_hydrology_crosswalk(
    path: Path,
    *,
    metadata_path: Path | None = None,
) -> HydrologyCrosswalk:
    """Load and validate an explicit hydrology crosswalk.

    Parameters
    ----------
    path : Path
        Crosswalk CSV with one support key per row.
    metadata_path : Path | None, optional
        Crosswalk review metadata JSON.

    Returns
    -------
    HydrologyCrosswalk
        Checksummed rows and review metadata.

    Raises
    ------
    FemicHydrologyMappingError
        If the CSV or metadata is malformed.
    """
    resolved = path.expanduser().resolve()
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        raise FemicHydrologyMappingError(f"Unable to read crosswalk: {resolved}: {exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FemicHydrologyMappingError(f"Crosswalk is not UTF-8: {resolved}") from exc
    try:
        rows = _crosswalk_rows(text.splitlines())
    except csv.Error as exc:
        raise FemicHydrologyMappingError(f"Unable to parse crosswalk CSV: {exc}") from exc
    metadata = _crosswalk_metadata(metadata_path, digest=digest)
    return HydrologyCrosswalk(
        path=resolved,
        sha256=digest,
        rows=rows,
        metadata=metadata,
    )


def load_hydrology_mapping(path: Path) -> HydrologyMapping:
    """Load a mapping manifest written by :func:`write_hydrology_mapping`.

    Parameters
    ----------
    path : Path
        Mapping directory or ``hydrology_mapping.json``.

    Returns
    -------
    HydrologyMapping
        Loaded mapping with rows, coverage, and review state.

    Raises
    ------
    FemicHydrologyMappingError
        If the manifest is missing, malformed, or inconsistent.
    """
    resolved = path.expanduser().resolve()
    manifest_path = resolved / "hydrology_mapping.json" if resolved.is_dir() else resolved
    payload = _read_json_object(manifest_path, "hydrology mapping manifest")
    if payload.get("schema_version") != HYDROLOGY_MAPPING_SCHEMA:
        raise FemicHydrologyMappingError(
            f"Unsupported hydrology mapping schema {payload.get('schema_version')!r}."
        )
    rows_payload = payload.get("rows")
    if not isinstance(rows_payload, list):
        raise FemicHydrologyMappingError("Hydrology mapping rows must be a list.")
    rows: list[HydrologyMappingRow] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(rows_payload, start=1):
        if not isinstance(item, Mapping):
            raise FemicHydrologyMappingError(f"Mapping row {index} must be an object.")
        unit = _required_text(item.get("support_unit"), f"mapping row {index} support_unit")
        if unit not in SUPPORT_UNITS:
            raise FemicHydrologyMappingError(
                f"Mapping row {index} has unsupported support_unit {unit!r}."
            )
        support_id = _required_text(item.get("support_id"), f"mapping row {index} support_id")
        key = (unit, support_id)
        if key in seen:
            raise FemicHydrologyMappingError(f"Duplicate mapping row for {unit} {support_id!r}.")
        seen.add(key)
        rows.append(
            HydrologyMappingRow(
                support_unit=unit,
                support_id=support_id,
                unit_id=_required_text(item.get("unit_id"), f"mapping row {index} unit_id"),
                watershed_id=_required_text(
                    item.get("watershed_id"), f"mapping row {index} watershed_id"
                ),
                receptor_id=_optional_text(item.get("receptor_id")),
                notes=_optional_text(item.get("notes")) or "",
            )
        )
    row_count = payload.get("row_count")
    if isinstance(row_count, int) and row_count != len(rows):
        raise FemicHydrologyMappingError("Hydrology mapping row_count does not match rows.")
    coverage = payload.get("coverage")
    if not isinstance(coverage, Mapping):
        raise FemicHydrologyMappingError("Hydrology mapping coverage must be an object.")
    warnings = payload.get("warnings", [])
    caveats = payload.get("caveats", [])
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise FemicHydrologyMappingError("Hydrology mapping warnings must be strings.")
    if not isinstance(caveats, list) or not all(isinstance(item, str) for item in caveats):
        raise FemicHydrologyMappingError("Hydrology mapping caveats must be strings.")
    return HydrologyMapping(
        mapping_id=_required_text(payload.get("mapping_id"), "mapping_id"),
        generated_utc=_required_text(payload.get("generated_utc"), "generated_utc"),
        scenario_path=Path(
            _required_text(payload.get("scenario_path"), "scenario_path")
        ).expanduser(),
        bundle_id=_required_text(payload.get("bundle_id"), "bundle_id"),
        bundle_version=_required_text(payload.get("bundle_version"), "bundle_version"),
        manifest_sha256=_required_text(payload.get("manifest_sha256"), "manifest_sha256"),
        crosswalk_id=_required_text(payload.get("crosswalk_id"), "crosswalk_id"),
        crosswalk_sha256=_required_text(payload.get("crosswalk_sha256"), "crosswalk_sha256"),
        review_status=_required_text(payload.get("review_status"), "review_status"),
        rows=tuple(rows),
        coverage={str(key): value for key, value in coverage.items()},
        warnings=tuple(item for item in warnings if item),
        caveats=tuple(item for item in caveats if item),
    )


def map_femic_hydrology_to_scenario(
    scenario_path: str | Path,
    bundle_dir: str | Path,
    crosswalk_path: str | Path,
    *,
    metadata_path: str | Path | None = None,
    allow_partial: bool = False,
    generated_utc: str | None = None,
) -> HydrologyMapping:
    """Map explicit support rows to FEMIC watersheds and receptors.

    Parameters
    ----------
    scenario_path : str | Path
        FHOPS scenario YAML with a registered hydrology pin.
    bundle_dir : str | Path
        FEMIC hydrology bundle directory or manifest.
    crosswalk_path : str | Path
        Explicit crosswalk CSV.
    metadata_path : str | Path | None, optional
        Crosswalk review metadata JSON.
    allow_partial : bool, optional
        Record unmapped supports instead of failing. Defaults to False.
    generated_utc : str | None, optional
        Mapping timestamp.

    Returns
    -------
    HydrologyMapping
        Resolved rows, coverage, review state, warnings, and caveats.

    Raises
    ------
    FemicHydrologyMappingError
        If the bundle is not pinned, a support or FEMIC ID is unknown, a
        mapping conflicts, or coverage is incomplete without ``allow_partial``.
    """
    scenario = Path(scenario_path).expanduser().resolve()
    try:
        loaded = load_scenario(scenario)
        bundle = load_femic_hydrology_bundle(Path(bundle_dir))
    except (FemicHydrologyError, ValueError, FileNotFoundError) as exc:
        raise FemicHydrologyMappingError(str(exc)) from exc
    pin = _matching_pin(loaded, bundle)
    if pin is None:
        raise FemicHydrologyMappingError(
            f"Bundle {bundle.bundle_id}@{bundle.bundle_version} is not pinned in the scenario; "
            "run `fhops scenario hydrology register` first."
        )
    crosswalk = load_hydrology_crosswalk(
        Path(crosswalk_path),
        metadata_path=Path(metadata_path) if metadata_path is not None else None,
    )
    known = {
        "block": set(loaded.block_ids()),
        "landing": set(loaded.landing_ids()),
        "road": {road.id for road in loaded.road_construction or []},
    }
    try:
        domain = read_femic_hydrology_domain(bundle)
        ledger = read_femic_hydrology_ledger(bundle)
    except FemicHydrologyError as exc:
        raise FemicHydrologyMappingError(str(exc)) from exc
    watersheds = _ids(domain.get("watersheds"), "watersheds", "watershed_id")
    receptors = _ids(domain.get("receptors"), "receptors", "receptor_id")
    unit_to_watershed = _unit_watersheds(ledger)
    rows: list[HydrologyMappingRow] = []
    for row in crosswalk.rows:
        unit, support_id = row.support_key()
        if support_id not in known[unit]:
            raise FemicHydrologyMappingError(
                f"Crosswalk references unknown {unit} id {support_id!r}."
            )
        expected_watershed = unit_to_watershed.get(row.unit_id)
        if expected_watershed is None:
            raise FemicHydrologyMappingError(
                f"Crosswalk references unknown FEMIC unit {row.unit_id!r}."
            )
        if row.watershed_id not in watersheds:
            raise FemicHydrologyMappingError(
                f"Crosswalk references unknown FEMIC watershed {row.watershed_id!r}."
            )
        if expected_watershed and expected_watershed != row.watershed_id:
            raise FemicHydrologyMappingError(
                f"FEMIC unit {row.unit_id!r} belongs to watershed "
                f"{expected_watershed!r}, not {row.watershed_id!r}."
            )
        if row.receptor_id is not None and row.receptor_id not in receptors:
            raise FemicHydrologyMappingError(
                f"Crosswalk references unknown FEMIC receptor {row.receptor_id!r}."
            )
        rows.append(
            HydrologyMappingRow(
                support_unit=unit,
                support_id=support_id,
                unit_id=row.unit_id,
                watershed_id=row.watershed_id,
                receptor_id=row.receptor_id,
                notes=row.notes,
            )
        )
    coverage = _coverage(known, rows)
    warnings: list[str] = []
    if crosswalk.metadata.review_status != "reviewed":
        warnings.append(
            f"Crosswalk review status is {crosswalk.metadata.review_status!r}; "
            "mapping is provisional."
        )
    unmapped_total = sum(_unmapped_count(coverage, unit) for unit in SUPPORT_UNITS)
    if unmapped_total:
        if not allow_partial:
            raise FemicHydrologyMappingError(
                "Crosswalk does not cover the scenario: "
                + ", ".join(
                    f"{_unmapped_count(coverage, unit)} {unit}(s)"
                    for unit in SUPPORT_UNITS
                    if _unmapped_count(coverage, unit)
                )
            )
        warnings.append("Partial mapping: unmapped supports are recorded in coverage.")
    timestamp = generated_utc or datetime.now(UTC).isoformat()
    material = {
        "bundle_id": bundle.bundle_id,
        "bundle_version": bundle.bundle_version,
        "manifest_sha256": bundle.manifest_sha256,
        "crosswalk_sha256": crosswalk.sha256,
        "rows": [row.to_dict() for row in rows],
        "coverage": coverage,
    }
    mapping_id = (
        "fhops-hydro-mapping-"
        + hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
    )
    return HydrologyMapping(
        mapping_id=mapping_id,
        generated_utc=timestamp,
        scenario_path=scenario,
        bundle_id=bundle.bundle_id,
        bundle_version=bundle.bundle_version,
        manifest_sha256=bundle.manifest_sha256,
        crosswalk_id=crosswalk.metadata.crosswalk_id,
        crosswalk_sha256=crosswalk.sha256,
        review_status=crosswalk.metadata.review_status,
        rows=tuple(rows),
        coverage=coverage,
        warnings=tuple(warnings),
        caveats=(
            "Mapping is an explicit reviewed crosswalk, not a spatial join.",
            "A mapping is not a hydrologic validation.",
            *crosswalk.metadata.caveats,
        ),
    )


def write_hydrology_mapping(mapping: HydrologyMapping, out_dir: Path) -> dict[str, Path]:
    """Write the mapping CSV and manifest.

    Parameters
    ----------
    mapping : HydrologyMapping
        Resolved mapping.
    out_dir : Path
        Output directory.

    Returns
    -------
    dict[str, Path]
        Paths keyed by ``rows`` and ``manifest``.
    """
    output = out_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows_path = output / "hydrology_mapping.csv"
    columns = (
        "support_unit",
        "support_id",
        "unit_id",
        "watershed_id",
        "receptor_id",
        "notes",
    )
    with rows_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(row.to_dict() for row in mapping.rows)
    manifest_path = output / "hydrology_mapping.json"
    manifest_path.write_text(
        json.dumps(mapping.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"rows": rows_path, "manifest": manifest_path}


def _crosswalk_rows(lines: list[str]) -> tuple[HydrologyCrosswalkRow, ...]:
    reader = csv.DictReader(lines)
    if reader.fieldnames is None:
        raise FemicHydrologyMappingError("Crosswalk CSV has no header.")
    required = {"block_id", "landing_id", "road_id", "unit_id", "watershed_id"}
    if not required.issubset(reader.fieldnames):
        raise FemicHydrologyMappingError(
            "Crosswalk CSV is missing required columns: "
            + ", ".join(sorted(required - set(reader.fieldnames)))
            + "."
        )
    rows: list[HydrologyCrosswalkRow] = []
    seen: set[tuple[str, str]] = set()
    for index, payload in enumerate(reader, start=2):
        block_id = _optional_text(payload.get("block_id"))
        landing_id = _optional_text(payload.get("landing_id"))
        road_id = _optional_text(payload.get("road_id"))
        keys = [item for item in (block_id, landing_id, road_id) if item is not None]
        if len(keys) != 1:
            raise FemicHydrologyMappingError(
                f"Crosswalk row {index} must set exactly one support key."
            )
        key = (
            "block" if block_id is not None else "landing" if landing_id is not None else "road",
            keys[0],
        )
        if key in seen:
            raise FemicHydrologyMappingError(f"Duplicate crosswalk support {key[0]} {key[1]}.")
        seen.add(key)
        rows.append(
            HydrologyCrosswalkRow(
                block_id=block_id,
                landing_id=landing_id,
                road_id=road_id,
                unit_id=_required_text(payload.get("unit_id"), f"crosswalk row {index} unit_id"),
                watershed_id=_required_text(
                    payload.get("watershed_id"), f"crosswalk row {index} watershed_id"
                ),
                receptor_id=_optional_text(payload.get("receptor_id")),
                notes=_optional_text(payload.get("notes")) or "",
            )
        )
    if not rows:
        raise FemicHydrologyMappingError("Crosswalk CSV contains no mapping rows.")
    return tuple(rows)


def _crosswalk_metadata(path: Path | None, *, digest: str) -> HydrologyCrosswalkMetadata:
    if path is None:
        return HydrologyCrosswalkMetadata(
            crosswalk_id=f"crosswalk-{digest[:16]}",
            created_utc="",
            review_status="not_reviewed",
            reviewed_by=None,
            method="unspecified",
            source="",
            caveats=("No crosswalk review metadata was supplied.",),
        )
    payload = _read_json_object(path, "crosswalk metadata")
    if payload.get("schema_version") != HYDROLOGY_CROSSWALK_SCHEMA:
        raise FemicHydrologyMappingError(
            f"Unsupported crosswalk metadata schema {payload.get('schema_version')!r}."
        )
    recorded = _optional_text(payload.get("crosswalk_sha256"))
    if recorded is not None and recorded.lower() != digest.lower():
        raise FemicHydrologyMappingError("Crosswalk metadata checksum does not match the CSV.")
    review_status = _required_text(payload.get("review_status"), "crosswalk review_status")
    if review_status not in HYDROLOGY_CROSSWALK_REVIEW_STATUSES:
        raise FemicHydrologyMappingError(f"Unsupported crosswalk review status {review_status!r}.")
    reviewed_by = _optional_text(payload.get("reviewed_by"))
    if review_status == "reviewed" and reviewed_by is None:
        raise FemicHydrologyMappingError("Reviewed crosswalk metadata requires reviewed_by.")
    caveats = payload.get("caveats", [])
    if not isinstance(caveats, list) or not all(isinstance(item, str) for item in caveats):
        raise FemicHydrologyMappingError("Crosswalk caveats must be a list of strings.")
    return HydrologyCrosswalkMetadata(
        crosswalk_id=_required_text(payload.get("crosswalk_id"), "crosswalk_id"),
        created_utc=_optional_text(payload.get("created_utc")) or "",
        review_status=review_status,
        reviewed_by=reviewed_by,
        method=_optional_text(payload.get("method")) or "",
        source=_optional_text(payload.get("source")) or "",
        caveats=tuple(item.strip() for item in caveats if item.strip()),
    )


def _matching_pin(scenario: object, bundle: FemicHydrologyBundle) -> object | None:
    pins = getattr(scenario, "hydrology_products", None) or []
    for pin in pins:
        if (pin.bundle_id, pin.bundle_version) == (bundle.bundle_id, bundle.bundle_version):
            if pin.manifest_sha256 != bundle.manifest_sha256:
                raise FemicHydrologyMappingError(
                    "Scenario hydrology pin has a different manifest checksum from the bundle."
                )
            return pin
    return None


def _ids(value: object, field: str, key: str) -> set[str]:
    if not isinstance(value, list):
        raise FemicHydrologyMappingError(f"FEMIC {field} must be a list.")
    result: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise FemicHydrologyMappingError(f"FEMIC {field} entries must be objects.")
        identifier = _optional_text(item.get(key))
        if identifier is None:
            raise FemicHydrologyMappingError(f"FEMIC {field} entries require {key}.")
        result.add(identifier)
    return result


def _unit_watersheds(ledger: dict[str, object]) -> dict[str, str]:
    units = ledger.get("units")
    if not isinstance(units, list):
        raise FemicHydrologyMappingError("FEMIC ledger units must be a list.")
    result: dict[str, str] = {}
    for item in units:
        if not isinstance(item, Mapping):
            raise FemicHydrologyMappingError("FEMIC ledger units must be objects.")
        unit_id = _optional_text(item.get("unit_id"))
        watershed_id = _optional_text(item.get("watershed_id"))
        if unit_id is None or watershed_id is None:
            raise FemicHydrologyMappingError("FEMIC ledger units require unit_id and watershed_id.")
        result[unit_id] = watershed_id
    return result


def _coverage(known: dict[str, set[str]], rows: list[HydrologyMappingRow]) -> dict[str, object]:
    mapped: dict[str, set[str]] = {unit: set() for unit in SUPPORT_UNITS}
    for row in rows:
        mapped[row.support_unit].add(row.support_id)
    coverage: dict[str, object] = {}
    for unit in SUPPORT_UNITS:
        coverage[f"scenario_{unit}s"] = len(known[unit])
        coverage[f"mapped_{unit}s"] = len(mapped[unit])
        coverage[f"unmapped_{unit}s"] = sorted(known[unit] - mapped[unit])
    return coverage


def _unmapped_count(coverage: dict[str, object], unit: str) -> int:
    value = coverage.get(f"unmapped_{unit}s")
    return len(value) if isinstance(value, list) else 0


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FemicHydrologyMappingError(f"{field} must be a non-empty string.")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _read_json_object(path: Path, context: str) -> dict[str, object]:
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FemicHydrologyMappingError(f"Unable to read {context}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise FemicHydrologyMappingError(f"{context} must be a JSON object.")
    return {str(key): value for key, value in payload.items()}
