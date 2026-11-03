"""Read-only salvage shelf-life report consumer.

This module joins an explicit storage/age table to a validated FHOPS scenario and
applies the published curves in :mod:`fhops.salvage.degradation`. It does not
schedule, price, or optimise anything. The scenario remains the authority for
block volume; the side table supplies only the age since fire or tree death.

The report is intentionally conservative:

* every block id must resolve to a scenario block;
* ages must be finite and non-negative;
* the output names the curve, source, and applicability boundary;
* an optional value is computed only when the caller supplies a price per cubic
  metre, and that price is labelled as a caller assumption.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from fhops.salvage.degradation import (
    DEFAULT_CURVE_ID,
    DecayCurve,
    DecayCurveLibrary,
    load_decay_library,
)
from fhops.scenario.io import load_scenario

__all__ = [
    "REQUIRED_STORAGE_COLUMNS",
    "SalvageReport",
    "build_salvage_report",
    "write_salvage_report",
]

#: Columns the storage/age table must provide.
REQUIRED_STORAGE_COLUMNS = ("block_id", "years_since_disturbance")

_REPORT_COLUMNS = (
    "block_id",
    "years_since_disturbance",
    "salvage_processing_mode",
    "is_salvage_block",
    "retention_fraction",
    "original_volume_m3",
    "retained_volume_m3",
    "value_per_m3",
    "retained_value",
    "eligible_products",
    "curve_id",
)


@dataclass(frozen=True)
class SalvageReport:
    """Result of joining a storage/age table to a scenario.

    Attributes
    ----------
    frame:
        Deterministic per-block table with the columns listed in
        :data:`_REPORT_COLUMNS`. ``retained_value`` is ``None`` when the caller
        did not supply a price.
    curve:
        The applied retention curve, including provenance and boundary text.
    library:
        The full curve library, used to expose product windows and sources.
    blocks_without_salvage_mode:
        Scenario block ids in the table that do not declare a
        ``salvage_processing_mode``. They are reported, not rejected, because
        some callers use salvage systems without setting the optional field.
    """

    frame: pd.DataFrame
    curve: DecayCurve
    library: DecayCurveLibrary
    blocks_without_salvage_mode: tuple[str, ...]

    @property
    def total_original_volume_m3(self) -> float:
        """Original volume in the report, in cubic metres."""

        return float(self.frame["original_volume_m3"].sum())

    @property
    def total_retained_volume_m3(self) -> float:
        """Retained volume in the report, in cubic metres."""

        return float(self.frame["retained_volume_m3"].sum())

    @property
    def total_retained_value(self) -> float | None:
        """Retained value when a price was supplied, otherwise ``None``."""

        if self.frame["retained_value"].isna().all():
            return None
        return float(self.frame["retained_value"].fillna(0.0).sum())


def _read_storage_table(storage_table: str | Path | pd.DataFrame) -> pd.DataFrame:
    if isinstance(storage_table, pd.DataFrame):
        frame = storage_table.copy()
    else:
        frame = pd.read_csv(storage_table)

    missing = [column for column in REQUIRED_STORAGE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError("storage table is missing required columns: " + ", ".join(missing))
    if frame.empty:
        raise ValueError("storage table must contain at least one row")

    frame = frame.loc[:, list(REQUIRED_STORAGE_COLUMNS)].copy()
    frame["block_id"] = frame["block_id"].astype(str).str.strip()
    if (frame["block_id"] == "").any():
        raise ValueError("storage table contains an empty block_id")
    if frame["block_id"].duplicated().any():
        duplicates = sorted(frame.loc[frame["block_id"].duplicated(), "block_id"].unique())
        raise ValueError("storage table has duplicate block_id rows: " + ", ".join(duplicates))

    ages = pd.to_numeric(frame["years_since_disturbance"], errors="coerce")
    if ages.isna().any():
        raise ValueError("years_since_disturbance must be numeric for every row")
    if (ages < 0.0).any():
        raise ValueError("years_since_disturbance must be non-negative")
    frame["years_since_disturbance"] = ages.astype(float)
    return frame.reset_index(drop=True)


def build_salvage_report(
    scenario_path: str | Path,
    storage_table: str | Path | pd.DataFrame,
    *,
    curve_id: str = DEFAULT_CURVE_ID,
    value_per_m3: float | None = None,
    library: DecayCurveLibrary | None = None,
) -> SalvageReport:
    """Build a per-block salvage retention report.

    Parameters
    ----------
    scenario_path:
        Path to a standard FHOPS ``scenario.yaml``. Blocks supply
        ``work_required`` (original volume, m³) and the optional
        ``salvage_processing_mode``.
    storage_table:
        CSV path or DataFrame with ``block_id`` and
        ``years_since_disturbance`` columns. Ages are years since fire or tree
        death and must be non-negative. Duplicate block rows are rejected so
        the report has one deterministic row per block.
    curve_id:
        Curve identifier from the packaged library. Defaults to the published
        Pacific Northwest fire-killed mixed-conifer curve.
    value_per_m3:
        Optional caller-supplied value per cubic metre of retained volume. When
        omitted, ``retained_value`` is blank. This is not a price forecast.
    library:
        Optional pre-loaded curve library. ``None`` loads the packaged data.

    Returns
    -------
    SalvageReport
        Deterministic per-block table plus the applied curve and library.

    Raises
    ------
    ValueError
        If required columns are missing, ages are invalid, block ids are
        duplicated, a block id is not in the scenario, or ``value_per_m3`` is
        negative.
    KeyError
        If ``curve_id`` is not present in the library.
    FileNotFoundError
        If the scenario or storage table does not exist.
    """

    if value_per_m3 is not None and value_per_m3 < 0.0:
        raise ValueError("value_per_m3 must be non-negative")

    resolved_library = library or load_decay_library()
    curve = resolved_library.curve(curve_id)
    scenario = load_scenario(scenario_path)
    blocks = {block.id: block for block in scenario.blocks}
    storage = _read_storage_table(storage_table)

    unknown = sorted(set(storage["block_id"]) - set(blocks))
    if unknown:
        raise ValueError(
            "storage table references blocks not present in the scenario: " + ", ".join(unknown)
        )

    rows: list[dict[str, Any]] = []
    for record in storage.to_dict("records"):
        block_id = str(record["block_id"])
        age = float(record["years_since_disturbance"])
        block = blocks[block_id]
        retention = curve.retention_at(age)
        original_volume = float(block.work_required)
        retained_volume = original_volume * retention
        mode = block.salvage_processing_mode
        rows.append(
            {
                "block_id": block_id,
                "years_since_disturbance": age,
                "salvage_processing_mode": "" if mode is None else mode.value,
                "is_salvage_block": mode is not None,
                "retention_fraction": retention,
                "original_volume_m3": original_volume,
                "retained_volume_m3": retained_volume,
                "value_per_m3": value_per_m3,
                "retained_value": None if value_per_m3 is None else retained_volume * value_per_m3,
                "eligible_products": ";".join(resolved_library.eligible_products(age)),
                "curve_id": curve.curve_id,
            }
        )

    frame = pd.DataFrame(rows, columns=list(_REPORT_COLUMNS))
    missing_modes = tuple(row["block_id"] for row in rows if not bool(row["is_salvage_block"]))
    return SalvageReport(
        frame=frame,
        curve=curve,
        library=resolved_library,
        blocks_without_salvage_mode=missing_modes,
    )


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        return f"{value:.4f}"
    return str(value)


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "---|" * len(columns),
    ]
    for record in frame.to_dict("records"):
        lines.append(
            "| " + " | ".join(_format_cell(record[column]) for column in frame.columns) + " |"
        )
    return "\n".join(lines) + "\n"


def write_salvage_report(report: SalvageReport, out_dir: str | Path) -> dict[str, Path]:
    """Write deterministic CSV and Markdown report artifacts.

    Parameters
    ----------
    report:
        Result from :func:`build_salvage_report`.
    out_dir:
        Directory for ``salvage_shelf_life.csv`` and
        ``salvage_shelf_life.md``. Created when absent.

    Returns
    -------
    dict of str to pathlib.Path
        Mapping with ``csv`` and ``markdown`` keys.
    """

    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "salvage_shelf_life.csv"
    markdown_path = output / "salvage_shelf_life.md"

    report.frame.to_csv(csv_path, index=False, float_format="%.4f")

    windows = "\n".join(
        f"- **{window.product}**: {window.min_years:g}"
        + ("+" if window.max_years is None else f"-{window.max_years:g}")
        + f" years — {window.note}"
        for window in report.library.product_windows
    )
    warning = ""
    if report.blocks_without_salvage_mode:
        warning = (
            "\n## Caveat\n\n"
            "These blocks did not declare `salvage_processing_mode`: "
            + ", ".join(report.blocks_without_salvage_mode)
            + ". They are included because the caller supplied a storage age, but they should not be "
            "read as validated salvage blocks.\n"
        )

    markdown = f"""# Salvage shelf-life report

**Curve:** `{report.curve.curve_id}` — {report.curve.name}

**Retention definition:** {report.curve.retention_definition}

**Source:** {report.curve.source.citation} <{report.curve.source.url}>

**Applicability boundary:** {report.curve.source.boundary}

**Totals:** {report.total_original_volume_m3:.2f} m³ original, {report.total_retained_volume_m3:.2f} m³ retained.

**Product windows (advisory):**

{windows}

{_markdown_table(report.frame)}{warning}
## Limits

This report is read-only. It does not change a schedule, objective, constraint, or solver. The
retention curve is a published reference curve, not a BC-specific, species-specific, or
roadside-storage-specific operational curve. `retained_value` is only present when the caller
supplies `--value-per-m3`; it is a volume-retention proxy at a constant unit value, not a grade
recovery or price forecast.
"""

    markdown_path.write_text(markdown, encoding="utf-8")
    return {"csv": csv_path, "markdown": markdown_path}
