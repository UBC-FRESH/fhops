from __future__ import annotations

import csv
import json
import sqlite3
from collections import deque
from collections.abc import Iterable
from pathlib import Path
from statistics import fmean
from typing import TypedDict

import typer

from fhops.telemetry.machine_costs import summarize_machine_costs

telemetry_app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="Telemetry maintenance utilities."
)


def _read_run_lines(path: Path) -> Iterable[tuple[str, dict[str, object] | None]]:
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line:
                yield raw, None
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                yield raw, None
            else:
                yield raw, payload if isinstance(payload, dict) else None


@telemetry_app.command("prune")
def prune(
    telemetry_log: Path = typer.Argument(
        Path("telemetry/runs.jsonl"),
        exists=False,
        dir_okay=False,
        writable=True,
        help="Telemetry JSONL file to prune.",
    ),
    keep: int = typer.Option(
        5000,
        "--keep",
        "-k",
        min=1,
        help="Number of most-recent run records to retain.",
    ),
    steps_dir: Path | None = typer.Option(
        None,
        "--steps-dir",
        help="Directory holding step logs (defaults to <log>/../steps).",
        dir_okay=True,
        file_okay=False,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview the prune operation without modifying any files.",
    ),
) -> None:
    """Trim run telemetry JSONL and delete matching step logs."""
    if not telemetry_log.exists():
        typer.echo(f"No telemetry log found at {telemetry_log}. Nothing to prune.")
        raise typer.Exit(0)

    lines = list(_read_run_lines(telemetry_log))
    if len(lines) <= keep:
        typer.echo(
            f"Telemetry log contains {len(lines)} record(s); nothing to prune (keep={keep})."
        )
        raise typer.Exit(0)

    kept_entries = deque(lines, maxlen=keep)
    removed_entries = lines[:-keep]

    removed_run_ids = {
        payload.get("run_id")
        for _, payload in removed_entries
        if isinstance(payload, dict) and payload.get("run_id")
    }

    steps_root = steps_dir or telemetry_log.parent / "steps"
    if dry_run:
        typer.echo(
            f"[dry-run] Would keep {len(kept_entries)} record(s) and prune {len(removed_entries)}."
        )
        if removed_run_ids:
            typer.echo(
                f"[dry-run] Would remove {len(removed_run_ids)} step log(s) in {steps_root}."
            )
        raise typer.Exit(0)

    tmp_path = telemetry_log.with_suffix(telemetry_log.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for raw_line, _ in kept_entries:
            # raw_line already includes newline representation from original file
            if raw_line.endswith("\n"):
                handle.write(raw_line)
            else:
                handle.write(raw_line + "\n")
    tmp_path.replace(telemetry_log)

    steps_removed = 0
    if steps_root.exists():
        for run_id in removed_run_ids:
            if not isinstance(run_id, str):
                continue
            step_path = steps_root / f"{run_id}.jsonl"
            if step_path.exists():
                step_path.unlink()
                steps_removed += 1
    typer.echo(
        f"Pruned {len(removed_entries)} record(s); kept {len(kept_entries)}. "
        f"Removed {steps_removed} step log(s)."
    )


def _summarise_config(config: dict[str, object] | None) -> str:
    if not config:
        return ""
    parts: list[str] = []
    for key in ("batch_size", "max_workers", "iters", "perturbation_strength"):
        value = config.get(key) if isinstance(config, dict) else None
        if value not in (None, "", []):
            parts.append(f"{key}={value}")
    operators = config.get("operators") if isinstance(config, dict) else None
    if isinstance(operators, dict):
        preview = ", ".join(f"{name}:{weight}" for name, weight in sorted(operators.items())[:3])
        parts.append(f"operators=({preview})")
    return "; ".join(parts)


class _AggregateRecord(TypedDict):
    algorithm: str
    scenario: str
    objectives: list[float]
    best_objective: float
    best_run_id: str
    best_started_at: str
    best_config: dict[str, object]
    best_machine_costs_summary: str
    best_repair_usage_alert: str


def _collect_tuner_report(sqlite_path: Path) -> list[dict[str, object]]:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"Telemetry SQLite store not found: {sqlite_path}")

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    summary_map: dict[tuple[str, str], dict[str, object]] = {}
    try:
        summary_rows = conn.execute(
            """
            SELECT algorithm, scenario_best_json, configurations, created_at, summary_id, schema_version
            FROM tuner_summaries
            ORDER BY created_at
            """
        ).fetchall()
        for row in summary_rows:
            algorithm = row["algorithm"] or "unknown"
            scenario_map = json.loads(row["scenario_best_json"] or "{}")
            for scenario, value in scenario_map.items():
                key = (algorithm, scenario)
                summary_map[key] = {
                    "summary_id": row["summary_id"],
                    "schema_version": row["schema_version"],
                    "summary_best": value,
                    "summary_configurations": row["configurations"],
                    "summary_updated_at": row["created_at"],
                }

        run_rows = conn.execute(
            """
            SELECT
                runs.run_id,
                runs.solver,
                runs.scenario,
                runs.context_json,
                runs.config_json,
                runs.started_at,
                metrics.value AS objective,
                alert.value_text AS repair_usage_alert
            FROM runs
            JOIN run_metrics AS metrics
                ON metrics.run_id = runs.run_id AND metrics.name = 'objective'
            LEFT JOIN run_kpis AS alert
                ON alert.run_id = runs.run_id AND alert.name = 'repair_usage_alert'
            """
        ).fetchall()
    finally:
        conn.close()

    aggregates: dict[tuple[str, str], _AggregateRecord] = {}
    for row in run_rows:
        context = json.loads(row["context_json"] or "{}")
        source = context.get("source")
        algorithm = context.get("algorithm")
        if isinstance(source, str):
            if source == "cli.tune-random":
                algorithm = "random"
            elif source == "cli.tune-grid":
                algorithm = "grid"
            elif source == "cli.tune-bayes":
                algorithm = "bayes"
        if algorithm is None:
            continue
        algorithm = str(algorithm)
        scenario = row["scenario"] or "unknown"
        key = (algorithm, scenario)
        if key not in aggregates:
            aggregates[key] = _AggregateRecord(
                algorithm=algorithm,
                scenario=scenario,
                objectives=[],
                best_objective=float("-inf"),
                best_run_id="",
                best_started_at="",
                best_config={},
                best_machine_costs_summary="",
                best_repair_usage_alert="",
            )
        record = aggregates[key]
        objective = row["objective"]
        if objective is None:
            continue
        objective_value = float(objective)
        record["objectives"].append(objective_value)
        if objective_value > record["best_objective"]:
            record["best_objective"] = objective_value
            record["best_run_id"] = row["run_id"]
            record["best_started_at"] = row["started_at"] or ""
            config = json.loads(row["config_json"] or "{}")
            record["best_config"] = config if isinstance(config, dict) else {}
            machine_costs_summary = summarize_machine_costs(context.get("machine_costs"))
            record["best_machine_costs_summary"] = machine_costs_summary
            alert_value = row["repair_usage_alert"]
            record["best_repair_usage_alert"] = alert_value or ""

    report_rows: list[dict[str, object]] = []
    for key, data in sorted(aggregates.items()):
        algorithm, scenario = key
        objectives = data["objectives"]
        if not objectives:
            continue
        stats_entry = {
            "algorithm": algorithm,
            "scenario": scenario,
            "runs": len(objectives),
            "best_objective": data["best_objective"],
            "mean_objective": fmean(objectives),
            "best_run_id": data["best_run_id"],
            "best_started_at": data["best_started_at"],
            "best_config": _summarise_config(data["best_config"]),
            "machine_costs_summary": data["best_machine_costs_summary"],
            "repair_usage_alert": data["best_repair_usage_alert"],
        }
        stats_entry.update(summary_map.get(key, {}))
        report_rows.append(stats_entry)
    return report_rows


