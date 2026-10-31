"""Exact level precomputation for the FHOPS serious game."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

from fhops.model.milp.data import build_operational_bundle
from fhops.model.milp.driver import solve_operational_milp
from fhops.scenario.contract import Problem
from fhops.scenario.io import load_scenario

from .levels import GameLevel
from .variants import GameChoices, build_game_scenario, fleet_penalty, variant_fingerprint

__all__ = [
    "GamePrecomputeError",
    "enumerate_choices",
    "precompute_level",
    "check_precompute",
    "load_precompute",
    "write_precompute",
]

SCHEMA_VERSION = "fhops.game.precompute.v1"
SolverFn = Callable[[Problem], dict[str, Any]]


class GamePrecomputeError(RuntimeError):
    """Raised when a level cannot be precomputed or a cache is incomplete."""


@dataclass(frozen=True, slots=True)
class VariantResult:
    """One precomputed level variant."""

    choices: GameChoices
    fingerprint: str
    outcome: str
    raw_objective: float | None
    fleet_penalty: float
    adjusted_objective: float | None
    production_m3: float | None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable record."""
        return {
            "choices": {
                "fleet_counts": dict(sorted(self.choices.fleet_counts.items())),
                "arrival_profile": self.choices.arrival_profile,
                "harvest_pattern": self.choices.harvest_pattern,
            },
            "variant_sha256": self.fingerprint,
            "outcome": self.outcome,
            "raw_objective": self.raw_objective,
            "fleet_penalty": self.fleet_penalty,
            "adjusted_objective": self.adjusted_objective,
            "production_m3": self.production_m3,
        }


def enumerate_choices(level: GameLevel) -> Iterator[GameChoices]:
    """Yield every finite control combination in deterministic order."""
    count_ranges = [range(option.owned, option.maximum + 1) for option in level.fleet]
    for counts in product(*count_ranges):
        fleet_counts = {
            option.role: int(count) for option, count in zip(level.fleet, counts, strict=True)
        }
        for arrival in level.arrival_profiles:
            for pattern in level.harvest_patterns:
                yield GameChoices(fleet_counts, arrival, pattern)


def precompute_level(
    level: GameLevel,
    *,
    solver: str = "highs",
    time_limit: int | None = 60,
    solve_fn: SolverFn | None = None,
) -> dict[str, Any]:
    """Solve every feasible variant and return best/worst bounds.

    Infeasible variants are recorded and excluded from the bounds. Any solver
    error or non-optimal feasible variant aborts the precompute, because the
    0–100 score is only valid over complete exact bounds.
    """
    base = load_scenario(level.scenario)
    results: list[VariantResult] = []
    infeasible: list[dict[str, object]] = []
    for choices in enumerate_choices(level):
        variant = build_game_scenario(base, level, choices)
        fingerprint = variant_fingerprint(variant)
        if solve_fn is None:
            pb = Problem.from_scenario(variant)
            result = solve_operational_milp(
                build_operational_bundle(pb),
                solver=solver,
                time_limit=time_limit,
            )
        else:
            result = solve_fn(Problem.from_scenario(variant))
        outcome = str(result.get("outcome", "error"))
        penalty = fleet_penalty(level, choices)
        raw = result.get("objective")
        if outcome == "infeasible":
            infeasible.append(
                {
                    "choices": {
                        "fleet_counts": dict(sorted(choices.fleet_counts.items())),
                        "arrival_profile": choices.arrival_profile,
                        "harvest_pattern": choices.harvest_pattern,
                    },
                    "variant_sha256": fingerprint,
                }
            )
            continue
        if outcome != "optimal" or raw is None:
            raise GamePrecomputeError(
                f"{level.level_id}: variant {fingerprint} returned {outcome!r}, expected optimal"
            )
        results.append(
            VariantResult(
                choices=choices,
                fingerprint=fingerprint,
                outcome=outcome,
                raw_objective=float(raw),
                fleet_penalty=penalty,
                adjusted_objective=float(raw) - penalty,
                production_m3=(
                    float(result["production"]) if result.get("production") is not None else None
                ),
            )
        )
    if not results:
        raise GamePrecomputeError(f"{level.level_id}: no feasible variants")
    best = max(results, key=lambda item: item.adjusted_objective or float("-inf"))
    worst = min(results, key=lambda item: item.adjusted_objective or float("inf"))
    if best.adjusted_objective is None or worst.adjusted_objective is None:
        raise GamePrecomputeError(f"{level.level_id}: missing objective bounds")
    return {
        "schema_version": SCHEMA_VERSION,
        "level_id": level.level_id,
        "level_order": level.order,
        "scenario": str(level.scenario),
        "menu": {
            "fleet": [
                {
                    "role": option.role,
                    "owned": option.owned,
                    "maximum": option.maximum,
                    "unit_cost": option.unit_cost,
                    "marginal_multipliers": list(option.marginal_multipliers),
                    "spot_surcharge": option.spot_surcharge,
                }
                for option in level.fleet
            ],
            "arrival_profiles": list(level.arrival_profiles),
            "harvest_patterns": list(level.harvest_patterns),
        },
        "objective_weights": level.objective_weights.model_dump(),
        "bounds": {
            "best_adjusted_objective": best.adjusted_objective,
            "worst_adjusted_objective": worst.adjusted_objective,
            "best_choices": best.choices.to_dict()
            if hasattr(best.choices, "to_dict")
            else {
                "fleet_counts": dict(sorted(best.choices.fleet_counts.items())),
                "arrival_profile": best.choices.arrival_profile,
                "harvest_pattern": best.choices.harvest_pattern,
            },
        },
        "completeness": {
            "complete": True,
            "variant_count": len(results) + len(infeasible),
            "feasible_count": len(results),
            "infeasible_count": len(infeasible),
        },
        "variants": [result.to_dict() for result in results],
        "infeasible": infeasible,
    }


def write_precompute(payload: dict[str, Any], path: str | Path) -> None:
    """Write a precompute payload as stable JSON."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_precompute(path: str | Path) -> dict[str, Any]:
    """Load a precompute payload and verify its schema."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise GamePrecomputeError(
            f"Unsupported precompute schema: {payload.get('schema_version')!r}"
        )
    return payload


def check_precompute(level: GameLevel, payload: dict[str, Any]) -> None:
    """Verify that a cached precompute covers the entire finite menu."""
    expected = {_choices_key(choices) for choices in enumerate_choices(level)}
    actual = {
        _choices_key(_choices_from_record(record["choices"]))
        for record in payload.get("variants", [])
    }
    actual.update(
        _choices_key(_choices_from_record(record["choices"]))
        for record in payload.get("infeasible", [])
    )
    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        raise GamePrecomputeError(
            f"{level.level_id}: precompute menu mismatch "
            f"({len(missing)} missing, {len(extra)} extra)"
        )
    if not payload.get("completeness", {}).get("complete"):
        raise GamePrecomputeError(f"{level.level_id}: precompute marked incomplete")
    if payload.get("level_id") != level.level_id:
        raise GamePrecomputeError(f"{level.level_id}: precompute level id mismatch")


def _choices_key(choices: GameChoices) -> tuple[tuple[tuple[str, int], ...], str, str]:
    return (
        tuple(sorted(choices.fleet_counts.items())),
        choices.arrival_profile,
        choices.harvest_pattern,
    )


def _choices_from_record(record: dict[str, Any]) -> GameChoices:
    return GameChoices(
        fleet_counts={str(key): int(value) for key, value in record["fleet_counts"].items()},
        arrival_profile=str(record["arrival_profile"]),
        harvest_pattern=str(record["harvest_pattern"]),
    )
