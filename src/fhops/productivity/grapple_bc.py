"""Grapple yarder productivity helpers calibrated on BC coastal datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping


def _validate_inputs(turn_volume_m3: float, yarding_distance_m: float) -> None:
    if turn_volume_m3 <= 0:
        raise ValueError("turn_volume_m3 must be > 0")
    if yarding_distance_m < 0:
        raise ValueError("yarding_distance_m must be >= 0")


def _minutes_per_turn_sr54(turn_volume_m3: float, yarding_distance_m: float) -> float:
    """Return cycle time (minutes/turn) for MacDonald (1988) Grapple 1 regression.

    Outhaul + inhaul comes from Table 9 in SR-54:
        time = 0.25 + distance * (0.00455 + 0.00030 * V)
    A fixed 1.35 min (hook/unhook/deck + moves + minor delays) is included per Table 10.
    """

    return 1.60 + yarding_distance_m * (0.00455 + 0.00030 * turn_volume_m3)


def _minutes_per_turn_tr75(
    yarding_distance_m: float,
    *,
    fixed_time_min: float,
    outhaul_intercept_min: float,
    outhaul_distance_coeff: float,
    inhaul_intercept_min: float,
    inhaul_distance_coeff: float,
) -> float:
    return (
        fixed_time_min
        + outhaul_intercept_min
        + outhaul_distance_coeff * yarding_distance_m
        + inhaul_intercept_min
        + inhaul_distance_coeff * yarding_distance_m
    )


def _productivity(turn_volume_m3: float, cycle_time_min: float) -> float:
    # Convert cycle time to hours and divide volume per turn.
    return 60.0 * turn_volume_m3 / cycle_time_min


def estimate_grapple_yarder_productivity_sr54(
    turn_volume_m3: float, yarding_distance_m: float
) -> float:
    """Estimate productivity (m³/PMH) for Washington 118A yarder on mechanically bunched wood.

    Derived from MacDonald (1988) SR-54, Table 9 and Table 10. Includes average move/minor delays.
    """

    _validate_inputs(turn_volume_m3, yarding_distance_m)
    cycle_time = _minutes_per_turn_sr54(turn_volume_m3, yarding_distance_m)
    return _productivity(turn_volume_m3, cycle_time)


def estimate_grapple_yarder_productivity_tr75_bunched(
    turn_volume_m3: float, yarding_distance_m: float
) -> float:
    """Estimate productivity for Madill 084 swing yarder on mechanically bunched second-growth.

    Regression coefficients from Peterson (1987) TR-75, Table 6.
    """

    _validate_inputs(turn_volume_m3, yarding_distance_m)
    cycle_time = _minutes_per_turn_tr75(
        yarding_distance_m,
        fixed_time_min=0.69,
        outhaul_intercept_min=0.0296,
        outhaul_distance_coeff=0.0027,
        inhaul_intercept_min=0.0,
        inhaul_distance_coeff=0.0044,
    )
    return _productivity(turn_volume_m3, cycle_time)


def estimate_grapple_yarder_productivity_tr75_handfelled(
    turn_volume_m3: float, yarding_distance_m: float
) -> float:
    """Estimate productivity for Madill 084 swing yarder on hand-felled second-growth timber."""

    _validate_inputs(turn_volume_m3, yarding_distance_m)
    cycle_time = _minutes_per_turn_tr75(
        yarding_distance_m,
        fixed_time_min=0.74,
        outhaul_intercept_min=0.0323,
        outhaul_distance_coeff=0.0026,
        inhaul_intercept_min=0.0247,
        inhaul_distance_coeff=0.0035,
    )
    return _productivity(turn_volume_m3, cycle_time)


__all__ = [
    "estimate_grapple_yarder_productivity_sr54",
    "estimate_grapple_yarder_productivity_tr75_bunched",
    "estimate_grapple_yarder_productivity_tr75_handfelled",
]


@dataclass(frozen=True)
class TN157Case:
    case_id: str
    label: str
    falling_method: str
    stand_type: str
    yarding_direction: str
    slope_percent_average: float
    average_turn_volume_m3: float
    average_yarding_distance_m: float
    logs_per_turn: float
    yarding_minutes: float
    total_turns: int
    logs_per_shift: int
    volume_per_shift_m3: float
    productivity_m3_per_pmh: float
    logs_per_yarding_hour: float
    cost_per_log_cad_1991: float
    cost_per_m3_cad_1991: float

    @property
    def cycle_time_minutes(self) -> float:
        if self.total_turns <= 0:
            return 0.0
        return self.yarding_minutes / self.total_turns


_TN157_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/tn157_cypress7280b.json"
)


def _weighted_average(
    values: Mapping[str, float],
    weights: Mapping[str, float],
    *,
    default: float = 0.0,
) -> float:
    total_weight = sum(weights.values())
    if total_weight <= 0:
        return default
    return sum(values[key] * weights[key] for key in values) / total_weight


@lru_cache(maxsize=1)
def _load_tn157_cases() -> Mapping[str, TN157Case]:
    if not _TN157_PATH.exists():
        raise FileNotFoundError(f"TN157 dataset not found: {_TN157_PATH}")
    with _TN157_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)

    cases: dict[str, TN157Case] = {}
    raw_entries = payload.get("case_studies", [])
    for entry in raw_entries:
        case_id = str(entry["id"])
        cases[case_id] = TN157Case(
            case_id=case_id,
            label=f"Case {case_id}",
            falling_method=entry.get("falling_method", "hand_felled"),
            stand_type=entry.get("stand_type", "mixed"),
            yarding_direction=entry.get("yarding_direction", "mixed"),
            slope_percent_average=float(entry.get("slope_percent_average", 0.0)),
            average_turn_volume_m3=float(entry.get("average_turn_volume_m3", 0.0)),
            average_yarding_distance_m=float(entry.get("average_yarding_distance_m", 0.0)),
            logs_per_turn=float(entry.get("logs_per_turn", 0.0)),
            yarding_minutes=float(entry.get("yarding_minutes", 0.0)),
            total_turns=int(entry.get("total_turns", 0)),
            logs_per_shift=int(entry.get("logs_per_shift_8h", 0)),
            volume_per_shift_m3=float(entry.get("volume_per_shift_m3", 0.0)),
            productivity_m3_per_pmh=float(entry.get("m3_per_yarding_hour", 0.0)),
            logs_per_yarding_hour=float(entry.get("logs_per_yarding_hour", 0.0)),
            cost_per_log_cad_1991=float(entry.get("cost_per_log_cad_1991", 0.0)),
            cost_per_m3_cad_1991=float(entry.get("cost_per_m3_cad_1991", 0.0)),
        )

    if raw_entries:
        total_turns = sum(int(entry.get("total_turns", 0)) for entry in raw_entries)
        yarding_minutes = sum(float(entry.get("yarding_minutes", 0.0)) for entry in raw_entries)
        logs_per_shift = sum(int(entry.get("logs_per_shift_8h", 0)) for entry in raw_entries)
        volume_per_shift = sum(float(entry.get("volume_per_shift_m3", 0.0)) for entry in raw_entries)

        def weighted(key: str, default: float = 0.0) -> float:
            values = {str(entry["id"]): float(entry.get(key, 0.0)) for entry in raw_entries}
            weights = {str(entry["id"]): float(entry.get("total_turns", 0.0)) for entry in raw_entries}
            return _weighted_average(values, weights, default=default)

        avg_turn_volume = weighted("average_turn_volume_m3")
        avg_yarding_distance = weighted("average_yarding_distance_m")
        avg_logs_per_turn = weighted("logs_per_turn")
        avg_slope = _weighted_average(
            {str(entry["id"]): float(entry.get("slope_percent_average", 0.0)) for entry in raw_entries},
            {str(entry["id"]): float(entry.get("yarding_minutes", 0.0)) for entry in raw_entries},
        )
        prod_weighted = (
            sum(
                float(entry.get("m3_per_yarding_hour", 0.0)) * float(entry.get("yarding_minutes", 0.0))
                for entry in raw_entries
            )
            / yarding_minutes
            if yarding_minutes > 0
            else 0.0
        )
        logs_per_hour_weighted = (
            sum(
                float(entry.get("logs_per_yarding_hour", 0.0)) * float(entry.get("yarding_minutes", 0.0))
                for entry in raw_entries
            )
            / yarding_minutes
            if yarding_minutes > 0
            else 0.0
        )
        cost_per_log = (
            sum(
                float(entry.get("cost_per_log_cad_1991", 0.0)) * float(entry.get("logs_per_shift_8h", 0.0))
                for entry in raw_entries
            )
            / logs_per_shift
            if logs_per_shift > 0
            else 0.0
        )
        cost_per_m3 = (
            sum(
                float(entry.get("cost_per_m3_cad_1991", 0.0)) * float(entry.get("volume_per_shift_m3", 0.0))
                for entry in raw_entries
            )
            / volume_per_shift
            if volume_per_shift > 0
            else 0.0
        )

        cases["combined"] = TN157Case(
            case_id="combined",
            label="Combined (7-case average)",
            falling_method="mixed",
            stand_type="mixed",
            yarding_direction="mixed",
            slope_percent_average=avg_slope,
            average_turn_volume_m3=avg_turn_volume,
            average_yarding_distance_m=avg_yarding_distance,
            logs_per_turn=avg_logs_per_turn,
            yarding_minutes=yarding_minutes,
            total_turns=total_turns,
            logs_per_shift=logs_per_shift,
            volume_per_shift_m3=volume_per_shift,
            productivity_m3_per_pmh=prod_weighted,
            logs_per_yarding_hour=logs_per_hour_weighted,
            cost_per_log_cad_1991=cost_per_log,
            cost_per_m3_cad_1991=cost_per_m3,
        )
    return cases


def list_tn157_case_ids() -> tuple[str, ...]:
    cases = _load_tn157_cases()
    numeric_ids = sorted((cid for cid in cases if cid.isdigit()), key=int)
    ordered = ["combined"] + [cid for cid in numeric_ids if cid != "combined"]
    return tuple(ordered)


def get_tn157_case(case_id: str) -> TN157Case:
    normalized = (case_id or "combined").strip().lower()
    if normalized in {"", "combined", "avg", "average"}:
        normalized = "combined"
    if normalized.startswith("case"):
        normalized = normalized[4:].strip()
    cases = _load_tn157_cases()
    if normalized not in cases:
        raise ValueError(f"Unknown TN157 case '{case_id}'. Valid options: {', '.join(cases)}.")
    return cases[normalized]


def estimate_grapple_yarder_productivity_tn157(case_id: str = "combined") -> float:
    case = get_tn157_case(case_id)
    return case.productivity_m3_per_pmh


__all__ += [
    "TN157Case",
    "estimate_grapple_yarder_productivity_tn157",
    "get_tn157_case",
    "list_tn157_case_ids",
]
