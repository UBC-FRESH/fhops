"""Reviewed operational hazard windows for FHOPS flood-aware constraints.

Hazard windows are an external input. They describe when a watershed is in a
watch, warning, or closure state. FHOPS does not derive them from weather or a
hydrology model at runtime.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

HYDROLOGY_HAZARD_SCHEMA = "fhops.hydrology.hazard.v1"
HYDROLOGY_HAZARD_REVIEW_STATUSES: tuple[str, ...] = (
    "not_reviewed",
    "review_pending",
    "reviewed",
)
HYDROLOGY_HAZARD_SEVERITIES: tuple[str, ...] = ("watch", "warning", "closure")
_SEVERITY_RANK = {"watch": 1, "warning": 2, "closure": 3}

__all__ = [
    "FemicHydrologyHazardError",
    "HYDROLOGY_HAZARD_SCHEMA",
    "HYDROLOGY_HAZARD_SEVERITIES",
    "HydrologyHazard",
    "HydrologyHazardValidation",
    "HydrologyHazardWindow",
    "load_hydrology_hazard",
    "validate_hydrology_hazard",
]


class FemicHydrologyHazardError(RuntimeError):
    """Raised when a hazard-window table cannot be consumed."""


@dataclass(frozen=True)
class HydrologyHazardWindow:
    """One watershed/day hazard window.

    Attributes
    ----------
    watershed_id : str
        FEMIC watershed identifier.
    start_day : int
        Inclusive first day (1-indexed).
    end_day : int
        Inclusive last day.
    severity : str
        ``watch``, ``warning``, or ``closure``.
    return_period_years : float | None
        Optional return period associated with the hazard.
    source_id : str | None
        Optional source identifier for this window.
    notes : str
        Human notes.
    """

    watershed_id: str
    start_day: int
    end_day: int
    severity: str
    return_period_years: float | None
    source_id: str | None
    notes: str

    def covers(self, day: int) -> bool:
        """Return whether the window covers a day.

        Parameters
        ----------
        day : int
            One-indexed day.

        Returns
        -------
        bool
            True when ``start_day <= day <= end_day``.
        """
        return self.start_day <= day <= self.end_day

    def to_dict(self) -> dict[str, object]:
        """Return the window as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Window fields.
        """
        return {
            "watershed_id": self.watershed_id,
            "start_day": self.start_day,
            "end_day": self.end_day,
            "severity": self.severity,
            "return_period_years": self.return_period_years,
            "source_id": self.source_id,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class HydrologyHazard:
    """Loaded and checksummed hazard-window table.

    Attributes
    ----------
    path : Path
        Hazard JSON path.
    sha256 : str
        SHA-256 digest of the file bytes.
    hazard_id : str
        Stable hazard identifier.
    generated_utc : str
        Producer generation timestamp.
    source_id : str
        Source or process that produced the windows.
    review_status : str
        ``not_reviewed``, ``review_pending``, or ``reviewed``.
    reviewer_id : str | None
        Reviewer identifier when reviewed.
    windows : tuple[HydrologyHazardWindow, ...]
        Validated windows.
    caveats : tuple[str, ...]
        Interpretation caveats.
    """

    path: Path
    sha256: str
    hazard_id: str
    generated_utc: str
    source_id: str
    review_status: str
    reviewer_id: str | None
    windows: tuple[HydrologyHazardWindow, ...]
    caveats: tuple[str, ...]

    def severity_for(self, watershed_id: str, day: int) -> str | None:
        """Return the highest severity covering a watershed/day.

        Parameters
        ----------
        watershed_id : str
            FEMIC watershed identifier.
        day : int
            One-indexed day.

        Returns
        -------
        str | None
            ``closure``, ``warning``, ``watch``, or None when no window covers
            the pair.
        """
        severities = [
            window.severity
            for window in self.windows
            if window.watershed_id == watershed_id and window.covers(day)
        ]
        if not severities:
            return None
        return max(severities, key=lambda item: _SEVERITY_RANK[item])

    def to_dict(self) -> dict[str, object]:
        """Return the hazard table as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Schema, identity, review, windows, and caveats.
        """
        return {
            "schema_version": HYDROLOGY_HAZARD_SCHEMA,
            "hazard_id": self.hazard_id,
            "generated_utc": self.generated_utc,
            "source_id": self.source_id,
            "review_status": self.review_status,
            "reviewer_id": self.reviewer_id,
            "windows": [window.to_dict() for window in self.windows],
            "caveats": list(self.caveats),
            "hazard_sha256": self.sha256,
        }


@dataclass(frozen=True)
class HydrologyHazardValidation:
    """Validation report for a hazard-window table.

    Attributes
    ----------
    path : Path
        Hazard path.
    is_valid : bool
        Whether every required check passed.
    checked_utc : str
        Report timestamp.
    errors : tuple[str, ...]
        Blocking findings.
    warnings : tuple[str, ...]
        Non-blocking findings.
    window_count : int
        Number of parsed windows.
    watershed_count : int
        Number of distinct watersheds.
    hazard_sha256 : str
        File digest.
    """

    path: Path
    is_valid: bool
    checked_utc: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    window_count: int
    watershed_count: int
    hazard_sha256: str

    def to_dict(self) -> dict[str, object]:
        """Return the validation report as a JSON-serializable mapping.

        Returns
        -------
        dict[str, object]
            Path, validity, findings, counts, and digest.
        """
        return {
            "path": str(self.path),
            "is_valid": self.is_valid,
            "checked_utc": self.checked_utc,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "window_count": self.window_count,
            "watershed_count": self.watershed_count,
            "hazard_sha256": self.hazard_sha256,
        }


def validate_hydrology_hazard(path: Path) -> HydrologyHazardValidation:
    """Validate a hazard-window table without raising.

    Parameters
    ----------
    path : Path
        Hazard JSON path.

    Returns
    -------
    HydrologyHazardValidation
        Validation report with specific errors and warnings.
    """
    report, _hazard = _load(path)
    return report


def load_hydrology_hazard(path: Path) -> HydrologyHazard:
    """Load and validate a hazard-window table.

    Parameters
    ----------
    path : Path
        Hazard JSON path.

    Returns
    -------
    HydrologyHazard
        Validated hazard windows.

    Raises
    ------
    FemicHydrologyHazardError
        If the table is invalid.
    """
    report, hazard = _load(path)
    if not report.is_valid or hazard is None:
        raise FemicHydrologyHazardError(
            "; ".join(report.errors) or "Invalid hydrology hazard table."
        )
    return hazard


def _load(
    path: Path,
) -> tuple[HydrologyHazardValidation, HydrologyHazard | None]:
    resolved = path.expanduser().resolve()
    checked = datetime.now(UTC).isoformat()
    errors: list[str] = []
    warnings: list[str] = []
    digest = ""
    window_count = 0
    watershed_count = 0
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        return (
            HydrologyHazardValidation(
                path=resolved,
                is_valid=False,
                checked_utc=checked,
                errors=(f"Unable to read hazard table: {exc}",),
                warnings=(),
                window_count=0,
                watershed_count=0,
                hazard_sha256="",
            ),
            None,
        )
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        errors.append(f"Hazard table is not UTF-8: {exc}")
        payload = None
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid hazard JSON: {exc}")
        payload = None
    if not isinstance(payload, Mapping):
        if not errors:
            errors.append("Hazard table must be a JSON object.")
        return _report(resolved, checked, errors, warnings, 0, 0, digest), None
    if payload.get("schema_version") != HYDROLOGY_HAZARD_SCHEMA:
        errors.append(f"Unsupported hazard schema {payload.get('schema_version')!r}.")
    hazard_id = _required_text(payload.get("hazard_id"), "hazard_id", errors)
    generated_utc = _required_text(payload.get("generated_utc"), "generated_utc", errors)
    source_id = _required_text(payload.get("source_id"), "source_id", errors)
    review_status = _required_text(payload.get("review_status"), "review_status", errors)
    if review_status and review_status not in HYDROLOGY_HAZARD_REVIEW_STATUSES:
        errors.append(f"Unsupported review_status {review_status!r}.")
    reviewer_id = _optional_text(payload.get("reviewer_id"))
    if review_status == "reviewed" and reviewer_id is None:
        errors.append("Reviewed hazard table requires reviewer_id.")
    caveats = _text_list(payload.get("caveats"), "caveats", errors, allow_empty=False)
    windows_payload = payload.get("windows")
    if not isinstance(windows_payload, list) or not windows_payload:
        errors.append("Hazard windows must be a non-empty list.")
        windows_payload = []
    windows: list[HydrologyHazardWindow] = []
    seen: set[tuple[str, int, int, str]] = set()
    for index, item in enumerate(windows_payload, start=1):
        if not isinstance(item, Mapping):
            errors.append(f"Hazard window {index} must be an object.")
            continue
        window = _window(item, index, errors)
        if window is None:
            continue
        key = (
            window.watershed_id,
            window.start_day,
            window.end_day,
            window.severity,
        )
        if key in seen:
            errors.append(
                "Duplicate hazard window for "
                f"watershed {window.watershed_id!r} days "
                f"{window.start_day}-{window.end_day} severity {window.severity!r}."
            )
        seen.add(key)
        windows.append(window)
    for left_index, left in enumerate(windows):
        for right in windows[left_index + 1 :]:
            if left.watershed_id != right.watershed_id:
                continue
            if not _overlap(left, right):
                continue
            if left.severity == right.severity:
                errors.append(
                    "Overlapping hazard windows of the same severity for "
                    f"watershed {left.watershed_id!r}."
                )
            else:
                warnings.append(
                    "Overlapping hazard windows with different severity for "
                    f"watershed {left.watershed_id!r}; the highest severity applies."
                )
    window_count = len(windows)
    watershed_count = len({window.watershed_id for window in windows})
    if errors:
        return _report(
            resolved,
            checked,
            errors,
            warnings,
            window_count,
            watershed_count,
            digest,
        ), None
    windows.sort(key=lambda window: (window.watershed_id, window.start_day, window.end_day))
    hazard = HydrologyHazard(
        path=resolved,
        sha256=digest,
        hazard_id=hazard_id,
        generated_utc=generated_utc,
        source_id=source_id,
        review_status=review_status,
        reviewer_id=reviewer_id,
        windows=tuple(windows),
        caveats=caveats,
    )
    return _report(
        resolved,
        checked,
        errors,
        warnings,
        window_count,
        watershed_count,
        digest,
        valid=True,
    ), hazard


def _window(
    item: Mapping[str, object], index: int, errors: list[str]
) -> HydrologyHazardWindow | None:
    watershed_id = _required_text(
        item.get("watershed_id"), f"hazard window {index} watershed_id", errors
    )
    start_day = _required_int(item.get("start_day"), f"hazard window {index} start_day", errors)
    end_day = _required_int(item.get("end_day"), f"hazard window {index} end_day", errors)
    severity = _required_text(item.get("severity"), f"hazard window {index} severity", errors)
    if severity and severity not in HYDROLOGY_HAZARD_SEVERITIES:
        errors.append(f"Hazard window {index} has unsupported severity {severity!r}.")
    if start_day < 1 or end_day < 1:
        errors.append(f"Hazard window {index} days must be >= 1.")
    if start_day > end_day:
        errors.append(f"Hazard window {index} start_day must be <= end_day.")
    return_period = _optional_positive(
        item.get("return_period_years"),
        f"hazard window {index} return_period_years",
        errors,
    )
    source = _optional_text(item.get("source_id"))
    notes = _optional_text(item.get("notes")) or ""
    if not watershed_id or not severity:
        return None
    return HydrologyHazardWindow(
        watershed_id=watershed_id,
        start_day=start_day,
        end_day=end_day,
        severity=severity,
        return_period_years=return_period,
        source_id=source,
        notes=notes,
    )


def _overlap(left: HydrologyHazardWindow, right: HydrologyHazardWindow) -> bool:
    return left.start_day <= right.end_day and right.start_day <= left.end_day


def _report(
    path: Path,
    checked: str,
    errors: list[str],
    warnings: list[str],
    window_count: int,
    watershed_count: int,
    digest: str,
    *,
    valid: bool | None = None,
) -> HydrologyHazardValidation:
    return HydrologyHazardValidation(
        path=path,
        is_valid=(not errors if valid is None else valid),
        checked_utc=checked,
        errors=tuple(errors),
        warnings=tuple(warnings),
        window_count=window_count,
        watershed_count=watershed_count,
        hazard_sha256=digest,
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


def _required_int(value: object, field: str, errors: list[str]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{field} must be an integer.")
        return 0
    return value


def _optional_positive(value: object, field: str, errors: list[str]) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be a positive finite number.")
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        errors.append(f"{field} must be a positive finite number.")
        return None
    return number


def _text_list(
    value: object, field: str, errors: list[str], *, allow_empty: bool
) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{field} must be a list of non-empty strings.")
        return ()
    items = tuple(item.strip() for item in value)
    if any(not item for item in items):
        errors.append(f"{field} must be a list of non-empty strings.")
        return ()
    if not allow_empty and not items:
        errors.append(f"{field} must not be empty.")
    return items
