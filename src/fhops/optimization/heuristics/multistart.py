"""Multi-start orchestration helpers for heuristic solvers."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fhops.cli._utils import resolve_operator_presets
from fhops.optimization.heuristics.sa import solve_sa
from fhops.scenario.contract import Problem
from fhops.telemetry import append_jsonl


@dataclass(slots=True)
class MultiStartResult:
    """Aggregated result of a multi-start run.

    Attributes
    ----------
    best_result:
        The best run's result dictionary (matching :func:`solve_sa` semantics).
    runs_meta:
        Telemetry entries for every run (status, objective, preset, etc.).
    """

    best_result: dict[str, Any]
    runs_meta: list[dict[str, Any]]


def _run_single(
    pb: Problem,
    seed: int,
    preset: Sequence[str] | None,
    sa_kwargs: dict[str, Any],
    run_id: int,
) -> tuple[float, dict[str, Any] | None, dict[str, Any]]:
    """Execute a single SA run and return (objective, result, meta)."""

    try:
        operators = None
        operator_weights = None
        preset_label: str | None = None
        if preset:
            preset_label = "+".join(preset)
            operators, operator_weights = resolve_operator_presets(preset)
        kwargs = dict(sa_kwargs)
        kwargs.setdefault("seed", seed)
        if operators is not None:
            if operators:
                kwargs["operators"] = operators
            if operator_weights:
                kwargs["operator_weights"] = operator_weights
        result = solve_sa(pb, **kwargs)
        objective = float(result.get("objective", float("-inf")))
        meta = result.get("meta", {}) or {}
        meta = {
            **meta,
            "run_id": run_id,
            "seed": seed,
            "preset": preset_label or "default",
            "objective": objective,
            "status": "ok",
        }
        return objective, result, meta
    except Exception as exc:  # pragma: no cover - defensive logging path
        meta = {
            "run_id": run_id,
            "seed": seed,
            "preset": preset_label or "default",
            "status": "error",
            "error": repr(exc),
        }
        return float("-inf"), None, meta


def run_multi_start(
    pb: Problem,
    seeds: Sequence[int],
    presets: Sequence[Sequence[str] | None] | None = None,
    *,
    max_workers: int | None = None,
    sa_kwargs: dict[str, Any] | None = None,
    telemetry_log: str | Path | None = None,
    summary_log: bool = True,
) -> MultiStartResult:
    """Run several SA instances (possibly in parallel) and return the best outcome."""

    seed_list = list(seeds)
    if not seed_list:
        raise ValueError("seeds must contain at least one entry")

    sa_kwargs = dict(sa_kwargs or {})
    preset_list: list[Sequence[str] | None]
    if presets is None:
        preset_list = [None] * len(seed_list)
    else:
        preset_list = list(presets)
        if len(preset_list) != len(seed_list):
            raise ValueError("presets must match the length of seeds or be omitted")

    runs_meta: list[dict[str, Any]] = []
    results: list[tuple[float, dict[str, Any] | None]] = []
    seen_ids: set[int] = set()

    if len(seed_list) == 1 or (max_workers is not None and max_workers <= 1):
        # Sequential fallback for simplicity/testing.
        for idx, (seed, preset) in enumerate(zip(seed_list, preset_list)):
            objective, result, meta = _run_single(pb, seed, preset, sa_kwargs, idx)
            runs_meta.append(meta)
            results.append((objective, result))
            if telemetry_log and idx not in seen_ids:
                append_jsonl(telemetry_log, meta)
                seen_ids.add(idx)
    else:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_run_single, pb, seed, preset, sa_kwargs, idx): idx
                for idx, (seed, preset) in enumerate(zip(seed_list, preset_list))
            }
            for future in as_completed(futures):
                idx = futures[future]
                objective, result, meta = future.result()
                runs_meta.append(meta)
                results.append((objective, result))
                if telemetry_log and idx not in seen_ids:
                    append_jsonl(telemetry_log, meta)
                    seen_ids.add(idx)

    # Select the best result (highest objective) among successful runs.
    best_objective = float("-inf")
    best_result: dict[str, Any] | None = None
    best_meta: dict[str, Any] | None = None
    for (objective, result), meta in zip(results, runs_meta):
        if result is None:
            continue
        if objective > best_objective or best_result is None:
            best_objective = objective
            best_result = result
            best_meta = meta

    if best_result is None:
        raise RuntimeError("All multi-start runs failed; see runs_meta for details")

    if telemetry_log and summary_log:
        summary = {
            "type": "multi_start_summary",
            "best_objective": best_objective,
            "best_run_id": best_meta.get("run_id") if best_meta else None,
            "runs_executed": len(runs_meta),
        }
        append_jsonl(telemetry_log, summary)

    return MultiStartResult(best_result=best_result, runs_meta=runs_meta)


def build_exploration_plan(
    n_runs: int,
    *,
    base_seed: int = 42,
    presets: Sequence[str] | None = None,
) -> tuple[list[int], list[Sequence[str] | None]]:
    """Generate deterministic seeds and preset allocations for multi-start runs.

    Parameters
    ----------
    n_runs:
        Number of runs to schedule; must be positive.
    base_seed:
        Starting seed; seeds increment by ``1000`` to reduce overlap.
    presets:
        Optional iterable of preset names. When provided, values cycle across runs.
        ``None`` defaults to ``['default', 'explore', 'mobilisation', 'stabilise']``.
    """

    if n_runs <= 0:
        raise ValueError("n_runs must be positive")

    seed_step = 1000
    seeds = [base_seed + i * seed_step for i in range(n_runs)]

    if presets is None:
        preset_cycle: list[Sequence[str] | None] = [
            None,
            ["explore"],
            ["mobilisation"],
            ["stabilise"],
        ]
    else:
        preset_cycle = [[name] if name else None for name in presets]
        if not preset_cycle:
            preset_cycle = [None]

    assigned_presets: list[Sequence[str] | None] = []
    for i in range(n_runs):
        assigned_presets.append(preset_cycle[i % len(preset_cycle)])

    return seeds, assigned_presets


__all__ = ["MultiStartResult", "run_multi_start", "build_exploration_plan"]
