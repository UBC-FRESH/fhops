"""Finite-space precompute for stand-scale serious-game levels."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import yaml

from .operation import evaluate_kc_selection_cut
from .scoring import ScoreBounds, normalize_score

__all__ = [
    "GameStandPrecomputeError",
    "StandChoices",
    "precompute_stand_level",
    "check_stand_precompute",
    "load_stand_precompute",
    "write_stand_precompute",
]

SCHEMA_VERSION = "fhops.game.stand_precompute.v1"
EvaluateFn = Callable[..., Any]


class GameStandPrecomputeError(RuntimeError):
    """Raised when a stand-level precompute is incomplete or invalid."""


@dataclass(frozen=True, slots=True)
class StandChoices:
    """One finite control combination for a stand-scale level."""

    care_level: float
    skidder_count: int
    log_length_m: float
    sawlog_min_dbh_cm: float
    road_extension_m: float

    def key(self) -> tuple[float, int, float, float, float]:
        """Return the stable comparison key."""
        return (
            self.care_level,
            self.skidder_count,
            self.log_length_m,
            self.sawlog_min_dbh_cm,
            self.road_extension_m,
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable record."""
        return {
            "care_level": self.care_level,
            "skidder_count": self.skidder_count,
            "log_length_m": self.log_length_m,
            "sawlog_min_dbh_cm": self.sawlog_min_dbh_cm,
            "road_extension_m": self.road_extension_m,
        }


def _load_level(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise GameStandPrecomputeError("Stand level manifest must be a mapping.")
    if payload.get("schema_version") != "fhops.game.level.v1":
        raise GameStandPrecomputeError("Unsupported stand level schema.")
    return payload


def enumerate_stand_choices(level: dict[str, Any]) -> Iterator[StandChoices]:
    """Yield every finite control combination for a level."""
    bucking = level.get("bucking") or {}
    landing = level.get("landing_options") or {"main": 0.0}
    for care, skidders, log_length, sawlog, extension in product(
        level["care_levels"],
        level["skidder_counts"],
        bucking["log_length_m"],
        bucking["sawlog_min_dbh_cm"],
        landing.values(),
    ):
        yield StandChoices(
            care_level=float(care),
            skidder_count=int(skidders),
            log_length_m=float(log_length),
            sawlog_min_dbh_cm=float(sawlog),
            road_extension_m=float(extension),
        )


def precompute_stand_level(
    level_path: str | Path,
    *,
    evaluate_fn: EvaluateFn = evaluate_kc_selection_cut,
) -> dict[str, Any]:
    """Evaluate every finite control combination and return exact bounds."""
    level_file = Path(level_path).expanduser().resolve()
    level = _load_level(level_file)
    level_dir = level_file.parent
    scenario = (level_dir / level["scenario"]).resolve()
    prices = (level_dir / level["prices"]).resolve()
    machine_ids = level["machine_ids"]
    skidders = tuple(machine_ids["skidders"])
    records: list[dict[str, Any]] = []
    for choices in enumerate_stand_choices(level):
        if choices.skidder_count > len(skidders):
            raise GameStandPrecomputeError("skidder_count exceeds available machines.")
        result = evaluate_fn(
            scenario,
            price_path=prices,
            care_level=choices.care_level,
            form_factor=float(level["stem_form_factor"]),
            log_length_m=choices.log_length_m,
            sawlog_min_dbh_cm=choices.sawlog_min_dbh_cm,
            road_extension_m=choices.road_extension_m,
            machine_ids={
                "feller": machine_ids["feller"],
                "skidders": skidders[: choices.skidder_count],
                "processors": tuple(machine_ids.get("processors", [])),
                "loader": machine_ids["loader"],
            },
        )
        result_payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        record = {
            **choices.to_dict(),
            "net_profit": float(result_payload["net_profit"]),
            "result": result_payload,
        }
        records.append(record)
    if not records:
        raise GameStandPrecomputeError("No finite combinations were enumerated.")
    best = max(records, key=lambda record: float(record["net_profit"]))
    worst = min(records, key=lambda record: float(record["net_profit"]))
    bounds = ScoreBounds(
        best_net_profit=float(best["net_profit"]),
        worst_net_profit=float(worst["net_profit"]),
    )
    for record in records:
        record["score"] = normalize_score(float(record["net_profit"]), bounds)
    return {
        "schema_version": SCHEMA_VERSION,
        "level_id": level["level_id"],
        "level_order": int(level.get("order", 0)),
        "level_manifest": str(level_file),
        "bounds": {
            "best_net_profit": bounds.best_net_profit,
            "worst_net_profit": bounds.worst_net_profit,
            "best_choices": {key: best[key] for key in StandChoices.__annotations__},
        },
        "completeness": {
            "complete": True,
            "combination_count": len(records),
        },
        "variants": records,
    }


def write_stand_precompute(payload: dict[str, Any], path: str | Path) -> None:
    """Write a stable precompute artifact."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_stand_precompute(path: str | Path) -> dict[str, Any]:
    """Load and schema-check a stand precompute artifact."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise GameStandPrecomputeError("Unsupported stand precompute schema.")
    return payload


def check_stand_precompute(level_path: str | Path, payload: dict[str, Any]) -> None:
    """Verify that a precompute covers the full finite menu."""
    level = _load_level(Path(level_path).expanduser().resolve())
    expected = {choices.key() for choices in enumerate_stand_choices(level)}
    actual = {
        (
            float(record["care_level"]),
            int(record["skidder_count"]),
            float(record["log_length_m"]),
            float(record["sawlog_min_dbh_cm"]),
            float(record["road_extension_m"]),
        )
        for record in payload.get("variants", [])
    }
    if expected != actual:
        raise GameStandPrecomputeError(
            f"{level['level_id']}: precompute menu mismatch "
            f"({len(expected - actual)} missing, {len(actual - expected)} extra)"
        )
    if not payload.get("completeness", {}).get("complete"):
        raise GameStandPrecomputeError(f"{level['level_id']}: precompute marked incomplete.")
    if payload.get("level_id") != level["level_id"]:
        raise GameStandPrecomputeError(f"{level['level_id']}: level id mismatch.")
