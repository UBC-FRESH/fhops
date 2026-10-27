"""Load explicit, schedule-bound road/culvert exposure for hydrology screening.

The table is a shared cross-repository input with schema
``ws4.hydrology.exposure.v1``. FHOPS validates it independently and binds it to
one assignments CSV. It never infers road state or culvert locations from
geometry.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

HYDROLOGY_EXPOSURE_SCHEMA = "ws4.hydrology.exposure.v1"
HYDROLOGY_EXPOSURE_REVIEW_STATUSES: tuple[str, ...] = (
    "not_reviewed",
    "review_pending",
    "reviewed",
)
HYDROLOGY_EXPOSURE_FEATURES: tuple[str, ...] = (
    "road_built_km",
    "road_used_km",
    "road_decommissioned_km",
    "culvert_count",
    "culvert_exposed_count",
)
HYDROLOGY_EXPOSURE_DERIVED_FEATURES: tuple[str, ...] = (
    "road_built_density_km_per_km2",
    "road_used_density_km_per_km2",
    "road_decommissioned_density_km_per_km2",
    "culvert_exposure_per_km2",
)
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

__all__ = [
    "FemicHydrologyExposureError",
    "HYDROLOGY_EXPOSURE_DERIVED_FEATURES",
    "HYDROLOGY_EXPOSURE_FEATURES",
    "HYDROLOGY_EXPOSURE_SCHEMA",
    "HydrologyExposure",
    "HydrologyExposureRow",
    "HydrologyExposureValidation",
    "load_hydrology_exposure",
    "schedule_sha256",
    "validate_hydrology_exposure",
]


class FemicHydrologyExposureError(RuntimeError):
    """Raised when a road/culvert exposure table cannot be consumed."""


@dataclass(frozen=True)
class HydrologyExposureRow:
    """One watershed/period exposure record.

    Attributes
    ----------
    watershed_id : str
        FEMIC watershed identifier.
    period : int
        Non-negative screening period.
    road_built_km : float
        Road length built in the period.
    road_used_km : float
        Road length used in the period.
    road_decommissioned_km : float
        Road length decommissioned in the period.
    culvert_count : int
        Culvert count in the watershed.
    culvert_exposed_count : int
        Culverts exposed to the flood path.
    """

    watershed_id: str
    period: int
    road_built_km: float
    road_used_km: float
    road_decommissioned_km: float
    culvert_count: int
    culvert_exposed_count: int

    def to_dict(self) -> dict[str, object]:
        """Return the row in the shared exposure-table shape.

        Returns
        -------
        dict[str, object]
            Watershed, period, road lengths, and culvert counts.
        """
        return {
            "watershed_id": self.watershed_id,
            "period": self.period,
            "road_built_km": self.road_built_km,
            "road_used_km": self.road_used_km,
            "road_decommissioned_km": self.road_decommissioned_km,
            "culvert_count": self.culvert_count,
            "culvert_exposed_count": self.culvert_exposed_count,
        }


@dataclass(frozen=True)
class HydrologyExposure:
    """Loaded and checksummed schedule-bound exposure table.

    Attributes
    ----------
    path : Path
        Exposure JSON path.
    sha256 : str
        SHA-256 digest of the file bytes.
    exposure_id : str
        Stable exposure identifier.
    generated_utc : str
        Producer generation timestamp.
    source_id : str
        Source or process that produced the table.
    review_status : str
        ``not_reviewed``, ``review_pending``, or ``reviewed``.
    reviewer_id : str | None
        Reviewer identifier when reviewed.
    schedule_sha256 : str
        SHA-256 of the bound FHOPS schedule file.
    watershed_ids : tuple[str, ...]
        Declared watersheds.
    periods : tuple[int, ...]
        Declared periods, sorted ascending.
    rows : tuple[HydrologyExposureRow, ...]
        Complete watershed/period grid.
    caveats : tuple[str, ...]
        Interpretation caveats.
    """

    path: Path
    sha256: str
    exposure_id: str
    generated_utc: str
    source_id: str
    review_status: str
    reviewer_id: str | None
    schedule_sha256: str
    watershed_ids: tuple[str, ...]
    periods: tuple[int, ...]
    rows: tuple[HydrologyExposureRow, ...]
    caveats: tuple[str, ...]

    def row(self, watershed_id: str, period: int) -> HydrologyExposureRow:
        """Return one watershed/period row.

        Parameters
        ----------
        watershed_id : str
            Declared watershed identifier.
        period : int
            Declared period.

        Returns
        -------
        HydrologyExposureRow
            Matching row.

        Raises
        ------
        FemicHydrologyExposureError
            If the watershed/period pair is not declared.
        """
        for row in self.rows:
            if row.watershed_id == watershed_id and row.period == period:
                return row
        raise FemicHydrologyExposureError(
            f"Exposure has no row for watershed {watershed_id!r} period {period}."
        )

    def features_for(
        self, watershed_id: str, period: int, *, watershed_area_ha: float | None = None
    ) -> dict[str, float]:
        """Return raw and optional density features for one watershed/period.

        Parameters
        ----------
        watershed_id : str
            Declared watershed identifier.
        period : int
            Declared period.
        watershed_area_ha : float | None, optional
            FEMIC watershed area. When positive, calculated densities are added.

        Returns
        -------
        dict[str, float]
            Raw exposure features and, when an area is supplied, density features.

        Raises
        ------
        FemicHydrologyExposureError
            If the row is missing or the area is not positive when supplied.
        """
        row = self.row(watershed_id, period)
        features = {
            "road_built_km": row.road_built_km,
            "road_used_km": row.road_used_km,
            "road_decommissioned_km": row.road_decommissioned_km,
            "culvert_count": float(row.culvert_count),
            "culvert_exposed_count": float(row.culvert_exposed_count),
        }
        if watershed_area_ha is not None:
            if not math.isfinite(watershed_area_ha) or watershed_area_ha <= 0:
                raise FemicHydrologyExposureError(
                    "watershed_area_ha must be positive and finite for density features."
                )
            area_km2 = watershed_area_ha / 100.0
            features["road_built_density_km_per_km2"] = row.road_built_km / area_km2
            features["road_used_density_km_per_km2"] = row.road_used_km / area_km2
            features["road_decommissioned_density_km_per_km2"] = (
                row.road_decommissioned_km / area_km2
            )
            features["culvert_exposure_per_km2"] = row.culvert_exposed_count / area_km2
        return features

    def to_dict(self) -> dict[str, object]:
        """Return the exposure table as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Schema, identity, review, schedule binding, rows, and caveats.
        """
        return {
            "schema_version": HYDROLOGY_EXPOSURE_SCHEMA,
            "exposure_id": self.exposure_id,
            "generated_utc": self.generated_utc,
            "source_id": self.source_id,
            "review_status": self.review_status,
            "reviewer_id": self.reviewer_id,
            "schedule_sha256": self.schedule_sha256,
            "watershed_ids": list(self.watershed_ids),
            "periods": list(self.periods),
            "rows": [row.to_dict() for row in self.rows],
            "caveats": list(self.caveats),
        }


@dataclass(frozen=True)
class HydrologyExposureValidation:
    """Validation report for a road/culvert exposure table.

    Attributes
    ----------
    path : Path
        Exposure path.
    is_valid : bool
        Whether every required check passed.
    checked_utc : str
        Report timestamp.
    errors : tuple[str, ...]
        Blocking findings.
    warnings : tuple[str, ...]
        Non-blocking findings.
    row_count : int
        Number of parsed rows.
    watershed_count : int
        Number of declared watersheds.
    period_count : int
        Number of declared periods.
    exposure_sha256 : str
        File digest.
    schedule_sha256 : str | None
        Declared schedule digest.
    """

    path: Path
    is_valid: bool
    checked_utc: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    row_count: int
    watershed_count: int
    period_count: int
    exposure_sha256: str
    schedule_sha256: str | None

    def to_dict(self) -> dict[str, object]:
        """Return the validation report as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Path, validity, findings, counts, and digests.
        """
        return {
            "path": str(self.path),
            "is_valid": self.is_valid,
            "checked_utc": self.checked_utc,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "row_count": self.row_count,
            "watershed_count": self.watershed_count,
            "period_count": self.period_count,
            "exposure_sha256": self.exposure_sha256,
            "schedule_sha256": self.schedule_sha256,
        }


def schedule_sha256(path: Path) -> str:
    """Return the SHA-256 digest of an assignments CSV.

    Parameters
    ----------
    path : Path
        FHOPS assignments CSV.

    Returns
    -------
    str
        Lowercase SHA-256 hex digest.

    Raises
    ------
    FemicHydrologyExposureError
        If the file cannot be read.
    """
    try:
        return hashlib.sha256(path.expanduser().read_bytes()).hexdigest()
    except OSError as exc:
        raise FemicHydrologyExposureError(f"Unable to read schedule: {path}: {exc}") from exc


def validate_hydrology_exposure(
    path: Path,
    *,
    schedule_path: Path | None = None,
) -> HydrologyExposureValidation:
    """Validate a shared exposure table without raising.

    Parameters
    ----------
    path : Path
        Exposure JSON path.
    schedule_path : Path | None, optional
        FHOPS assignments CSV to compare with the declared schedule digest.

    Returns
    -------
    HydrologyExposureValidation
        Validation report with specific errors and warnings.
    """
    report, _exposure = _load(path, schedule_path=schedule_path)
    return report


def load_hydrology_exposure(
    path: Path,
    *,
    schedule_path: Path | None = None,
) -> HydrologyExposure:
    """Load and validate a shared exposure table.

    Parameters
    ----------
    path : Path
        Exposure JSON path.
    schedule_path : Path | None, optional
        FHOPS assignments CSV to compare with ``schedule_sha256``.

    Returns
    -------
    HydrologyExposure
        Validated exposure table.

    Raises
    ------
    FemicHydrologyExposureError
        If the table is invalid or bound to a different schedule.
    """
    report, exposure = _load(path, schedule_path=schedule_path)
    if not report.is_valid or exposure is None:
        raise FemicHydrologyExposureError(
            "; ".join(report.errors) or "Invalid hydrology exposure table."
        )
    return exposure


def _load(
    path: Path,
    *,
    schedule_path: Path | None,
) -> tuple[HydrologyExposureValidation, HydrologyExposure | None]:
    resolved = path.expanduser().resolve()
    checked = datetime.now(UTC).isoformat()
    errors: list[str] = []
    warnings: list[str] = []
    exposure_sha = ""
    declared_schedule: str | None = None
    row_count = 0
    watershed_count = 0
    period_count = 0
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        return (
            HydrologyExposureValidation(
                path=resolved,
                is_valid=False,
                checked_utc=checked,
                errors=(f"Unable to read exposure: {exc}",),
                warnings=(),
                row_count=0,
                watershed_count=0,
                period_count=0,
                exposure_sha256="",
                schedule_sha256=None,
            ),
            None,
        )
    exposure_sha = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        errors.append(f"Exposure is not UTF-8: {exc}")
        payload = None
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid exposure JSON: {exc}")
        payload = None
    if not isinstance(payload, Mapping):
        if not errors:
            errors.append("Exposure table must be a JSON object.")
        return _report(
            resolved,
            checked,
            errors,
            warnings,
            row_count,
            watershed_count,
            period_count,
            exposure_sha,
            declared_schedule,
        ), None
    if payload.get("schema_version") != HYDROLOGY_EXPOSURE_SCHEMA:
        errors.append(f"Unsupported exposure schema {payload.get('schema_version')!r}.")
    exposure_id = _required_text(payload.get("exposure_id"), "exposure_id", errors)
    generated_utc = _required_text(payload.get("generated_utc"), "generated_utc", errors)
    source_id = _required_text(payload.get("source_id"), "source_id", errors)
    review_status = _required_text(payload.get("review_status"), "review_status", errors)
    if review_status and review_status not in HYDROLOGY_EXPOSURE_REVIEW_STATUSES:
        errors.append(f"Unsupported review_status {review_status!r}.")
    reviewer_id = _optional_text(payload.get("reviewer_id"))
    if review_status == "reviewed" and reviewer_id is None:
        errors.append("Reviewed exposure requires reviewer_id.")
    declared_schedule = _required_text(
        payload.get("schedule_sha256"), "schedule_sha256", errors
    ).lower()
    if declared_schedule and SHA256_PATTERN.fullmatch(declared_schedule) is None:
        errors.append("schedule_sha256 must be a 64-character hex digest.")
    watershed_ids = _text_list(
        payload.get("watershed_ids"), "watershed_ids", errors, allow_empty=False
    )
    if len(set(watershed_ids)) != len(watershed_ids):
        errors.append("watershed_ids must be unique.")
    periods = _int_list(payload.get("periods"), "periods", errors, allow_empty=False)
    if len(set(periods)) != len(periods):
        errors.append("periods must be unique.")
    periods = tuple(sorted(periods))
    watershed_count = len(watershed_ids)
    period_count = len(periods)
    rows_payload = payload.get("rows")
    if not isinstance(rows_payload, list) or not rows_payload:
        errors.append("Exposure rows must be a non-empty list.")
        rows_payload = []
    declared_watersheds = set(watershed_ids)
    declared_periods = set(periods)
    seen: set[tuple[str, int]] = set()
    rows: list[HydrologyExposureRow] = []
    for index, item in enumerate(rows_payload, start=1):
        if not isinstance(item, Mapping):
            errors.append(f"Exposure row {index} must be an object.")
            continue
        watershed_id = _required_text(
            item.get("watershed_id"), f"exposure row {index} watershed_id", errors
        )
        if watershed_id and watershed_id not in declared_watersheds:
            errors.append(f"Exposure row {index} names undeclared watershed {watershed_id!r}.")
        period = _required_int(item.get("period"), f"exposure row {index} period", errors)
        if period not in declared_periods:
            errors.append(f"Exposure row {index} names undeclared period {period}.")
        key = (watershed_id, period)
        if key in seen:
            errors.append(f"Duplicate exposure row for watershed {watershed_id!r} period {period}.")
        seen.add(key)
        rows.append(
            HydrologyExposureRow(
                watershed_id=watershed_id,
                period=period,
                road_built_km=_required_number(
                    item.get("road_built_km"), f"exposure row {index} road_built_km", errors
                ),
                road_used_km=_required_number(
                    item.get("road_used_km"), f"exposure row {index} road_used_km", errors
                ),
                road_decommissioned_km=_required_number(
                    item.get("road_decommissioned_km"),
                    f"exposure row {index} road_decommissioned_km",
                    errors,
                ),
                culvert_count=_required_int(
                    item.get("culvert_count"), f"exposure row {index} culvert_count", errors
                ),
                culvert_exposed_count=_required_int(
                    item.get("culvert_exposed_count"),
                    f"exposure row {index} culvert_exposed_count",
                    errors,
                ),
            )
        )
    expected = {(watershed_id, period) for watershed_id in watershed_ids for period in periods}
    missing = sorted(expected - seen)
    if missing:
        first = missing[0]
        errors.append(
            f"Exposure is missing {len(missing)} declared row(s), starting with "
            f"watershed {first[0]!r} period {first[1]}."
        )
    row_count = len(rows)
    if schedule_path is not None:
        try:
            actual_schedule = schedule_sha256(schedule_path)
        except FemicHydrologyExposureError as exc:
            errors.append(str(exc))
        else:
            if declared_schedule and declared_schedule != actual_schedule:
                errors.append(
                    "Exposure schedule hash does not match the assignments CSV; "
                    "regenerate the table for this schedule."
                )
    if any(error.startswith("Exposure is missing") for error in errors):
        warnings.append("The declared watershed/period grid is incomplete.")
    if errors:
        return _report(
            resolved,
            checked,
            errors,
            warnings,
            row_count,
            watershed_count,
            period_count,
            exposure_sha,
            declared_schedule,
        ), None
    caveats = _text_list(payload.get("caveats"), "caveats", errors, allow_empty=True)
    if errors:
        return _report(
            resolved,
            checked,
            errors,
            warnings,
            row_count,
            watershed_count,
            period_count,
            exposure_sha,
            declared_schedule,
        ), None
    rows.sort(key=lambda row: (row.watershed_id, row.period))
    exposure = HydrologyExposure(
        path=resolved,
        sha256=exposure_sha,
        exposure_id=exposure_id,
        generated_utc=generated_utc,
        source_id=source_id,
        review_status=review_status,
        reviewer_id=reviewer_id,
        schedule_sha256=declared_schedule,
        watershed_ids=tuple(watershed_ids),
        periods=periods,
        rows=tuple(rows),
        caveats=caveats,
    )
    return _report(
        resolved,
        checked,
        errors,
        warnings,
        row_count,
        watershed_count,
        period_count,
        exposure_sha,
        declared_schedule,
        valid=True,
    ), exposure


def _report(
    path: Path,
    checked: str,
    errors: list[str],
    warnings: list[str],
    row_count: int,
    watershed_count: int,
    period_count: int,
    exposure_sha: str,
    schedule_sha: str | None,
    *,
    valid: bool | None = None,
) -> HydrologyExposureValidation:
    return HydrologyExposureValidation(
        path=path,
        is_valid=(not errors if valid is None else valid),
        checked_utc=checked,
        errors=tuple(errors),
        warnings=tuple(warnings),
        row_count=row_count,
        watershed_count=watershed_count,
        period_count=period_count,
        exposure_sha256=exposure_sha,
        schedule_sha256=schedule_sha,
    )


def _required_text(value: object, field: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty string.")
        return ""
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None or not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _required_number(value: object, field: str, errors: list[str]) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be a finite non-negative number.")
        return 0.0
    number = float(value)
    if not math.isfinite(number) or number < 0:
        errors.append(f"{field} must be a finite non-negative number.")
        return 0.0
    return number


def _required_int(value: object, field: str, errors: list[str]) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{field} must be a non-negative integer.")
        return 0
    return value


def _text_list(
    value: object, field: str, errors: list[str], *, allow_empty: bool
) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{field} must be a list of strings.")
        return ()
    items = tuple(item.strip() for item in value if item.strip())
    if not allow_empty and not items:
        errors.append(f"{field} must not be empty.")
    return items


def _int_list(
    value: object, field: str, errors: list[str], *, allow_empty: bool
) -> tuple[int, ...]:
    if not isinstance(value, list):
        errors.append(f"{field} must be a list of non-negative integers.")
        return ()
    items: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            errors.append(f"{field} must be a list of non-negative integers.")
            continue
        items.append(item)
    if not allow_empty and not items:
        errors.append(f"{field} must not be empty.")
    return tuple(items)