def _render_markdown(rows: list[dict[str, object]]) -> str:
    headers = [
        "Algorithm",
        "Scenario",
        "Best Objective",
        "Mean Objective",
        "Runs",
        "Summary Best",
        "Configurations",
        "Machine Costs",
        "Repair Usage Alert",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        summary_best_raw = row.get("summary_best")
        summary_best_str = (
            f"{float(summary_best_raw):.3f}" if isinstance(summary_best_raw, int | float) else ""
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["algorithm"]),
                    str(row["scenario"]),
                    f"{row['best_objective']:.3f}",
                    f"{row['mean_objective']:.3f}",
                    str(row["runs"]),
                    summary_best_str,
                    str(row.get("summary_configurations", "")),
                    row.get("machine_costs_summary", ""),
                    row.get("repair_usage_alert", ""),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


@telemetry_app.command("report")
def report(
    sqlite_path: Path = typer.Argument(
        Path("telemetry/runs.sqlite"),
        exists=False,
        dir_okay=False,
        readable=False,
        help="Path to the telemetry SQLite store.",
    ),
    out_csv: Path | None = typer.Option(
        None,
        "--out-csv",
        help="Optional CSV path for writing the aggregated report.",
    ),
    out_markdown: Path | None = typer.Option(
        None,
        "--out-markdown",
        help="Optional Markdown path for writing the aggregated summary table.",
    ),
) -> None:
    """Generate tuning comparison reports from the telemetry store."""

    sqlite_path = sqlite_path.resolve()
    try:
        rows = _collect_tuner_report(sqlite_path)
    except FileNotFoundError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc

    if not rows:
        typer.echo("No tuner telemetry records found.")
        raise typer.Exit(0)

    if out_csv:
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        headers = [
            "algorithm",
            "scenario",
            "runs",
            "best_objective",
            "mean_objective",
            "best_run_id",
            "best_started_at",
            "best_config",
            "summary_best",
            "summary_configurations",
            "summary_updated_at",
            "machine_costs_summary",
            "repair_usage_alert",
        ]
        with out_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                summary_best_raw = row.get("summary_best")
                writer.writerow(
                    {
                        "algorithm": row["algorithm"],
                        "scenario": row["scenario"],
                        "runs": row["runs"],
                        "best_objective": f"{row['best_objective']:.6f}",
                        "mean_objective": f"{row['mean_objective']:.6f}",
                        "best_run_id": row["best_run_id"],
                        "best_started_at": row["best_started_at"],
                        "best_config": row["best_config"],
                        "summary_best": (
                            f"{float(summary_best_raw):.6f}"
                            if isinstance(summary_best_raw, int | float)
                            else ""
                        ),
                        "summary_configurations": row.get("summary_configurations", ""),
                        "summary_updated_at": row.get("summary_updated_at", ""),
                        "machine_costs_summary": row.get("machine_costs_summary", ""),
                        "repair_usage_alert": row.get("repair_usage_alert", ""),
                    }
                )

    markdown = _render_markdown(rows)
    if out_markdown:
        out_markdown.parent.mkdir(parents=True, exist_ok=True)
        out_markdown.write_text(markdown + "\n", encoding="utf-8")

    if not out_csv and not out_markdown:
        typer.echo(markdown)

    alert_rows = [row for row in rows if row.get("repair_usage_alert")]
    if alert_rows:
        alert_scenarios = ", ".join(
            sorted({f"{row['scenario']} ({row['algorithm']})" for row in alert_rows})
        )
        typer.echo(
            f"WARNING: repair usage alerts detected for {alert_scenarios}. Review the `repair_usage_alert` column for details."
        )
