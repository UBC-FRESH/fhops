"""Read-only FHOPS support report for FEMIC ground-summary CSV files.

The summary is produced by ``femic lidar ground-summary`` and uses
``femic.ground-summary.v1``. FHOPS only inspects it: it does not write the scenario, change
``lidar_support``, or run the solver. The report shows which scenario blocks have ground
evidence and which are missing or unknown.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from fhops.scenario.io import load_scenario

GROUND_SUMMARY_SCHEMA_VERSION = "femic.ground-summary.v1"
GROUND_SUMMARY_METRIC_COLUMNS: tuple[str, ...] = (
    "point_count",
    "ground_count",
    "ground_fraction",
    "low_count",
    "low_fraction",
    "hag_mean",
    "hag_p50",
    "hag_p95",
    "hag_max",
)


class GroundSummaryError(RuntimeError):
    """Raised when a ground-summary CSV cannot be consumed."""


@dataclass(frozen=True)
class GroundSummaryRecord:
    """One block row from a FEMIC ground summary.

    Attributes
    ----------
    block_id : str
        Block identifier.
    point_count : int
        Points in the block.
    ground_count : int
        Predicted-ground points.
    ground_fraction : float
        Ground count divided by point count.
    low_count : int
        Low-point-flagged points.
    low_fraction : float
        Low count divided by point count.
    hag_mean_m : float or None
        Mean HAG, in metres.
    hag_p50_m : float or None
        Median HAG.
    hag_p95_m : float or None
        95th percentile HAG.
    hag_max_m : float or None
        Maximum HAG.
    """

    block_id: str
    point_count: int
    ground_count: int
    ground_fraction: float
    low_count: int
    low_fraction: float
    hag_mean_m: float | None
    hag_p50_m: float | None
    hag_p95_m: float | None
    hag_max_m: float | None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly row.

        Returns
        -------
        dict
            Row fields.
        """
        return {
            "block_id": self.block_id,
            "point_count": self.point_count,
            "ground_count": self.ground_count,
            "ground_fraction": self.ground_fraction,
            "low_count": self.low_count,
            "low_fraction": self.low_fraction,
            "hag_mean_m": self.hag_mean_m,
            "hag_p50_m": self.hag_p50_m,
            "hag_p95_m": self.hag_p95_m,
            "hag_max_m": self.hag_max_m,
        }


@dataclass(frozen=True)
class GroundSupportRow:
    """A matched block/ground-summary row.

    Attributes
    ----------
    block_id : str
        Scenario block identifier.
    point_count : int
        Points in the block.
    ground_fraction : float
        Predicted-ground fraction.
    low_fraction : float
        Low-point fraction.
    hag_mean_m : float or None
        Mean HAG.
    hag_p95_m : float or None
        95th percentile HAG.
    """

    block_id: str
    point_count: int
    ground_fraction: float
    low_fraction: float
    hag_mean_m: float | None
    hag_p95_m: float | None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly row.

        Returns
        -------
        dict
            Row fields.
        """
        return {
            "block_id": self.block_id,
            "point_count": self.point_count,
            "ground_fraction": self.ground_fraction,
            "low_fraction": self.low_fraction,
            "hag_mean_m": self.hag_mean_m,
            "hag_p95_m": self.hag_p95_m,
        }


@dataclass(frozen=True)
class GroundSupportReport:
    """Read-only report for a ground summary against a scenario.

    Attributes
    ----------
    scenario_path : Path
        Scenario path.
    summary_path : Path
        Ground-summary CSV path.
    rows : tuple of GroundSupportRow
        Matched block rows.
    missing_block_ids : tuple of str
        Scenario blocks without a summary row.
    unknown_block_ids : tuple of str
        Summary rows whose block is not in the scenario.
    warnings : tuple of str
        Non-fatal warnings.
    """

    scenario_path: Path
    summary_path: Path
    rows: tuple[GroundSupportRow, ...]
    missing_block_ids: tuple[str, ...]
    unknown_block_ids: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly report.

        Returns
        -------
        dict
            Paths, rows, missing/unknown IDs, and warnings.
        """
        return {
            "schema_version": GROUND_SUMMARY_SCHEMA_VERSION,
            "scenario_path": str(self.scenario_path),
            "summary_path": str(self.summary_path),
            "row_count": len(self.rows),
            "rows": [row.to_dict() for row in self.rows],
            "missing_block_ids": list(self.missing_block_ids),
            "unknown_block_ids": list(self.unknown_block_ids),
            "warnings": list(self.warnings),
        }


def _number(value: str | None, label: str) -> float | None:
    """Parse an optional floating-point CSV value.

    Parameters
    ----------
    value : str or None
        Raw field.
    label : str
        Field label for errors.

    Returns
    -------
    float or None
        Parsed value, or ``None`` for an empty field.

    Raises
    ------
    GroundSummaryError
        When the value is not a finite number.
    """
    if value is None or not value.strip():
        return None
    try:
        number = float(value)
    except ValueError as exc:
        raise GroundSummaryError(f"field '{label}' is not a number: {value!r}") from exc
    if not math.isfinite(number):
        raise GroundSummaryError(f"field '{label}' is not finite: {value!r}")
    return number


