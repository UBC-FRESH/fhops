#!/usr/bin/env python
"""Aggregate multiple tuner_report.csv files and compare objectives across runs."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import pandas as pd


def _parse_report_arg(entry: str) -> tuple[str, Path]:
    if "=" in entry:
        label, path_str = entry.split("=", 1)
        label = label.strip()
        path = Path(path_str.strip())
    else:
        path = Path(entry.strip())
        label = path.stem
    if path.is_dir():
        path = path / "tuner_report.csv"
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    return label, path


def _load_report(label: str, path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"algorithm", "scenario", "best_objective", "mean_objective", "runs"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Report {path} missing columns: {sorted(missing)}")
    df = df.copy()
    df["algorithm"] = df["algorithm"].str.lower().str.strip()
    df["scenario"] = df["scenario"].str.strip()
    if "best_run_id" not in df.columns:
        df["best_run_id"] = None
    df.rename(
        columns={
            "best_objective": f"best_{label}",
            "mean_objective": f"mean_{label}",
            "runs": f"runs_{label}",
            "best_run_id": f"best_run_id_{label}",
        },
        inplace=True,
    )
    subset = [
        "algorithm",
        "scenario",
        f"best_run_id_{label}",
        f"best_{label}",
        f"mean_{label}",
        f"runs_{label}",
    ]
    return df[subset]


def _merge_reports(reports: Iterable[pd.DataFrame]) -> pd.DataFrame:
    iterator = iter(reports)
    try:
        combined = next(iterator)
    except StopIteration:
        raise ValueError("At least one report is required.")
    for df in iterator:
        combined = combined.merge(df, on=["algorithm", "scenario"], how="outer")
    combined.sort_values(["scenario", "algorithm"], inplace=True)
    return combined.reset_index(drop=True)


def _format_markdown(df: pd.DataFrame, labels: list[str]) -> str:
    headers = ["Algorithm", "Scenario"]
    for label in labels:
        headers.extend(
            [
                f"Best ({label})",
                f"Δ Best ({label})" if label != labels[0] else "",
                f"Mean ({label})",
                f"Runs ({label})",
            ]
        )
    headers = [h for h in headers if h]

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    baseline = labels[0]
    for _, row in df.iterrows():
        cells = [row["algorithm"], row["scenario"]]
        base_best = row.get(f"best_{baseline}")
        for label in labels:
            best_val = row.get(f"best_{label}")
            mean_val = row.get(f"mean_{label}")
            runs_val = row.get(f"runs_{label}")
            cells.append(_format_number(best_val))
            if label != baseline:
                diff = None
                if pd.notna(best_val) and pd.notna(base_best):
                    diff = best_val - base_best
                cells.append(_format_number(diff, prefix="+"))
            cells.append(_format_number(mean_val))
            cells.append(str(int(runs_val)) if pd.notna(runs_val) else "")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _format_number(
    value, *, prefix: str = "", suffix: str = "", multiplier: float | None = None
) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if multiplier is not None:
        numeric *= multiplier
    return f"{prefix}{numeric:.3f}{suffix}"


def _format_percent(value) -> str:
    return _format_number(value, suffix="%", multiplier=100.0)


def _is_zero(value) -> bool:
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return False


def _parse_json_field(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {}


def _determine_scenario_key(
    scenario_field: str | None,
    context: dict[str, Any],
) -> tuple[str, str, str | None]:
    bundle = context.get("bundle")
    member = context.get("bundle_member")
    label = context.get("scenario_label") or member or scenario_field or "unknown"
    if bundle:
        key = f"{bundle}:{member or label}"
        display = key
    else:
        key = label
        display = label
    return key, display, bundle


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_convergence_steps(
    step_path: Path, thresholds: Sequence[float]
) -> tuple[dict[float, int | None], float | None]:
    if not step_path.exists():
        return {threshold: None for threshold in thresholds}, None
    first_reach: dict[float, int | None] = {threshold: None for threshold in thresholds}
    best_logged: float | None = None
    sorted_thresholds = sorted(thresholds)

    with step_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            best_value = _safe_float(record.get("best_objective"))
            if best_value is None:
                continue
            if best_logged is None or best_value > best_logged:
                best_logged = best_value
            step_value = record.get("step")
            if isinstance(step_value, int | float):
                for threshold in sorted_thresholds:
                    if best_value >= threshold and first_reach[threshold] is None:
                        first_reach[threshold] = int(step_value)
    return first_reach, best_logged


def _compute_convergence(
    sqlite_path: Path,
    telemetry_log: Path,
    *,
    hard_threshold: float,
    soft_threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"Telemetry SQLite store not found: {sqlite_path}")

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        run_rows = conn.execute(
            """
            SELECT run_id, solver, scenario, duration_seconds,
                   context_json, config_json, tuner_meta_json
            FROM runs
            """
        ).fetchall()
        metric_rows = conn.execute(
            """
            SELECT run_id, name, value, value_text
            FROM run_metrics
            WHERE name IN ('objective', 'initial_score')
            """
        ).fetchall()
    finally:
        conn.close()

    objective_map: dict[str, float] = {}
    initial_score_map: dict[str, float] = {}
    for row in metric_rows:
        run_id = row["run_id"]
        metric_name = row["name"]
        value = row["value"]
        if value is None and row["value_text"]:
            value = _safe_float(row["value_text"])
        if value is None:
            continue
        if metric_name == "objective":
            objective_map[run_id] = float(value)
        elif metric_name == "initial_score":
            initial_score_map[run_id] = float(value)

    mip_objectives: dict[str, float] = {}
    scenario_meta: dict[str, dict[str, Any]] = {}
    heuristics_records: list[dict[str, Any]] = []

    steps_dir = telemetry_log.parent / "steps"
    heuristic_solvers = {"sa", "ils", "tabu"}

    for row in run_rows:
        run_id = row["run_id"]
        solver = (row["solver"] or "").lower()
        scenario_field = row["scenario"]
        context = _parse_json_field(row["context_json"])
        config = _parse_json_field(row["config_json"])
        tuner_meta = _parse_json_field(row["tuner_meta_json"])
        scenario_key, scenario_display, bundle_name = _determine_scenario_key(
            scenario_field, context
        )
        scenario_meta.setdefault(
            scenario_key,
            {
                "scenario": scenario_display,
                "bundle": bundle_name,
            },
        )
        if solver == "mip":
            objective = objective_map.get(run_id)
            if objective is None:
                continue
            previous = mip_objectives.get(scenario_key)
            mip_objectives[scenario_key] = (
                max(previous, objective) if previous is not None else objective
            )
            continue

        if solver not in heuristic_solvers:
            continue

        heuristics_records.append(
            {
                "run_id": run_id,
                "solver": solver,
                "scenario_key": scenario_key,
                "scenario": scenario_display,
                "bundle": bundle_name,
                "context": context,
                "config": config,
                "tuner_meta": tuner_meta,
                "duration_seconds": _safe_float(row["duration_seconds"]),
            }
        )

    if not heuristics_records:
        runs_columns = [
            "scenario",
            "bundle",
            "algorithm",
            "tier",
            "run_id",
            "iterations_to_1pct",
            "iterations_to_5pct",
            "total_iterations",
            "best_objective",
            "mip_objective",
            "baseline_objective",
            "gap_absolute",
            "gap_pct",
            "gap_range",
            "duration_seconds",
        ]
        summary_columns = [
            "scenario",
            "bundle",
            "algorithm",
            "tier",
            "runs_total",
            "runs_reached_1pct",
            "success_rate",
            "mean_iterations_to_1pct",
            "median_iterations_to_1pct",
            "min_iterations_to_1pct",
            "max_iterations_to_1pct",
            "runs_reached_5pct",
            "success_rate_soft",
            "mean_iterations_to_5pct",
            "median_iterations_to_5pct",
            "min_iterations_to_5pct",
            "max_iterations_to_5pct",
            "mean_gap_absolute",
            "mean_gap_pct",
            "mean_gap_range",
        ]
        return pd.DataFrame(columns=runs_columns), pd.DataFrame(columns=summary_columns)

    runs_records: list[dict[str, Any]] = []
    threshold_targets = {
        "hard": float(hard_threshold),
        "soft": float(soft_threshold),
    }
    for record in heuristics_records:
        scenario_key = record["scenario_key"]
        mip_obj = mip_objectives.get(scenario_key)
        if mip_obj is None or mip_obj == 0:
            # Skip scenarios without a baseline optimum
            continue
        threshold_values = {
            name: float(mip_obj) * (1.0 - frac) for name, frac in threshold_targets.items()
        }
        run_id = record["run_id"]
        steps_path = steps_dir / f"{run_id}.jsonl"
        iterations_map, best_logged = _extract_convergence_steps(
            steps_path,
            [threshold_values["hard"], threshold_values["soft"]],
        )
        iterations_to_hard = iterations_map.get(threshold_values["hard"])
        iterations_to_soft = iterations_map.get(threshold_values["soft"])

        best_objective = objective_map.get(run_id)
        if best_objective is None:
            best_objective = best_logged
        elif best_logged is not None:
            best_objective = max(best_objective, best_logged)

        if best_objective is None:
            continue

        config = record["config"]
        tuner_meta = record["tuner_meta"]
        progress = tuner_meta.get("progress", {}) if isinstance(tuner_meta, dict) else {}
        total_iterations = None
        for key in ("iters", "iterations"):
            value = config.get(key)
            if isinstance(value, int | float):
                total_iterations = int(value)
                break
        if total_iterations is None and isinstance(progress, dict):
            value = progress.get("iterations")
            if isinstance(value, int | float):
                total_iterations = int(value)

        # Fallback when threshold reached only at final iteration
        if (
            iterations_to_hard is None
            and best_objective >= threshold_values["hard"]
            and total_iterations is not None
        ):
            iterations_to_hard = total_iterations
        if (
            iterations_to_soft is None
            and best_objective >= threshold_values["soft"]
            and total_iterations is not None
        ):
            iterations_to_soft = total_iterations

        baseline_objective = initial_score_map.get(run_id)

        gap_absolute: float | None = None
        gap_pct: float | None = None
        gap_range: float | None = None
        delta = float(mip_obj) - float(best_objective)
        gap_absolute = delta
        if mip_obj != 0:
            gap_pct_raw = delta / float(mip_obj)
            gap_pct = max(0.0, gap_pct_raw)
        if baseline_objective is not None:
            denom = float(mip_obj) - float(baseline_objective)
            if denom > 1e-9:
                ratio = delta / denom
                gap_range = max(0.0, min(1.0, ratio))

        tier = record["context"].get("tier")
        if tier is None and isinstance(tuner_meta, dict):
            budget = tuner_meta.get("budget", {})
            if isinstance(budget, dict):
                tier = budget.get("tier")

        runs_records.append(
            {
                "scenario": record["scenario"],
                "bundle": record["bundle"],
                "algorithm": record["solver"],
                "tier": tier or "",
                "run_id": run_id,
                "iterations_to_1pct": iterations_to_hard,
                "iterations_to_5pct": iterations_to_soft,
                "total_iterations": total_iterations,
                "best_objective": best_objective,
                "mip_objective": mip_obj,
                "baseline_objective": baseline_objective,
                "gap_absolute": gap_absolute,
                "gap_pct": gap_pct,
                "gap_range": gap_range,
                "duration_seconds": record["duration_seconds"],
            }
        )

    runs_df = pd.DataFrame(runs_records)
    if runs_df.empty:
        runs_columns = [
            "scenario",
            "bundle",
            "algorithm",
            "tier",
            "run_id",
            "iterations_to_1pct",
            "iterations_to_5pct",
            "total_iterations",
            "best_objective",
            "mip_objective",
            "baseline_objective",
            "gap_absolute",
            "gap_pct",
            "gap_range",
            "duration_seconds",
        ]
        summary_columns = [
            "scenario",
            "bundle",
            "algorithm",
            "tier",
            "runs_total",
            "runs_reached_1pct",
            "success_rate",
            "mean_iterations_to_1pct",
            "median_iterations_to_1pct",
            "min_iterations_to_1pct",
            "max_iterations_to_1pct",
            "runs_reached_5pct",
            "success_rate_soft",
            "mean_iterations_to_5pct",
            "median_iterations_to_5pct",
            "min_iterations_to_5pct",
            "max_iterations_to_5pct",
            "mean_gap_absolute",
            "mean_gap_pct",
            "mean_gap_range",
        ]
        return pd.DataFrame(columns=runs_columns), pd.DataFrame(columns=summary_columns)

    group_columns = ["scenario", "bundle", "algorithm", "tier"]
    summary_records: list[dict[str, Any]] = []
    grouped = runs_df.groupby(group_columns, dropna=False)
    for (scenario, bundle, algorithm, tier), group in grouped:
        total_runs = len(group)
        reached_hard_mask = group["iterations_to_1pct"].notna()
        reached_soft_mask = group["iterations_to_5pct"].notna()
        reached_hard = int(reached_hard_mask.sum())
        reached_soft = int(reached_soft_mask.sum())
        success_rate_hard = reached_hard / total_runs if total_runs else 0.0
        success_rate_soft = reached_soft / total_runs if total_runs else 0.0
        hard_iterations = group.loc[reached_hard_mask, "iterations_to_1pct"].astype(float)
        soft_iterations = group.loc[reached_soft_mask, "iterations_to_5pct"].astype(float)
        summary_records.append(
            {
                "scenario": scenario,
                "bundle": bundle,
                "algorithm": algorithm,
                "tier": tier,
                "runs_total": total_runs,
                "runs_reached_1pct": reached_hard,
                "success_rate": success_rate_hard,
                "mean_iterations_to_1pct": hard_iterations.mean()
                if not hard_iterations.empty
                else None,
                "median_iterations_to_1pct": hard_iterations.median()
                if not hard_iterations.empty
                else None,
                "min_iterations_to_1pct": hard_iterations.min()
                if not hard_iterations.empty
                else None,
                "max_iterations_to_1pct": hard_iterations.max()
                if not hard_iterations.empty
                else None,
                "runs_reached_5pct": reached_soft,
                "success_rate_soft": success_rate_soft,
                "mean_iterations_to_5pct": soft_iterations.mean()
                if not soft_iterations.empty
                else None,
                "median_iterations_to_5pct": soft_iterations.median()
                if not soft_iterations.empty
                else None,
                "min_iterations_to_5pct": soft_iterations.min()
                if not soft_iterations.empty
                else None,
                "max_iterations_to_5pct": soft_iterations.max()
                if not soft_iterations.empty
                else None,
                "mean_gap_absolute": group["gap_absolute"].mean(skipna=True)
                if "gap_absolute" in group
                else None,
                "mean_gap_pct": group["gap_pct"].mean(skipna=True) if "gap_pct" in group else None,
                "mean_gap_range": group["gap_range"].mean(skipna=True)
                if "gap_range" in group
                else None,
            }
        )

    summary_df = pd.DataFrame(summary_records).sort_values(
        ["scenario", "algorithm", "tier"], na_position="last"
    )
    runs_df.sort_values(["scenario", "algorithm", "tier", "run_id"], inplace=True)
    return runs_df, summary_df


def _render_simple_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "*(no data)*"
    headers = list(df.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in df.iterrows():
        cells = []
        for col in headers:
            value = row[col]
            if isinstance(value, float):
                cells.append(f"{value:.3f}")
            else:
                cells.append("" if value is None else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


DESIRED_METRICS = {
    "total_production": "best_total_production",
    "mobilisation_cost": "best_mobilisation_cost",
    "utilisation_ratio_mean_shift": "best_utilisation_ratio_shift",
    "utilisation_ratio_mean_day": "best_utilisation_ratio_day",
    "downtime_hours_total": "best_downtime_hours",
    "downtime_event_count": "best_downtime_events",
    "downtime_production_loss_est": "best_downtime_loss",
    "weather_severity_total": "best_weather_severity",
    "weather_hours_est": "best_weather_hours",
    "weather_production_loss_est": "best_weather_loss",
}
METRIC_LABELS = {
    "best_objective": "Best Objective",
    "best_total_production": "Total Production",
    "best_mobilisation_cost": "Mobilisation Cost",
    "best_utilisation_ratio_shift": "Utilisation (Shift)",
    "best_utilisation_ratio_day": "Utilisation (Day)",
    "best_downtime_hours": "Downtime Hours",
    "best_downtime_events": "Downtime Events",
    "best_downtime_loss": "Downtime Loss (Est.)",
    "best_weather_severity": "Weather Severity",
    "best_weather_hours": "Weather Hours (Est.)",
    "best_weather_loss": "Weather Loss (Est.)",
}


def _load_run_metrics(sqlite_path: Path, run_id: str | None) -> dict[str, float]:
    if not run_id or not sqlite_path.exists():
        return {}
    metrics: dict[str, float] = {}
    conn = sqlite3.connect(sqlite_path)
    try:
        rows = conn.execute(
            "SELECT name, value, value_text FROM run_metrics WHERE run_id = ?",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()
    for name, value, value_text in rows:
        if name not in DESIRED_METRICS:
            continue
        column = DESIRED_METRICS[name]
        if value is not None:
            metrics[column] = float(value)
        elif value_text:
            try:
                metrics[column] = float(value_text)
            except ValueError:
                continue
    return metrics


def _collect_history(directory: Path, *, pattern: str = "*.csv") -> pd.DataFrame:
    directory = directory.expanduser()
    if not directory.exists():
        raise FileNotFoundError(f"History directory not found: {directory}")

    records: list[pd.DataFrame] = []
    for path in sorted(directory.glob(pattern)):
        if not path.is_file():
            continue
        snapshot = path.stem
        df = pd.read_csv(path)
        required = {"algorithm", "scenario", "best_objective", "mean_objective", "runs"}
        if required - set(df.columns):
            continue
        df = df.copy()
        df["snapshot"] = snapshot
        sqlite_path = path.with_suffix(".sqlite")
        metric_rows = []
        for row in df.itertuples(index=False):
            metrics = _load_run_metrics(sqlite_path, getattr(row, "best_run_id", None))
            metric_rows.append(metrics)
        metrics_df = pd.DataFrame(metric_rows)
        merged = pd.concat([df, metrics_df], axis=1)
        keep_cols = [
            "algorithm",
            "scenario",
            "best_run_id",
            "best_objective",
            "mean_objective",
            "runs",
            "snapshot",
        ] + list(DESIRED_METRICS.values())
        records.append(merged[[col for col in keep_cols if col in merged.columns]])
    if not records:
        return pd.DataFrame(
            columns=[
                "algorithm",
                "scenario",
                "best_objective",
                "mean_objective",
                "runs",
                "snapshot",
            ]
        )
    combined = pd.concat(records, ignore_index=True)
    combined["algorithm"] = combined["algorithm"].str.lower().str.strip()
    combined["scenario"] = combined["scenario"].str.strip()
    return combined


def _render_history_markdown(df: pd.DataFrame) -> str:
    extra_columns = [col for col in DESIRED_METRICS.values() if col in df.columns]
    headers = ["Snapshot", "Algorithm", "Scenario", "Best", "Mean", "Runs"] + [
        METRIC_LABELS.get(col, col) for col in extra_columns
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in df.iterrows():
        cells = [
            str(row["snapshot"]),
            str(row["algorithm"]),
            str(row["scenario"]),
            _format_number(row["best_objective"]),
            _format_number(row["mean_objective"]),
            str(int(row["runs"])) if pd.notna(row["runs"]) else "",
        ]
        for col in extra_columns:
            cells.append(_format_number(row.get(col)))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _export_history_chart(df: pd.DataFrame, output_path: Path) -> None:
    try:
        import altair as alt
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise SystemExit("Altair is required for --out-history-chart support.") from exc
    value_columns = ["best_objective"] + [
        col for col in DESIRED_METRICS.values() if col in df.columns
    ]
    chart_df = df.melt(
        id_vars=["snapshot", "algorithm", "scenario"],
        value_vars=value_columns,
        var_name="metric",
        value_name="value",
    )
    chart_df["metric_label"] = chart_df["metric"].map(METRIC_LABELS).fillna(chart_df["metric"])
    chart = (
        alt.Chart(chart_df)
        .mark_line(point=True)
        .encode(
            x=alt.X("snapshot:N", title="Snapshot"),
            y=alt.Y("value:Q", title="Value"),
            color=alt.Color("algorithm:N", title="Algorithm"),
            column=alt.Column("metric_label:N", title="Metric", sort=list(METRIC_LABELS.values())),
            row=alt.Row("scenario:N", title="Scenario"),
        )
        .properties(width=220, height=180)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chart.save(output_path, embed_options={"actions": False})


def _compute_history_deltas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    metrics = ["best_objective"] + [col for col in DESIRED_METRICS.values() if col in df.columns]
    records: list[dict[str, object]] = []
    for (scenario, algorithm), group in df.sort_values("snapshot").groupby(
        ["scenario", "algorithm"], dropna=False
    ):
        if len(group) < 2:
            continue
        latest = group.iloc[-1]
        previous = group.iloc[-2]
        entry: dict[str, object] = {
            "scenario": scenario,
            "algorithm": algorithm,
            "snapshot_current": latest["snapshot"],
            "snapshot_previous": previous["snapshot"],
        }
        for metric in metrics:
            current_val = latest.get(metric)
            prev_val = previous.get(metric)
            entry[f"{metric}"] = current_val
            if (
                current_val is not None
                and prev_val is not None
                and not (pd.isna(current_val) or pd.isna(prev_val))
            ):
                entry[f"{metric}_delta"] = float(current_val) - float(prev_val)
                if not _is_zero(prev_val):
                    entry[f"{metric}_delta_pct"] = (float(current_val) - float(prev_val)) / float(
                        prev_val
                    )
                else:
                    entry[f"{metric}_delta_pct"] = None
            else:
                entry[f"{metric}_delta"] = None
                entry[f"{metric}_delta_pct"] = None
        records.append(entry)
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def _render_delta_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "*(Not enough history to compute deltas yet.)*"
    metric_pairs = []
    metrics = ["best_objective"] + [col for col in DESIRED_METRICS.values() if col in df.columns]
    for metric in metrics:
        label = METRIC_LABELS.get(metric, metric.replace("best_", "").replace("_", " ").title())
        entries = [(metric, label), (f"{metric}_delta", f"Δ {label}")]
        pct_column = f"{metric}_delta_pct"
        if pct_column in df.columns:
            entries.append((pct_column, f"Δ% {label}"))
        metric_pairs.append(entries)
    headers = ["Scenario", "Algorithm", "Current Snapshot", "Previous Snapshot"]
    for entries in metric_pairs:
        for _, header_label in entries:
            headers.append(header_label)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in df.iterrows():
        cells = [
            str(row["scenario"]),
            str(row["algorithm"]),
            str(row["snapshot_current"]),
            str(row["snapshot_previous"]),
        ]
        for entries in metric_pairs:
            for column, _ in entries:
                value = row.get(column)
                if column.endswith("_delta_pct"):
                    cells.append(_format_percent(value))
                elif column.endswith("_delta"):
                    cells.append(_format_number(value, prefix="+"))
                else:
                    cells.append(_format_number(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _summarize_best_by_scenario(df: pd.DataFrame, labels: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["scenario"])
    scenarios = sorted(set(df["scenario"].dropna()))
    rows: list[dict[str, object]] = []
    for scenario in scenarios:
        subset = df[df["scenario"] == scenario]
        if subset.empty:
            continue
        summary: dict[str, object] = {"scenario": scenario}
        baseline_value: float | None = None
        for idx, label in enumerate(labels):
            value_column = f"best_{label}"
            if value_column not in subset.columns:
                summary[f"best_algorithm_{label}"] = ""
                summary[f"best_value_{label}"] = None
                if idx != 0:
                    summary[f"best_delta_{label}"] = None
                continue
            values = pd.to_numeric(subset[value_column], errors="coerce")
            valid = subset.loc[values.notna()]
            if valid.empty:
                summary[f"best_algorithm_{label}"] = ""
                summary[f"best_value_{label}"] = None
                if idx != 0:
                    summary[f"best_delta_{label}"] = None
                continue
            best_idx = values.idxmax()
            best_entry = subset.loc[best_idx]
            best_value = float(values.loc[best_idx])
            summary[f"best_algorithm_{label}"] = str(best_entry["algorithm"])
            summary[f"best_value_{label}"] = best_value
            if idx == 0:
                baseline_value = best_value
            else:
                summary[f"best_delta_{label}"] = (
                    best_value - baseline_value if baseline_value is not None else None
                )
        rows.append(summary)
    return pd.DataFrame(rows)


def _render_summary_markdown(df: pd.DataFrame, labels: list[str]) -> str:
    if df.empty:
        return "*(No scenarios available to summarise.)*"
    headers = ["Scenario"]
    for idx, label in enumerate(labels):
        headers.extend([f"Best Algo ({label})", f"Best Obj ({label})"])
        if idx != 0:
            headers.append(f"Δ vs {labels[0]}")
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in df.iterrows():
        cells = [str(row["scenario"])]
        for idx, label in enumerate(labels):
            algo = str(row.get(f"best_algorithm_{label}", "") or "")
            value = _format_number(row.get(f"best_value_{label}"))
            cells.extend([algo, value])
            if idx != 0:
                delta = _format_number(row.get(f"best_delta_{label}"), prefix="+")
                cells.append(delta)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="append",
        required=True,
        help="Report path (or label=path). Directories default to tuner_report.csv.",
    )
    parser.add_argument(
        "--history-dir",
        type=Path,
        help="Directory containing multiple tuner_report CSV snapshots to build a history.",
    )
    parser.add_argument(
        "--history-pattern",
        default="*.csv",
        help="Filename glob used when scanning --history-dir (default: *.csv).",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        help="Optional CSV output path for the combined report.",
    )
    parser.add_argument(
        "--out-markdown",
        type=Path,
        help="Optional Markdown output path for the combined report.",
    )
    parser.add_argument(
        "--out-chart",
        type=Path,
        help="Optional HTML path for an Altair chart comparing best objectives.",
    )
    parser.add_argument(
        "--out-history-csv",
        type=Path,
        help="Optional CSV path for the historical aggregation when --history-dir is set.",
    )
    parser.add_argument(
        "--out-history-markdown",
        type=Path,
        help="Optional Markdown path for the historical aggregation when --history-dir is set.",
    )
    parser.add_argument(
        "--out-history-chart",
        type=Path,
        help="Optional HTML Altair chart showing history trends (requires --history-dir).",
    )
    parser.add_argument(
        "--out-history-delta-csv",
        type=Path,
        help="Optional CSV path summarising latest vs previous snapshot deltas (requires --history-dir).",
    )
    parser.add_argument(
        "--out-history-delta-markdown",
        type=Path,
        help="Optional Markdown path for the delta summary (requires --history-dir).",
    )
    parser.add_argument(
        "--out-summary-csv",
        type=Path,
        help="Optional CSV path summarising the best algorithm/objective per scenario for each report label.",
    )
    parser.add_argument(
        "--out-summary-markdown",
        type=Path,
        help="Optional Markdown table listing per-scenario best performance for each report label.",
    )
    parser.add_argument(
        "--telemetry-log",
        type=Path,
        help="Telemetry runs JSONL used to derive convergence metrics (requires matching .sqlite store).",
    )
    parser.add_argument(
        "--convergence-threshold",
        type=float,
        default=0.01,
        help="Optimality gap threshold (fraction). Default: 0.01 (1%% gap).",
    )
    parser.add_argument(
        "--convergence-soft-threshold",
        type=float,
        default=0.05,
        help="Secondary (softer) gap threshold (fraction). Default: 0.05 (5%% gap).",
    )
    parser.add_argument(
        "--out-convergence-csv",
        type=Path,
        help="Optional CSV path for per-run convergence metrics (requires --telemetry-log).",
    )
    parser.add_argument(
        "--out-convergence-summary-csv",
        type=Path,
        help="Optional CSV path for aggregated convergence metrics (requires --telemetry-log).",
    )
    parser.add_argument(
        "--out-convergence-summary-markdown",
        type=Path,
        help="Optional Markdown path for aggregated convergence metrics (requires --telemetry-log).",
    )
    args = parser.parse_args(argv)

    labels: list[str] = []
    frames: list[pd.DataFrame] = []
    for entry in args.report:
        label, path = _parse_report_arg(entry)
        labels.append(label)
        frames.append(_load_report(label, path))

    combined = _merge_reports(frames)
    baseline = labels[0]
    for label in labels[1:]:
        combined[f"best_delta_{label}"] = combined[f"best_{label}"] - combined[f"best_{baseline}"]

    if args.out_csv:
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(args.out_csv, index=False)

    markdown = _format_markdown(combined, labels)
    if args.out_markdown:
        args.out_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.out_markdown.write_text(markdown + "\n", encoding="utf-8")

    if args.out_chart:
        try:
            import altair as alt
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise SystemExit("Altair is required for --out-chart support.") from exc

        chart_records: list[dict[str, object]] = []
        for _, row in combined.iterrows():
            for label in labels:
                best_val = row.get(f"best_{label}")
                if pd.notna(best_val):
                    chart_records.append(
                        {
                            "algorithm": row["algorithm"],
                            "scenario": row["scenario"],
                            "label": label,
                            "best_objective": best_val,
                        }
                    )
        chart_df = pd.DataFrame(chart_records)
        if not chart_df.empty:
            chart = (
                alt.Chart(chart_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X("label:N", title="Report"),
                    y=alt.Y("best_objective:Q", title="Best Objective"),
                    color=alt.Color("algorithm:N", title="Algorithm"),
                    row=alt.Row("scenario:N", title="Scenario"),
                )
                .properties(width=250, height=180)
            )
            args.out_chart.parent.mkdir(parents=True, exist_ok=True)
            chart.save(args.out_chart, embed_options={"actions": False})

    if not args.out_csv and not args.out_markdown:
        print(markdown)

    if args.out_summary_csv or args.out_summary_markdown:
        summary_df = _summarize_best_by_scenario(combined, labels)
        if args.out_summary_csv:
            args.out_summary_csv.parent.mkdir(parents=True, exist_ok=True)
            summary_df.to_csv(args.out_summary_csv, index=False)
        if args.out_summary_markdown:
            args.out_summary_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.out_summary_markdown.write_text(
                _render_summary_markdown(summary_df, labels) + "\n", encoding="utf-8"
            )

    convergence_outputs_requested = any(
        [
            args.out_convergence_csv,
            args.out_convergence_summary_csv,
            args.out_convergence_summary_markdown,
        ]
    )
    if args.telemetry_log:
        telemetry_log = args.telemetry_log
        sqlite_path = telemetry_log.with_suffix(".sqlite")
        convergence_runs_df, convergence_summary_df = _compute_convergence(
            sqlite_path,
            telemetry_log,
            hard_threshold=max(0.0, float(args.convergence_threshold)),
            soft_threshold=max(0.0, float(args.convergence_soft_threshold)),
        )
        if args.out_convergence_csv:
            args.out_convergence_csv.parent.mkdir(parents=True, exist_ok=True)
            convergence_runs_df.to_csv(args.out_convergence_csv, index=False)
        if args.out_convergence_summary_csv:
            args.out_convergence_summary_csv.parent.mkdir(parents=True, exist_ok=True)
            convergence_summary_df.to_csv(args.out_convergence_summary_csv, index=False)
        if args.out_convergence_summary_markdown:
            args.out_convergence_summary_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.out_convergence_summary_markdown.write_text(
                _render_simple_markdown(convergence_summary_df) + "\n",
                encoding="utf-8",
            )
        if not convergence_outputs_requested and not args.out_csv and not args.out_markdown:
            # Print a brief convergence summary when running interactively
            print(_render_simple_markdown(convergence_summary_df))
    elif convergence_outputs_requested:
        raise SystemExit("--telemetry-log is required when requesting convergence outputs.")

    if args.history_dir:
        history_df = _collect_history(Path(args.history_dir), pattern=args.history_pattern)
        if history_df.empty:
            print("No history entries discovered in", args.history_dir)
        else:
            history_df.sort_values(["scenario", "algorithm", "snapshot"], inplace=True)
            if args.out_history_csv:
                args.out_history_csv.parent.mkdir(parents=True, exist_ok=True)
                history_df.to_csv(args.out_history_csv, index=False)
            if args.out_history_markdown:
                args.out_history_markdown.parent.mkdir(parents=True, exist_ok=True)
                args.out_history_markdown.write_text(
                    _render_history_markdown(history_df) + "\n", encoding="utf-8"
                )
            if args.out_history_chart:
                _export_history_chart(history_df, args.out_history_chart)
            if args.out_history_delta_csv or args.out_history_delta_markdown:
                delta_df = _compute_history_deltas(history_df)
                if args.out_history_delta_csv:
                    args.out_history_delta_csv.parent.mkdir(parents=True, exist_ok=True)
                    delta_df.to_csv(args.out_history_delta_csv, index=False)
                if args.out_history_delta_markdown:
                    args.out_history_delta_markdown.parent.mkdir(parents=True, exist_ok=True)
                    args.out_history_delta_markdown.write_text(
                        _render_delta_markdown(delta_df) + "\n", encoding="utf-8"
                    )
            if not any([args.out_history_csv, args.out_history_markdown, args.out_history_chart]):
                print(_render_history_markdown(history_df))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
