#!/usr/bin/env python3
"""Audit the committed SoftwareX benchmark, table, playback, scaling, and tuning assets.

The manuscript quotes numbers from several generated files that are written by different scripts
(``fhops bench suite`` summaries, assignment CSVs, ``build_tables.py`` tables, playback exports,
the synthetic scaling sweep, and the tuning harness). This script checks that they agree with each
other without re-running any solver:

* every benchmark ``summary.csv`` row is re-derived from its assignment CSV: ``compute_kpis``
  recomputes production, mobilisation, completed blocks and day-level utilisation, and the
  assignment count is the CSV row count. The schedule is also scored with a fresh heuristic
  evaluation (``evaluate_schedule`` with the objective-weight overrides the SA/ILS/Tabu drivers
  apply); this is reported as ``full_eval_objective`` / ``objective_gap`` but is **not** a pass/fail
  check: the solvers report the score of their internal best schedule, whose cached per-machine
  mobilisation can omit machines (FHOPS 1.0.1 heuristics), so the reported objective can exceed
  the fresh evaluation of the exported schedule. Whether an objective is reproducible is checked
  by re-running the benchmark (see ``notes/v101_maintenance_plan.md`` §8.16);
* the manuscript tables (``data/tables/*.csv``) equal a fresh ``build_tables.py`` rendering of the
  committed summaries (and, optionally, a manuscript ``sections/includes`` copy of the ``.tex``);
* each deterministic playback export is re-played from the benchmark assignment CSV it claims to
  come from (day-level production/hours/mobilisation must match) and its ``metrics.json`` agrees
  with the benchmark KPIs (delivered volume, mobilisation, utilisation);
* ``scaling_summary.csv`` agrees with the per-tier scaling summaries and their assignment CSVs;
* the tuning comparison/report tables agree with the run telemetry (``runs.jsonl``).

Exit status is 1 when any check fails. Use ``--json-out`` to keep the full matrix.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from fhops.evaluation import compute_kpis, day_dataframe, run_playback
from fhops.evaluation.playback.adapters import normalise_shift_ids
from fhops.optimization.heuristics.common import (
    evaluate_schedule,
    resolve_objective_weight_overrides,
)
from fhops.optimization.heuristics.ils import _assignments_to_schedule
from fhops.optimization.operational_problem import (
    build_operational_problem,
    override_objective_weights,
)
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario

BENCH_SCENARIOS = ("tiny7", "small21", "med42", "synthetic_small")
SCALING_TIERS = ("small", "medium", "large")
PLAYBACK = {
    "tiny7": ("ils", "sa"),
    "med42": ("ils", "sa"),
    "synthetic_small": ("ils", "sa"),
}
TOL = 1e-6

TUNER_SOURCES = {
    "cli.tune-random": "random",
    "cli.tune-grid": "grid",
    "cli.tune-bayes": "bayes",
    "benchmark.ils": "ils",
    "benchmark.tabu": "tabu",
}
COMPARISON_KEYS = {
    "baseline:tiny7": "FHOPS Tiny7",
    "baseline:small21": "FHOPS Small21",
    "baseline:med42": "FHOPS Medium42",
    "synthetic-small": "synthetic-small",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="FHOPS repository root.",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=None,
        help="Asset directory to audit (default: <repo-root>/docs/softwarex/assets).",
    )
    parser.add_argument(
        "--manuscript-includes",
        type=Path,
        default=None,
        help="Optional manuscript sections/includes directory; its solver_performance.tex and "
        "tuning_leaderboard.tex are compared with the FHOPS tables.",
    )
    parser.add_argument("--json-out", type=Path, default=None, help="Write the full matrix here.")
    return parser.parse_args()


def _close(a: Any, b: Any, tol: float = TOL) -> bool:
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    if math.isnan(fa) and math.isnan(fb):
        return True
    return abs(fa - fb) <= tol


def resolve_scenario(repo_root: Path, raw: str) -> Path:
    """Map a recorded (possibly absolute, other-checkout) scenario path into ``repo_root``."""
    for anchor in ("examples/", "docs/softwarex/"):
        idx = raw.find(anchor)
        if idx >= 0:
            return repo_root / raw[idx:]
    return repo_root / raw


def assignment_file(row: pd.Series) -> str:
    solver = str(row["solver"])
    if solver == "sa":
        label = row.get("preset_label")
        label = "default" if pd.isna(label) else str(label)
        if label in {"default", "custom"}:
            return "sa_assignments.csv"
        return f"sa_assignments_{label.replace('+', '_')}.csv"
    return f"{solver}_assignments.csv"


class Evaluator:
    """Cache problems/contexts per scenario and score assignment tables."""

    def __init__(self) -> None:
        self._cache: dict[Path, tuple[Problem, Any]] = {}

    def problem(self, scenario: Path) -> tuple[Problem, Any]:
        if scenario not in self._cache:
            pb = Problem.from_scenario(load_scenario(str(scenario)))
            ctx = build_operational_problem(pb)
            overrides = resolve_objective_weight_overrides(pb, None)
            if overrides:
                ctx = override_objective_weights(ctx, overrides)
            self._cache[scenario] = (pb, ctx)
        return self._cache[scenario]

    def score(self, scenario: Path, assignments: pd.DataFrame) -> dict[str, Any]:
        pb, ctx = self.problem(scenario)
        sched = _assignments_to_schedule(pb, assignments)
        objective = float(evaluate_schedule(pb, sched, ctx))
        kpis = compute_kpis(pb, assignments)
        return {
            "objective": objective,
            "assignments": int(len(assignments)),
            "total_production": float(kpis.get("total_production", float("nan"))),
            "mobilisation_cost": float(kpis.get("mobilisation_cost", 0.0)),
            "completed_blocks": float(kpis.get("completed_blocks", float("nan"))),
            "utilisation_ratio_mean_day": float(
                kpis.get("utilisation_ratio_mean_day", float("nan"))
            ),
        }


def audit_summary_rows(
    evaluator: Evaluator,
    repo_root: Path,
    summary_path: Path,
    group: str,
) -> list[dict[str, Any]]:
    df = pd.read_csv(summary_path)
    out: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        rel = assignment_file(row)
        csv_path = summary_path.parent / str(row["scenario"]) / rel
        label = row.get("preset_label")
        record: dict[str, Any] = {
            "group": group,
            "solver": row["solver"],
            "preset": "" if pd.isna(label) else str(label),
            "assignments_csv": str(csv_path.relative_to(summary_path.parent)),
            "summary_objective": float(row["objective"]),
            "summary_runtime_s": float(row["runtime_s"]),
        }
        if not csv_path.exists():
            record.update({"status": "MISSING", "mismatches": ["assignment CSV missing"]})
            out.append(record)
            continue
        scenario = resolve_scenario(repo_root, str(row["scenario_path"]))
        assign = pd.read_csv(csv_path)
        scored = evaluator.score(scenario, assign)
        checks = {
            "assignments": (row["assignments"], scored["assignments"]),
            "total_production": (row.get("kpi_total_production"), scored["total_production"]),
            "mobilisation_cost": (
                row.get("kpi_mobilisation_cost", 0.0)
                if not pd.isna(row.get("kpi_mobilisation_cost", 0.0))
                else 0.0,
                scored["mobilisation_cost"],
            ),
            "completed_blocks": (row.get("kpi_completed_blocks"), scored["completed_blocks"]),
            "utilisation_ratio_mean_day": (
                row.get("kpi_utilisation_ratio_mean_day"),
                scored["utilisation_ratio_mean_day"],
            ),
        }
        mismatches = [
            f"{key}: summary={a!r} csv={b!r}" for key, (a, b) in checks.items() if not _close(a, b)
        ]
        record.update(
            {
                "full_eval_objective": scored["objective"],
                "objective_gap": float(row["objective"]) - scored["objective"],
                "csv_assignments": scored["assignments"],
                "csv_total_production": scored["total_production"],
                "csv_mobilisation_cost": scored["mobilisation_cost"],
                "status": "OK" if not mismatches else "STALE",
                "mismatches": mismatches,
            }
        )
        out.append(record)
    return out


def audit_tables(repo_root: Path, assets: Path, includes: Path | None) -> list[dict[str, Any]]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_tables  # noqa: PLC0415

    out: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        default_sa = build_tables.build_solver_performance_table(
            assets / "data/benchmarks", tmp_dir
        )
        build_tables.build_tuning_leaderboard_table(
            assets / "data/tuning/tuner_comparison.csv",
            assets / "data/tuning/tuner_report.csv",
            default_sa,
            tmp_dir,
        )
        for name in (
            "solver_performance.csv",
            "solver_performance.tex",
            "tuning_leaderboard.csv",
            "tuning_leaderboard.tex",
        ):
            fresh = (tmp_dir / name).read_text(encoding="utf-8")
            committed_path = assets / "data/tables" / name
            committed = committed_path.read_text(encoding="utf-8")
            diff = _line_diff(committed, fresh)
            out.append(
                {
                    "table": f"data/tables/{name}",
                    "reference": "build_tables.py on committed summaries",
                    "status": "OK" if not diff else "STALE",
                    "mismatches": diff,
                }
            )
            if includes is not None and name.endswith(".tex"):
                ms_path = includes / name
                if ms_path.exists():
                    diff_ms = _line_diff(ms_path.read_text(encoding="utf-8"), fresh)
                    out.append(
                        {
                            "table": f"manuscript includes/{name}",
                            "reference": "build_tables.py on committed summaries",
                            "status": "OK" if not diff_ms else "DIFFERS",
                            "mismatches": diff_ms,
                        }
                    )
    return out


def _line_diff(old: str, new: str) -> list[str]:
    old_lines, new_lines = old.splitlines(), new.splitlines()
    diffs: list[str] = []
    for idx in range(max(len(old_lines), len(new_lines))):
        a = old_lines[idx] if idx < len(old_lines) else "<missing>"
        b = new_lines[idx] if idx < len(new_lines) else "<missing>"
        if a != b:
            diffs.append(f"committed: {a} | regenerated: {b}")
    return diffs


def audit_playback(evaluator: Evaluator, repo_root: Path, assets: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for slug, solvers in PLAYBACK.items():
        summary = pd.read_csv(assets / "data/benchmarks" / slug / "summary.csv")
        for solver in solvers:
            subset = summary[summary["solver"] == solver]
            if solver == "sa":
                subset = subset[subset["preset_label"].fillna("default") == "default"]
            row = subset.iloc[0]
            scenario = resolve_scenario(repo_root, str(row["scenario_path"]))
            assign_path = assets / "data/benchmarks" / slug / "user-1" / assignment_file(row)
            pb, _ = evaluator.problem(scenario)
            assign = normalise_shift_ids(pb, pd.read_csv(assign_path))
            fresh_day = day_dataframe(run_playback(pb, assign))
            det_dir = assets / "data/playback" / slug / solver / "deterministic"
            committed_day = pd.read_csv(det_dir / "day.csv")
            mismatches: list[str] = []
            for col in ("production_units", "total_hours", "mobilisation_cost"):
                a = committed_day[col].to_numpy(dtype=float)
                b = fresh_day[col].to_numpy(dtype=float)
                if a.shape != b.shape or (abs(a - b) > TOL).any():
                    mismatches.append(
                        f"day.csv {col}: committed sum={a.sum():.6f} replay sum={b.sum():.6f}"
                    )
            metrics = json.loads((det_dir / "metrics.json").read_text(encoding="utf-8"))
            mob = row.get("kpi_mobilisation_cost", 0.0)
            mob = 0.0 if pd.isna(mob) else mob
            metric_checks = {
                "total_production (delivered)": (
                    metrics.get("total_production"),
                    row["kpi_total_production"],
                ),
                "mobilisation_cost": (metrics.get("mobilisation_cost"), mob),
                "average_utilisation": (
                    metrics.get("average_utilisation"),
                    row["kpi_utilisation_ratio_mean_day"],
                ),
            }
            for key, (a, b) in metric_checks.items():
                if not _close(a, b):
                    mismatches.append(
                        f"metrics.json {key}: playback={float(a)!r} benchmark={float(b)!r}"
                    )
            out.append(
                {
                    "playback": f"{slug}/{solver}/deterministic",
                    "assignments_csv": str(assign_path.relative_to(assets)),
                    "status": "OK" if not mismatches else "STALE",
                    "mismatches": mismatches,
                }
            )
    return out


def audit_scaling(evaluator: Evaluator, repo_root: Path, assets: Path) -> list[dict[str, Any]]:
    scaling = assets / "data/scaling"
    table = pd.read_csv(scaling / "scaling_summary.csv").set_index("tier")
    out: list[dict[str, Any]] = []
    for tier in SCALING_TIERS:
        summary_path = scaling / "benchmarks" / tier / "summary.csv"
        rows = audit_summary_rows(evaluator, repo_root, summary_path, f"scaling/{tier}")
        bench = pd.read_csv(summary_path).iloc[0]
        mismatches = list(rows[0]["mismatches"])
        for key in ("objective", "runtime_s", "assignments"):
            if not _close(table.loc[tier, key], bench[key]):
                mismatches.append(
                    f"scaling_summary.csv {key}={table.loc[tier, key]!r} vs summary.csv {bench[key]!r}"
                )
        rows[0]["mismatches"] = mismatches
        rows[0]["status"] = "OK" if not mismatches else "STALE"
        out.extend(rows)
    return out


def audit_tuning(assets: Path) -> list[dict[str, Any]]:
    tuning = assets / "data/tuning"
    runs: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for line in (tuning / "telemetry/runs.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("record_type") != "run":
            continue
        algo = TUNER_SOURCES.get(record.get("context", {}).get("source", ""))
        if algo is None:
            continue
        runs[(record["scenario"], algo)].append(
            (float(record["metrics"]["objective"]), float(record.get("duration_seconds") or 0.0))
        )
    comparison = pd.read_csv(tuning / "tuner_comparison.csv")
    report = pd.read_csv(tuning / "tuner_report.csv")
    out: list[dict[str, Any]] = []
    for _, row in comparison.iterrows():
        scenario = COMPARISON_KEYS[row["scenario"]]
        values = runs.get((scenario, row["algorithm"]), [])
        mismatches: list[str] = []
        if not values:
            mismatches.append("no telemetry runs")
        else:
            objs = [v for v, _ in values]
            times = [t for _, t in values]
            checks = {
                "best_objective": (row["best_objective"], max(objs)),
                "mean_objective": (row["mean_objective"], sum(objs) / len(objs)),
                "mean_runtime": (row["mean_runtime"], sum(times) / len(times)),
            }
            for key, (a, b) in checks.items():
                if not _close(a, b, 1e-4):
                    mismatches.append(f"{key}: comparison={a!r} telemetry={b!r}")
        rep = report[(report["scenario"] == scenario) & (report["algorithm"] == row["algorithm"])]
        if not rep.empty and not _close(rep.iloc[0]["best_objective"], row["best_objective"], 1e-4):
            mismatches.append(
                f"tuner_report best_objective={rep.iloc[0]['best_objective']!r} "
                f"vs comparison {row['best_objective']!r}"
            )
        out.append(
            {
                "tuning": f"{row['scenario']}/{row['algorithm']}",
                "runs": len(values),
                "status": "OK" if not mismatches else "STALE",
                "mismatches": mismatches,
            }
        )
    return out


def _print_section(title: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
    print(f"\n## {title}\n")
    print("| " + " | ".join(columns) + " |")
    print("|" + "---|" * len(columns))
    for row in rows:
        cells = []
        for col in columns:
            value = row.get(col, "")
            if col == "mismatches":
                value = "; ".join(value) if value else ""
            elif isinstance(value, float):
                value = f"{value:.6f}"
            cells.append(str(value))
        print("| " + " | ".join(cells) + " |")


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    assets = (args.assets_dir or repo_root / "docs/softwarex/assets").resolve()
    evaluator = Evaluator()

    bench_rows: list[dict[str, Any]] = []
    for slug in BENCH_SCENARIOS:
        bench_rows.extend(
            audit_summary_rows(
                evaluator, repo_root, assets / "data/benchmarks" / slug / "summary.csv", slug
            )
        )
    result = {
        "benchmarks": bench_rows,
        "tables": audit_tables(repo_root, assets, args.manuscript_includes),
        "playback": audit_playback(evaluator, repo_root, assets),
        "scaling": audit_scaling(evaluator, repo_root, assets),
        "tuning": audit_tuning(assets),
    }

    _print_section(
        "Benchmark summary rows vs assignment CSVs",
        bench_rows,
        [
            "group",
            "solver",
            "preset",
            "summary_objective",
            "full_eval_objective",
            "objective_gap",
            "status",
            "mismatches",
        ],
    )
    _print_section(
        "Manuscript tables vs build_tables.py", result["tables"], ["table", "status", "mismatches"]
    )
    _print_section(
        "Deterministic playback vs benchmark assignments",
        result["playback"],
        ["playback", "assignments_csv", "status", "mismatches"],
    )
    _print_section(
        "Scaling sweep",
        result["scaling"],
        [
            "group",
            "summary_objective",
            "full_eval_objective",
            "summary_runtime_s",
            "status",
            "mismatches",
        ],
    )
    _print_section(
        "Tuning tables vs telemetry", result["tuning"], ["tuning", "runs", "status", "mismatches"]
    )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    failed = [
        row for section in result.values() for row in section if row.get("status") not in {"OK"}
    ]
    print(f"\n{len(failed)} failing check(s).")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