def _integer(value: str | None, label: str) -> int:
    """Parse a required integer CSV value.

    Parameters
    ----------
    value : str or None
        Raw field.
    label : str
        Field label for errors.

    Returns
    -------
    int
        Parsed integer.

    Raises
    ------
    GroundSummaryError
        When the value is missing or not an integer.
    """
    if value is None or not value.strip():
        raise GroundSummaryError(f"field '{label}' is required")
    try:
        return int(value)
    except ValueError as exc:
        raise GroundSummaryError(f"field '{label}' is not an integer: {value!r}") from exc


def _read_summary(
    path: Path,
    *,
    id_field: str = "block_id",
) -> dict[str, GroundSummaryRecord]:
    """Read and validate a ground-summary CSV.

    Parameters
    ----------
    path : Path
        CSV path.

    Returns
    -------
    dict
        Block ID to record.

    Raises
    ------
    GroundSummaryError
        When the file is missing, malformed, or has duplicate blocks.
    """
    try:
        handle = path.open("r", encoding="utf-8", newline="")
    except FileNotFoundError as exc:
        raise GroundSummaryError(f"ground summary does not exist: {path}") from exc
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise GroundSummaryError("ground summary has no header")
        if id_field in reader.fieldnames:
            id_column = id_field
        elif "polygon_id" in reader.fieldnames:
            id_column = "polygon_id"
        else:
            raise GroundSummaryError(f"ground summary has no '{id_field}' or 'polygon_id' column")
        missing = [name for name in GROUND_SUMMARY_METRIC_COLUMNS if name not in reader.fieldnames]
        if missing:
            raise GroundSummaryError("ground summary is missing columns: " + ", ".join(missing))
        records: dict[str, GroundSummaryRecord] = {}
        for line, row in enumerate(reader, start=2):
            block_id = (row.get(id_column) or "").strip()
            if not block_id:
                raise GroundSummaryError(f"row {line} has no block_id")
            if block_id in records:
                raise GroundSummaryError(f"duplicate block_id {block_id!r}")
            point_count = _integer(row.get("point_count"), "point_count")
            ground_count = _integer(row.get("ground_count"), "ground_count")
            low_count = _integer(row.get("low_count"), "low_count")
            ground_fraction = _number(row.get("ground_fraction"), "ground_fraction")
            low_fraction = _number(row.get("low_fraction"), "low_fraction")
            if ground_fraction is None or low_fraction is None:
                raise GroundSummaryError(f"row {line} has no fraction")
            if not 0 <= ground_fraction <= 1 or not 0 <= low_fraction <= 1:
                raise GroundSummaryError(f"row {line} fractions must be in [0, 1]")
            if not 0 <= ground_count <= point_count or not 0 <= low_count <= point_count:
                raise GroundSummaryError(f"row {line} counts exceed point_count")
            records[block_id] = GroundSummaryRecord(
                block_id=block_id,
                point_count=point_count,
                ground_count=ground_count,
                ground_fraction=ground_fraction,
                low_count=low_count,
                low_fraction=low_fraction,
                hag_mean_m=_number(row.get("hag_mean"), "hag_mean"),
                hag_p50_m=_number(row.get("hag_p50"), "hag_p50"),
                hag_p95_m=_number(row.get("hag_p95"), "hag_p95"),
                hag_max_m=_number(row.get("hag_max"), "hag_max"),
            )
    if not records:
        raise GroundSummaryError("ground summary has no block rows")
    return records


def inspect_ground_summary(
    scenario_path: str | Path,
    summary_path: str | Path,
    *,
    id_field: str = "block_id",
) -> GroundSupportReport:
    """Match a FEMIC ground summary to a scenario's blocks.

    Parameters
    ----------
    scenario_path : str or Path
        FHOPS scenario YAML.
    summary_path : str or Path
        FEMIC ``femic.ground-summary.v1`` CSV.
    id_field : str
        Preferred block identifier column. ``polygon_id`` is accepted as a fallback.

    Returns
    -------
    GroundSupportReport
        Matched rows, missing/unknown block IDs, and warnings.

    Raises
    ------
    GroundSummaryError
        When the scenario or summary is invalid.
    """
    scenario_file = Path(scenario_path).expanduser().resolve()
    summary_file = Path(summary_path).expanduser().resolve()
    try:
        scenario = load_scenario(scenario_file)
    except (ValueError, FileNotFoundError) as exc:
        raise GroundSummaryError(f"cannot load scenario: {exc}") from exc
    records = _read_summary(summary_file, id_field=id_field)
    scenario_ids = set(scenario.block_ids())
    matched = sorted(scenario_ids & set(records))
    missing = sorted(scenario_ids - set(records))
    unknown = sorted(set(records) - scenario_ids)
    warnings: list[str] = []
    if missing:
        warnings.append(f"{len(missing)} scenario blocks have no ground summary")
    if unknown:
        warnings.append(f"{len(unknown)} summary blocks are not in the scenario")
    if not matched:
        warnings.append("no scenario blocks matched the ground summary")
    rows = tuple(
        GroundSupportRow(
            block_id=block_id,
            point_count=records[block_id].point_count,
            ground_fraction=records[block_id].ground_fraction,
            low_fraction=records[block_id].low_fraction,
            hag_mean_m=records[block_id].hag_mean_m,
            hag_p95_m=records[block_id].hag_p95_m,
        )
        for block_id in matched
    )
    return GroundSupportReport(
        scenario_path=scenario_file,
        summary_path=summary_file,
        rows=rows,
        missing_block_ids=tuple(missing),
        unknown_block_ids=tuple(unknown),
        warnings=tuple(warnings),
    )
