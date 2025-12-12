"""Reporting helpers for rolling-horizon plans."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from fhops.evaluation.metrics.kpis import KPIResult
from fhops.scenario.contract import Problem
from fhops.scenario.contract.models import Scenario, ScheduleLock

from .rolling import (
    RollingKPIComparison,
    RollingPlanResult,
    compute_rolling_kpis,
)
from .rolling import (
    rolling_assignments_dataframe as _rolling_assignments_dataframe,
)

__all__ = [
    "RollingPlanComparison",
    "evaluate_rolling_plan",
    "rolling_assignments_dataframe",
    "comparison_dataframe",
]


@dataclass(slots=True)
class RollingPlanComparison:
    """Bundle containing KPI totals for rolling vs. baseline plans.

    Attributes
    ----------
    rolling_kpis : KPIResult
        KPI bundle computed from the locked assignments emitted by the rolling planner. Contains
        scalar totals plus cached shift/day calendars via :class:`fhops.evaluation.metrics.kpis.KPIResult`.
    baseline_kpis : KPIResult | None
        KPI bundle computed from a full-horizon baseline such as a monolithic MILP solve. ``None``
        when a baseline DataFrame or lock list is not supplied.
    deltas : dict[str, float]
        Numeric KPI differences keyed by ``<metric>_delta`` and ``<metric>_pct_delta`` (when a
        non-zero baseline exists). Only numeric KPI entries are compared.
    metadata : dict[str, object]
        Copy of :class:`fhops.planning.rolling.RollingPlanResult.metadata` with the additional
        ``baseline_label`` and assignment counts so telemetry exports can capture context.
    """

    rolling_kpis: KPIResult
    baseline_kpis: KPIResult | None
    deltas: dict[str, float]
    metadata: dict[str, object]


rolling_assignments_dataframe = _rolling_assignments_dataframe


def evaluate_rolling_plan(
    result: RollingPlanResult,
    scenario: Scenario | Problem,
    *,
    baseline_assignments: pd.DataFrame | Sequence[ScheduleLock] | None = None,
    baseline_label: str = "single_horizon",
) -> RollingPlanComparison:
    """Compute KPI and playback deltas between a rolling plan and a baseline plan.

    Parameters
    ----------
    result :
        Locked plan and iteration summaries produced by :func:`fhops.planning.solve_rolling_plan`
        or :func:`fhops.planning.run_rolling_horizon`.
    scenario :
        Scenario or operational problem used to evaluate the plan (typically the same scenario used
        to generate ``result``).
    baseline_assignments :
        Optional baseline schedule to compare against. Accepts either a schedule DataFrame with
        ``machine_id``, ``block_id``, ``day`` (and optional ``shift_id``) columns or a sequence of
        :class:`fhops.scenario.contract.models.ScheduleLock` entries. Use a monolithic MILP/SA
        schedule to quantify rolling suboptimality; pass ``None`` to skip baseline deltas.
    baseline_label :
        Label describing the baseline schedule (e.g., ``"full_mip_600s"``). This value is threaded
        into the comparison metadata so telemetry exports remain traceable.

    Returns
    -------
    RollingPlanComparison
        KPI totals for the rolling run, baseline KPIs when provided, per-metric deltas, and merged
        metadata that includes assignment counts and the ``baseline_label``.

    Raises
    ------
    TypeError
        If ``baseline_assignments`` is not a DataFrame or sequence of ``ScheduleLock`` items.
    """

    comparison: RollingKPIComparison = compute_rolling_kpis(
        scenario,
        result,
        baseline_assignments=baseline_assignments,
    )

    metadata = dict(result.metadata)
    metadata["baseline_label"] = baseline_label if comparison.baseline_kpis is not None else None
    metadata["rolling_assignment_count"] = len(comparison.rolling_assignments)
    baseline_count = (
        len(comparison.baseline_assignments) if comparison.baseline_assignments is not None else 0
    )
    metadata["baseline_assignment_count"] = baseline_count

    return RollingPlanComparison(
        rolling_kpis=comparison.rolling_kpis,
        baseline_kpis=comparison.baseline_kpis,
        deltas=comparison.delta_totals or {},
        metadata=metadata,
    )


def comparison_dataframe(
    comparison: RollingPlanComparison, *, metrics: Sequence[str] | None = None
) -> pd.DataFrame:
    """Return a tidy DataFrame of rolling vs. baseline KPIs for plotting.

    Parameters
    ----------
    comparison :
        KPI bundle returned by :func:`evaluate_rolling_plan`. Must contain deltas for each metric of
        interest when a baseline is supplied.
    metrics :
        Optional subset of KPI metric names to include. Defaults to all keys present in
        ``comparison.rolling_kpis``.

    Returns
    -------
    pandas.DataFrame
        DataFrame with columns ``metric``, ``rolling``, ``baseline``, ``delta``, ``pct_delta``, and
        ``baseline_label``. Rows contain one metric per KPI, suitable for plotting or Markdown
        table generation.
    """

    baseline_kpis = comparison.baseline_kpis
    rows: list[dict[str, float | str | None]] = []

    if metrics is None:
        metrics = sorted(comparison.rolling_kpis.keys())

    for metric in metrics:
        rolling_value = comparison.rolling_kpis.get(metric)
        baseline_value = None
        if baseline_kpis is not None:
            baseline_value = baseline_kpis.get(metric)

        if rolling_value is None and baseline_value is None:
            continue

        delta_key = f"{metric}_delta"
        pct_delta_key = f"{metric}_pct_delta"
        label_value = comparison.metadata.get("baseline_label")
        label_str = str(label_value) if label_value is not None else None
        rows.append(
            {
                "metric": metric,
                "rolling": rolling_value,
                "baseline": baseline_value,
                "delta": comparison.deltas.get(delta_key) if comparison.deltas else None,
                "pct_delta": comparison.deltas.get(pct_delta_key) if comparison.deltas else None,
                "baseline_label": label_str,
            }
        )

    return pd.DataFrame(
        rows,
        columns=["metric", "rolling", "baseline", "delta", "pct_delta", "baseline_label"],
    )
