"""Dataset quality checks for machine availability and ground-support evidence.

The inspector is advisory by default: it reports data-quality deviations that
do not make a scenario invalid. Missing or checksum-invalid ground-support
references are errors because the scenario explicitly pins them.

The 24 h/day machine baseline is the FHOPS convention for shipped examples
(year-round operations with only brief shutdowns). Deviations are allowed, but
they should be explicit and reviewed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fhops.scenario.contract.models import Scenario
from fhops.scenario.lidar_ground_summary import GroundSummaryError, inspect_ground_support

DATA_QUALITY_SCHEMA = "fhops.data_quality.v1"
DAILY_HOURS_BASELINE = 24.0


@dataclass(frozen=True)
class DataQualityIssue:
    """One machine or ground-support quality finding.

    Attributes
    ----------
    severity:
        ``"warning"`` for non-blocking deviations, ``"error"`` for pinned
        evidence that cannot be consumed.
    code:
        Stable machine-readable identifier.
    entity_id:
        Machine or block id associated with the finding, or an empty string.
    message:
        Human-readable explanation.
    """

    severity: str
    code: str
    entity_id: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-friendly issue mapping."""
        return {
            "severity": self.severity,
            "code": self.code,
            "entity_id": self.entity_id,
            "message": self.message,
        }


@dataclass(frozen=True)
class DataQualityReport:
    """Scenario data-quality findings.

    Attributes
    ----------
    scenario_name:
        Scenario label.
    scenario_path:
        Resolved scenario YAML path, when known.
    issues:
        Findings in deterministic machine/ground-support order.
    """

    scenario_name: str
    scenario_path: str
    issues: tuple[DataQualityIssue, ...]

    @property
    def warnings(self) -> tuple[DataQualityIssue, ...]:
        """Return non-blocking findings."""
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    @property
    def errors(self) -> tuple[DataQualityIssue, ...]:
        """Return findings that make pinned evidence unusable."""
        return tuple(issue for issue in self.issues if issue.severity == "error")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly report."""
        return {
            "schema_version": DATA_QUALITY_SCHEMA,
            "scenario_name": self.scenario_name,
            "scenario_path": self.scenario_path,
            "issue_count": len(self.issues),
            "warning_count": len(self.warnings),
            "error_count": len(self.errors),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def inspect_data_quality(
    scenario: Scenario, scenario_path: str | Path | None = None
) -> DataQualityReport:
    """Inspect one scenario for machine and ground-support quality issues.

    Parameters
    ----------
    scenario:
        Loaded scenario contract.
    scenario_path:
        Optional scenario YAML path used to resolve an optional
        ``ground_support`` reference.

    Returns
    -------
    DataQualityReport
        Deterministic findings. Machine daily-hour deviations are warnings;
        invalid pinned ground-support references are errors.
    """
    issues: list[DataQualityIssue] = []
    for machine in sorted(scenario.machines, key=lambda item: item.id):
        if abs(machine.daily_hours - DAILY_HOURS_BASELINE) > 1e-6:
            issues.append(
                DataQualityIssue(
                    severity="warning",
                    code="machine_daily_hours",
                    entity_id=machine.id,
                    message=(
                        f"machine {machine.id!r} daily_hours={machine.daily_hours:g} "
                        f"differs from the {DAILY_HOURS_BASELINE:g} h/day baseline."
                    ),
                )
            )
        if machine.daily_hours <= 0:
            issues.append(
                DataQualityIssue(
                    severity="warning",
                    code="machine_unavailable",
                    entity_id=machine.id,
                    message=f"machine {machine.id!r} has daily_hours={machine.daily_hours:g}.",
                )
            )

    if scenario.ground_support is not None and scenario_path is not None:
        try:
            ground = inspect_ground_support(scenario_path)
        except GroundSummaryError as exc:
            issues.append(
                DataQualityIssue(
                    severity="error",
                    code="ground_support_invalid",
                    entity_id=scenario.ground_support.summary_path,
                    message=str(exc),
                )
            )
        else:
            for block_id in ground.missing_block_ids:
                issues.append(
                    DataQualityIssue(
                        severity="warning",
                        code="ground_summary_missing_block",
                        entity_id=block_id,
                        message=f"block {block_id!r} has no row in the ground summary.",
                    )
                )
            for block_id in ground.unknown_block_ids:
                issues.append(
                    DataQualityIssue(
                        severity="warning",
                        code="ground_summary_unknown_block",
                        entity_id=block_id,
                        message=f"ground summary block {block_id!r} is not in the scenario.",
                    )
                )
            for message in ground.warnings:
                issues.append(
                    DataQualityIssue(
                        severity="warning",
                        code="ground_summary_warning",
                        entity_id="",
                        message=message,
                    )
                )

    return DataQualityReport(
        scenario_name=scenario.name,
        scenario_path=str(Path(scenario_path).resolve()) if scenario_path else "",
        issues=tuple(issues),
    )


__all__ = [
    "DAILY_HOURS_BASELINE",
    "DATA_QUALITY_SCHEMA",
    "DataQualityIssue",
    "DataQualityReport",
    "inspect_data_quality",
]
