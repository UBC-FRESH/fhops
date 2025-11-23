"""Grapple yarder productivity helpers calibrated on BC coastal datasets."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _validate_inputs(turn_volume_m3: float, yarding_distance_m: float) -> None:
    """Validate generic turn volume (m³) and yarding distance (m) inputs."""
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
    """Cycle time (minutes/turn) for TR-75 swing yarder regressions."""
    return (
        fixed_time_min
        + outhaul_intercept_min
        + outhaul_distance_coeff * yarding_distance_m
        + inhaul_intercept_min
        + inhaul_distance_coeff * yarding_distance_m
    )


def _productivity(turn_volume_m3: float, cycle_time_min: float) -> float:
    """Convert turn volume (m³) and cycle time (minutes) to m³/PMH."""
    return 60.0 * turn_volume_m3 / cycle_time_min


def estimate_grapple_yarder_productivity_sr54(
    turn_volume_m3: float, yarding_distance_m: float
) -> float:
    """
    Estimate productivity (m³/PMH) for a Washington 118A skyline on mechanically bunched wood.

    Parameters
    ----------
    turn_volume_m3:
        Cubic metres per turn (≈0.5–3.0 m³ in SR-54 Table 9). Must be > 0.
    yarding_distance_m:
        Uphill skyline distance (metres). Regression calibrated for roughly 30–300 m.

    Returns
    -------
    float
        Delay-free productivity expressed in cubic metres per productive machine hour (PMH₀).

    Notes
    -----
    Based on MacDonald (1988) SR-54 Table 9 + Table 10 with the fixed 1.35 min move/minor-delay
    allowance. Use with mechanically bunched second-growth cedar/hem-fir stands similar to the
    study design.
    """

    _validate_inputs(turn_volume_m3, yarding_distance_m)
    cycle_time = _minutes_per_turn_sr54(turn_volume_m3, yarding_distance_m)
    return _productivity(turn_volume_m3, cycle_time)


def estimate_grapple_yarder_productivity_tr75_bunched(
    turn_volume_m3: float, yarding_distance_m: float
) -> float:
    """
    Estimate productivity for a Madill 084 swing yarder on mechanically bunched second-growth.

    Parameters
    ----------
    turn_volume_m3:
        Cubic metres per turn pulled by the grapple (Peterson 1987 observed 1–3 m³).
    yarding_distance_m:
        Outhaul distance along the skyline (metres). Regression calibrated for 0–400 m.

    Returns
    -------
    float
        Productivity in m³/PMH₀ drawn from TR-75 Table 6 coefficients.
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
    """
    Estimate productivity for a Madill 084 swing yarder on hand-felled second-growth.

    Parameters
    ----------
    turn_volume_m3:
        Cubic metres per turn (hand-felled timber; typically smaller than bunched).
    yarding_distance_m:
        Skyline distance in metres (0–400 m typical).

    Returns
    -------
    float
        Productivity in m³/PMH₀ using the hand-felled regression from TR-75 Table 6.
    """

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
    "estimate_grapple_yarder_productivity_adv1n35",
]


@dataclass(frozen=True)
class TN157Case:
    """
    FPInnovations TN-157 Cypress 7280B grapple yarder case-study metrics.

    Attributes
    ----------
    case_id:
        Identifier from the bulletin (``"1"``–``"7"`` or ``"combined"`` aggregate).
    label:
        Human-readable label used in CLI output.
    falling_method:
        `hand_felled`, `mechanically bunched`, etc.
    stand_type:
        Species/age mix description.
    yarding_direction:
        Uphill/downhill/mixed descriptor.
    slope_percent_average:
        Average slope (%) for the corridor mix.
    average_turn_volume_m3:
        Cubic metres per turn observed in the case study.
    average_yarding_distance_m:
        Slope distance from stump to landing (metres).
    logs_per_turn:
        Average log count per turn.
    yarding_minutes:
        Total productive minutes logged.
    total_turns:
        Number of turns observed.
    logs_per_shift:
        8 h output (logs per shift).
    volume_per_shift_m3:
        8 h volume output (m³ per shift).
    productivity_m3_per_pmh:
        Delay-free productivity (m³/PMH₀).
    logs_per_yarding_hour:
        Throughput in logs per PMH₀.
    cost_per_log_cad_1991, cost_per_m3_cad_1991:
        Cost metrics normalised to the 1991 CAD base year.
    cost_base_year:
        CPI base year for the costs (defaults to 1991).
    """

    @property
    def cycle_time_minutes(self) -> float:
        """Average cycle time (minutes/turn) for the case."""
        if self.total_turns <= 0:
            return 0.0
        return self.yarding_minutes / self.total_turns


_TN157_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/tn157_cypress7280b.json"
)
_TN147_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/tn147_highlead.json"
)
_TR122_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/tr122_swingyarder.json"
)
_ADV5N28_PATH = (
    Path(__file__).resolve().parents[3]
    / "data/reference/fpinnovations/adv5n28_skyline_conversion.json"
)
_ADV1N35_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/adv1n35_owren400.json"
)
_ADV1N40_PATH = (
    Path(__file__).resolve().parents[3] / "data/reference/fpinnovations/adv1n40_madill071.json"
)


def _weighted_average(
    values: Mapping[str, float],
    weights: Mapping[str, float],
    *,
    default: float = 0.0,
) -> float:
    """Return weighted average of ``values`` keyed by the same IDs as ``weights``."""
    total_weight = sum(weights.values())
    if total_weight <= 0:
        return default
    return sum(values[key] * weights[key] for key in values) / total_weight


@lru_cache(maxsize=1)
def _load_tn157_cases() -> Mapping[str, TN157Case]:
    """Load TN-157 case studies (cached) from the bundled JSON dataset."""
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
        volume_per_shift = sum(
            float(entry.get("volume_per_shift_m3", 0.0)) for entry in raw_entries
        )

        def weighted(key: str, default: float = 0.0) -> float:
            """Helper to compute turn-weighted averages for combined TN157 stats."""
            values = {str(entry["id"]): float(entry.get(key, 0.0)) for entry in raw_entries}
            weights = {
                str(entry["id"]): float(entry.get("total_turns", 0.0)) for entry in raw_entries
            }
            return _weighted_average(values, weights, default=default)

        avg_turn_volume = weighted("average_turn_volume_m3")
        avg_yarding_distance = weighted("average_yarding_distance_m")
        avg_logs_per_turn = weighted("logs_per_turn")
        avg_slope = _weighted_average(
            {
                str(entry["id"]): float(entry.get("slope_percent_average", 0.0))
                for entry in raw_entries
            },
            {str(entry["id"]): float(entry.get("yarding_minutes", 0.0)) for entry in raw_entries},
        )
        prod_weighted = (
            sum(
                float(entry.get("m3_per_yarding_hour", 0.0))
                * float(entry.get("yarding_minutes", 0.0))
                for entry in raw_entries
            )
            / yarding_minutes
            if yarding_minutes > 0
            else 0.0
        )
        logs_per_hour_weighted = (
            sum(
                float(entry.get("logs_per_yarding_hour", 0.0))
                * float(entry.get("yarding_minutes", 0.0))
                for entry in raw_entries
            )
            / yarding_minutes
            if yarding_minutes > 0
            else 0.0
        )
        cost_per_log = (
            sum(
                float(entry.get("cost_per_log_cad_1991", 0.0))
                * float(entry.get("logs_per_shift_8h", 0.0))
                for entry in raw_entries
            )
            / logs_per_shift
            if logs_per_shift > 0
            else 0.0
        )
        cost_per_m3 = (
            sum(
                float(entry.get("cost_per_m3_cad_1991", 0.0))
                * float(entry.get("volume_per_shift_m3", 0.0))
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
    """
    Return the available TN-157 case identifiers.

    Returns
    -------
    tuple[str, ...]
        Ordered tuple including ``"combined"`` plus the numeric case IDs present in the dataset.
    """
    cases = _load_tn157_cases()
    numeric_ids = sorted((cid for cid in cases if cid.isdigit()), key=int)
    ordered = ["combined"] + [cid for cid in numeric_ids if cid != "combined"]
    return tuple(ordered)


def get_tn157_case(case_id: str) -> TN157Case:
    """
    Return a TN-157 case dataclass by identifier.

    Parameters
    ----------
    case_id:
        Case label (`"1"`–`"7"`, `"combined"`, `"combined_turns"`, or `"Case 3"` style). ``None``/empty
        strings default to the combined record.

    Returns
    -------
    TN157Case
        Dataclass with productivity, cost, and stand descriptors from TN-157.

    Raises
    ------
    ValueError
        If the identifier is not present in the dataset.
    """
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
    """
    Look up the TN-157 case study and return its productivity (m³/PMH₀).

    Parameters
    ----------
    case_id:
        Case identifier accepted by :func:`get_tn157_case`. Defaults to the combined average.

    Returns
    -------
    float
        Productivity in cubic metres per productive machine hour.
    """
    case = get_tn157_case(case_id)
    return case.productivity_m3_per_pmh


@dataclass(frozen=True)
class TN147Case:
    """
    FPInnovations TN-147 Madill 009 highlead case-study metrics.

    Attributes
    ----------
    case_id:
        Identifier from the bulletin.
    label:
        Display label for CLI/Docs.
    average_turn_volume_m3:
        Mean payload (m³/turn); ``None`` if not recorded.
    average_yarding_distance_m:
        Mean slope distance (m); ``None`` if not recorded.
    logs_per_turn:
        Average log count per turn; ``None`` when absent.
    logs_per_shift_8h:
        Output per 8 h shift (logs).
    volume_per_shift_m3:
        Output per 8 h shift (m³).
    cost_per_log_cad_1989, cost_per_m3_cad_1989:
        Cost metrics normalised to 1989 CAD.
    cost_base_year:
        CPI base year (default 1989).
    """

    @property
    def productivity_m3_per_pmh(self) -> float:
        """Productivity for the case (m³ per productive hour)."""
        return self.volume_per_shift_m3 / 8.0


def _tn147_weighted_average(
    values: Mapping[str, float], weights: Mapping[str, float], default: float | None = None
) -> float | None:
    """Weighted average helper used for TN147 combined rows."""
    total_weight = sum(weights.values())
    if total_weight <= 0:
        return default
    return sum(values[key] * weights[key] for key in values) / total_weight


@lru_cache(maxsize=1)
def _load_tn147_cases() -> Mapping[str, TN147Case]:
    """Load TN-147 case studies (cached) from the bundled JSON dataset."""
    if not _TN147_PATH.exists():
        raise FileNotFoundError(f"TN147 dataset not found: {_TN147_PATH}")
    with _TN147_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    entries: Sequence[Mapping[str, object]] = payload.get("case_studies", [])
    cases: dict[str, TN147Case] = {}
    for entry in entries:
        case_id = str(entry["id"])
        cases[case_id] = TN147Case(
            case_id=case_id,
            label=f"Case {case_id}",
            average_turn_volume_m3=float(entry.get("avg_turn_volume_m3") or 0.0),
            average_yarding_distance_m=float(entry.get("avg_yarding_distance_m") or 0.0),
            logs_per_turn=float(entry.get("logs_per_turn") or 0.0),
            logs_per_shift_8h=float(entry.get("logs_per_shift_8h") or 0.0),
            volume_per_shift_m3=float(entry.get("volume_per_shift_m3") or 0.0),
            cost_per_log_cad_1989=float(entry.get("cost_per_log_cad_1989") or 0.0),
            cost_per_m3_cad_1989=float(entry.get("cost_per_m3_cad_1989") or 0.0),
        )

    if entries:
        total_turns = {
            str(entry["id"]): float(entry.get("total_turns") or 0.0) for entry in entries
        }
        avg_turn_volume = _tn147_weighted_average(
            {str(entry["id"]): float(entry.get("avg_turn_volume_m3") or 0.0) for entry in entries},
            total_turns,
            default=0.0,
        )
        avg_distance = _tn147_weighted_average(
            {
                str(entry["id"]): float(entry.get("avg_yarding_distance_m") or 0.0)
                for entry in entries
            },
            total_turns,
            default=0.0,
        )
        avg_logs_per_turn = _tn147_weighted_average(
            {str(entry["id"]): float(entry.get("logs_per_turn") or 0.0) for entry in entries},
            total_turns,
            default=0.0,
        )
        total_volume = sum(float(entry.get("volume_per_shift_m3") or 0.0) for entry in entries)
        total_logs = sum(float(entry.get("logs_per_shift_8h") or 0.0) for entry in entries)

        volume_weights = {
            str(entry["id"]): float(entry.get("volume_per_shift_m3") or 0.0) for entry in entries
        }
        log_weights = {
            str(entry["id"]): float(entry.get("logs_per_shift_8h") or 0.0) for entry in entries
        }

        cost_per_m3 = _tn147_weighted_average(
            {
                str(entry["id"]): float(entry.get("cost_per_m3_cad_1989") or 0.0)
                for entry in entries
            },
            volume_weights,
            default=0.0,
        )
        cost_per_log = _tn147_weighted_average(
            {
                str(entry["id"]): float(entry.get("cost_per_log_cad_1989") or 0.0)
                for entry in entries
            },
            log_weights,
            default=0.0,
        )

        cases["combined"] = TN147Case(
            case_id="combined",
            label="Combined (7-case average)",
            average_turn_volume_m3=avg_turn_volume,
            average_yarding_distance_m=avg_distance,
            logs_per_turn=avg_logs_per_turn,
            logs_per_shift_8h=total_logs,
            volume_per_shift_m3=total_volume,
            cost_per_log_cad_1989=cost_per_log,
            cost_per_m3_cad_1989=cost_per_m3,
        )
        cases["combined_turns"] = TN147Case(
            case_id="combined_turns",
            label="Combined (turn-weighted)",
            average_turn_volume_m3=avg_turn_volume,
            average_yarding_distance_m=avg_distance,
            logs_per_turn=avg_logs_per_turn,
            logs_per_shift_8h=total_logs / len(entries) if entries else 0.0,
            volume_per_shift_m3=total_volume / len(entries) if entries else 0.0,
            cost_per_log_cad_1989=cost_per_log,
            cost_per_m3_cad_1989=cost_per_m3,
        )

    return cases


def list_tn147_case_ids() -> tuple[str, ...]:
    """
    Return the available TN-147 case identifiers.

    Returns
    -------
    tuple[str, ...]
        Tuple of case IDs. Includes ``"combined"`` (default aggregate) and excludes the internal
        ``"combined_turns"`` helper used for weighting.
    """
    cases = _load_tn147_cases()
    ordered = [cid for cid in cases if cid != "combined_turns"]
    return tuple(sorted(ordered, key=lambda cid: (cid != "combined", cid)))


def get_tn147_case(case_id: str) -> TN147Case:
    """
    Return TN-147 case metadata by identifier.

    Parameters
    ----------
    case_id:
        Case identifier (numeric string or ``"combined"``). ``None``/empty defaults to ``"combined"``.

    Returns
    -------
    TN147Case
        Case dataclass with productivity and costing metrics.

    Raises
    ------
    ValueError
        If the identifier is not found in the dataset.
    """
    normalized = (case_id or "combined").strip().lower()
    if normalized in {"", "combined"}:
        normalized = "combined"
    cases = _load_tn147_cases()
    if normalized not in cases:
        raise ValueError(
            f"Unknown TN147 case '{case_id}'. Valid options: {', '.join(sorted(cases))}."
        )
    case = cases[normalized]
    if normalized == "combined_turns":
        return cases["combined"]
    return case


def estimate_grapple_yarder_productivity_tn147(case_id: str = "combined") -> float:
    """
    Look up the TN-147 case study and return productivity (m³/PMH₀).

    Parameters
    ----------
    case_id:
        Case identifier accepted by :func:`get_tn147_case`.

    Returns
    -------
    float
        Productivity in cubic metres per productive machine hour.
    """
    case = get_tn147_case(case_id)
    return case.productivity_m3_per_pmh


@dataclass(frozen=True)
class TR122Treatment:
    """
    FPInnovations TR-122 Roberts Creek swing-yarder treatment summary.

    Attributes
    ----------
    treatment_id:
        Identifier such as ``"hill_crew_a"``.
    label:
        Human-readable label (title-cased ID by default).
    volume_per_shift_m3:
        8 h shift output (m³).
    yarder_production_hours, yarder_total_hours:
        Productive and total yarder hours recorded during the study.
    loader_hours:
        Loader utilisation (hours).
    avg_piece_m3, avg_pieces_per_cycle, cycle_volume_m3:
        Payload descriptors for each cycle.
    yarding_distance_m:
        Average yarding distance (m) from the cycle distribution, if available.
    cycle_minutes:
        Mean cycle time (minutes) derived from the distribution data.
    cost_total_per_m3_cad_1996, yarder_cost_per_m3_cad_1996, loader_cost_per_m3_cad_1996:
        Cost components normalised to 1996 CAD.
    yarding_labour_per_m3_cad_1996, loading_labour_per_m3_cad_1996:
        Labour cost breakdown (1996 CAD).
    cost_base_year:
        CPI base year (1996).
    """

    @property
    def productivity_m3_per_pmh(self) -> float:
        """Productivity (m³/PMH) derived from the 8 h shift volume."""
        return self.volume_per_shift_m3 / 8.0


@lru_cache(maxsize=1)
def _load_tr122_treatments() -> Mapping[str, TR122Treatment]:
    """Load TR-122 treatment metadata from the bundled JSON dataset."""
    if not _TR122_PATH.exists():
        raise FileNotFoundError(f"TR122 dataset not found: {_TR122_PATH}")
    with _TR122_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    treatments: dict[str, TR122Treatment] = {}
    cycle_data = payload.get("cycle_distribution", {})
    for entry in payload.get("treatments", []):
        treatment_id = entry["id"]
        label = treatment_id.replace("_", " ").title()
        costs = entry.get("costs", {})
        cycle_info = cycle_data.get(treatment_id, {}).get("overall", {})
        yarding_distance = cycle_info.get("yarding_distance_m")
        if yarding_distance is None:
            yarding_distance = (
                cycle_data.get(treatment_id, {}).get("corridors", {}).get("yarding_distance_m")
            )
        treatments[treatment_id] = TR122Treatment(
            treatment_id=treatment_id,
            label=label,
            volume_per_shift_m3=float(entry.get("volume_per_shift_m3") or 0.0),
            yarder_production_hours=float(entry.get("yarder_production_hours") or 0.0),
            yarder_total_hours=float(entry.get("yarder_total_hours") or 0.0),
            loader_hours=float(entry.get("loader_hours") or 0.0),
            avg_piece_m3=float(entry.get("avg_piece_m3") or 0.0),
            avg_pieces_per_cycle=float(entry.get("avg_pieces_per_cycle") or 0.0),
            cycle_volume_m3=float(entry.get("cycle_volume_m3") or 0.0),
            yarding_distance_m=float(yarding_distance) if yarding_distance is not None else None,
            cycle_minutes=float(cycle_info.get("total_cycle_min")) if cycle_info else None,
            cost_total_per_m3_cad_1996=float(costs.get("total_yarding_loading_per_m3") or 0.0),
            yarder_cost_per_m3_cad_1996=float(costs.get("yarder_per_m3") or 0.0),
            loader_cost_per_m3_cad_1996=float(costs.get("loader_per_m3") or 0.0),
            yarding_labour_per_m3_cad_1996=float(costs.get("yarding_labour_per_m3") or 0.0),
            loading_labour_per_m3_cad_1996=float(costs.get("loading_labour_per_m3") or 0.0),
        )
    return treatments


def list_tr122_treatment_ids() -> tuple[str, ...]:
    """
    Return available TR-122 treatment identifiers.

    Returns
    -------
    tuple[str, ...]
        Sorted tuple of treatment IDs.
    """
    return tuple(sorted(_load_tr122_treatments()))


def get_tr122_treatment(treatment_id: str) -> TR122Treatment:
    """
    Return TR-122 treatment metadata by identifier.

    Parameters
    ----------
    treatment_id:
        Identifier from :func:`list_tr122_treatment_ids`.

    Returns
    -------
    TR122Treatment
        Dataclass containing productivity/cost information.

    Raises
    ------
    ValueError
        If the identifier is unknown.
    """
    treatments = _load_tr122_treatments()
    normalized = treatment_id.strip().lower()
    if normalized not in treatments:
        raise ValueError(
            f"Unknown TR122 treatment '{treatment_id}'. Valid options: {', '.join(sorted(treatments))}."
        )
    return treatments[normalized]


def estimate_grapple_yarder_productivity_tr122(treatment_id: str) -> float:
    """
    Return the TR-122 treatment productivity (m³/PMH₀).

    Parameters
    ----------
    treatment_id:
        Identifier accepted by :func:`get_tr122_treatment`.

    Returns
    -------
    float
        Productivity in m³/PMH₀.
    """
    treatment = get_tr122_treatment(treatment_id)
    return treatment.productivity_m3_per_pmh


@dataclass(frozen=True)
class ADV5N28Block:
    """
    FPInnovations Advantage Vol. 5 No. 28 skyline-conversion block metadata.

    Attributes
    ----------
    block_id:
        Identifier from the study.
    label:
        Display label (silviculture system or title-cased ID).
    silviculture_system:
        Treatment description (e.g., ``"uniform selection"``).
    area_ha, net_volume_m3_per_ha:
        Block size and net volume.
    slope_percent_average:
        Mean slope (%) across the block.
    yarding_direction:
        Uphill/downhill descriptor.
    average_turn_volume_m3, average_yarding_distance_m, logs_per_turn:
        Payload descriptors aggregated over the study.
    productivity_m3_per_shift_8h, productivity_m3_per_smh, productivity_m3_per_pmh,
    productivity_m3_per_yarding_hour:
        Reported productivity metrics.
    cost_total_actual_per_m3_cad_2002, cost_total_estimated_per_m3_cad_2002,
    cost_helicopter_reference_per_m3_cad_2002:
        Cost comparisons normalised to 2002 CAD (actual skyline, projected skyline, helicopter ref).
    notes:
        Tuple of free-form notes from the bulletin.
    cost_base_year:
        CPI base year (default 2002).
    """


def _maybe_float(value: object | None) -> float | None:
    """Return float(value) when possible, otherwise ``None``."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - dataset controlled
        return None


@lru_cache(maxsize=1)
def _load_adv5n28_blocks() -> Mapping[str, ADV5N28Block]:
    """Load ADV5N28 skyline-conversion blocks from the bundled JSON dataset."""
    if not _ADV5N28_PATH.exists():
        raise FileNotFoundError(f"ADV5N28 dataset not found: {_ADV5N28_PATH}")
    with _ADV5N28_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)

    blocks: dict[str, ADV5N28Block] = {}
    for entry in payload.get("blocks", []):
        block_id = entry.get("id")
        if not block_id:
            continue
        yarding = entry.get("yarding", {}) or {}
        costs = entry.get("costs_cad_2002_per_m3", {}) or {}
        label = entry.get("silviculture_system") or block_id.replace("_", " ").title()
        blocks[block_id.lower()] = ADV5N28Block(
            block_id=block_id,
            label=label,
            silviculture_system=label,
            area_ha=float(entry.get("area_ha") or 0.0),
            net_volume_m3_per_ha=float(entry.get("net_volume_m3_per_ha") or 0.0),
            slope_percent_average=float(entry.get("slope_percent_average") or 0.0),
            yarding_direction=entry.get("yarding_direction", "downhill"),
            average_turn_volume_m3=float(yarding.get("average_turn_volume_m3") or 0.0),
            average_yarding_distance_m=float(
                yarding.get("average_slope_yarding_distance_m")
                or yarding.get("average_yarding_distance_m")
                or 0.0
            ),
            logs_per_turn=float(
                yarding.get("average_turn_pieces") or yarding.get("average_logs_per_turn") or 0.0
            ),
            productivity_m3_per_shift_8h=float(yarding.get("productivity_m3_per_shift_8h") or 0.0),
            productivity_m3_per_smh=float(yarding.get("productivity_m3_per_smh") or 0.0),
            productivity_m3_per_pmh=float(yarding.get("productivity_m3_per_pmh") or 0.0),
            productivity_m3_per_yarding_hour=float(
                yarding.get("productivity_m3_per_yarding_hour") or 0.0
            ),
            cost_total_actual_per_m3_cad_2002=float(costs.get("total_actual") or 0.0),
            cost_total_estimated_per_m3_cad_2002=_maybe_float(costs.get("estimated_future_total")),
            cost_helicopter_reference_per_m3_cad_2002=_maybe_float(
                costs.get("local_helicopter_reference_total")
            ),
            notes=tuple(entry.get("notes", [])),
        )
    return blocks


def list_adv5n28_block_ids() -> tuple[str, ...]:
    """
    Return sorted ADV5N28 block identifiers.

    Returns
    -------
    tuple[str, ...]
        Tuple of lowercase block IDs available in the dataset.
    """
    return tuple(sorted(_load_adv5n28_blocks()))


def get_adv5n28_block(block_id: str) -> ADV5N28Block:
    """
    Return ADV5N28 block metadata by identifier.

    Parameters
    ----------
    block_id:
        Identifier from :func:`list_adv5n28_block_ids` (case-insensitive).

    Returns
    -------
    ADV5N28Block
        Block metadata including productivity and cost references.

    Raises
    ------
    ValueError
        If the identifier is missing or unknown.
    """
    if not block_id:
        raise ValueError("Block identifier is required for ADV5N28 presets.")
    blocks = _load_adv5n28_blocks()
    normalized = block_id.strip().lower()
    if normalized not in blocks:
        raise ValueError(
            f"Unknown ADV5N28 block '{block_id}'. Valid options: {', '.join(sorted(blocks))}."
        )
    return blocks[normalized]


def estimate_grapple_yarder_productivity_adv5n28(block_id: str) -> float:
    """
    Return the ADV5N28 block productivity (m³/PMH₀).

    Parameters
    ----------
    block_id:
        Identifier accepted by :func:`get_adv5n28_block`.

    Returns
    -------
    float
        Productivity in m³ per PMH₀.
    """
    block = get_adv5n28_block(block_id)
    return block.productivity_m3_per_pmh


@dataclass(frozen=True)
class ADV1N35Metadata:
    """
    Cycle-time/productivity coefficients for the ADV1N35 Owren 400 dataset.

    Attributes
    ----------
    intercept, slope_distance_coeff, lateral_distance_coeff, stems_coeff:
        Regression coefficients from the FPInnovations Advantage Vol. 1 No. 35 study.
    default_turn_volume_m3, default_stems_per_turn, default_lateral_distance_m:
        Default payload parameters used when optional arguments are omitted.
    default_in_cycle_delay_min:
        Default in-cycle delay minutes appended to the regression.
    utilisation:
        Observed utilisation fraction applied when calculating PMH.
    note:
        Short citation or provenance string rendered in CLI output.
    """

    intercept: float
    slope_distance_coeff: float
    lateral_distance_coeff: float
    stems_coeff: float
    default_turn_volume_m3: float
    default_stems_per_turn: float
    default_lateral_distance_m: float
    default_in_cycle_delay_min: float
    utilisation: float
    note: str


@lru_cache(maxsize=1)
def get_adv1n35_metadata() -> ADV1N35Metadata:
    """
    Return the cached ADV1N35 Owren 400 regression metadata.

    Returns
    -------
    ADV1N35Metadata
        Dataclass with regression coefficients and default payload assumptions.

    Raises
    ------
    FileNotFoundError
        If the ADV1N35 dataset JSON is missing.
    """
    if not _ADV1N35_PATH.exists():
        raise FileNotFoundError(f"ADV1N35 dataset not found: {_ADV1N35_PATH}")
    with _ADV1N35_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    coeffs = payload["regressions"]["cycle_time"].get("coefficients", {})
    defaults = payload["regressions"]["productivity"]["defaults"]
    note = (
        "[dim]Regression from FPInnovations Advantage Vol. 1 No. 35 "
        "(Owren 400 hydrostatic yarder with single-tree intermediate supports).[/dim]"
    )
    return ADV1N35Metadata(
        intercept=float(coeffs.get("intercept", 1.94)),
        slope_distance_coeff=float(coeffs.get("slope_distance", 0.0151)),
        lateral_distance_coeff=float(coeffs.get("lateral_distance", 0.0511)),
        stems_coeff=float(coeffs.get("stems_per_turn", 0.147)),
        default_turn_volume_m3=float(defaults.get("payload_volume_m3", 1.97)),
        default_stems_per_turn=float(defaults.get("payload_stems", 2.63)),
        default_lateral_distance_m=float(defaults.get("lateral_distance_m", 11.0)),
        default_in_cycle_delay_min=float(defaults.get("in_cycle_delay_minutes", 0.69)),
        utilisation=float(defaults.get("utilisation", 0.94)),
        note=note,
    )


def estimate_grapple_yarder_productivity_adv1n35(
    *,
    turn_volume_m3: float,
    yarding_distance_m: float,
    lateral_distance_m: float | None = None,
    stems_per_turn: float | None = None,
    in_cycle_delay_minutes: float | None = None,
) -> float:
    """
    Estimate productivity (m³/PMH₀) for the Owren 400 hydrostatic yarder (ADV1N35).

    Parameters
    ----------
    turn_volume_m3:
        Payload volume per turn (m³). Must be > 0.
    yarding_distance_m:
        Slope distance from stump to landing (m). Must be ≥ 0.
    lateral_distance_m:
        Optional lateral distance (m). Defaults to the dataset average when ``None``.
    stems_per_turn:
        Optional stems per turn. Defaults to the dataset average when ``None``.
    in_cycle_delay_minutes:
        Optional minutes of hook/unhook delays to add to the regression. Defaults to the dataset
        average when ``None``.

    Returns
    -------
    float
        Productivity in cubic metres per productive machine hour.
    """

    _validate_inputs(turn_volume_m3, yarding_distance_m)
    if lateral_distance_m is not None and lateral_distance_m < 0:
        raise ValueError("lateral_distance_m must be >= 0")
    if stems_per_turn is not None and stems_per_turn <= 0:
        raise ValueError("grapple_stems_per_cycle must be > 0")
    if in_cycle_delay_minutes is not None and in_cycle_delay_minutes < 0:
        raise ValueError("grapple_in_cycle_delay_minutes must be >= 0")

    metadata = get_adv1n35_metadata()
    lateral = (
        metadata.default_lateral_distance_m if lateral_distance_m is None else lateral_distance_m
    )
    stems = metadata.default_stems_per_turn if stems_per_turn is None else stems_per_turn
    delay = (
        metadata.default_in_cycle_delay_min
        if in_cycle_delay_minutes is None
        else in_cycle_delay_minutes
    )

    cycle_time_min = (
        metadata.intercept
        + metadata.slope_distance_coeff * yarding_distance_m
        + metadata.lateral_distance_coeff * lateral
        + metadata.stems_coeff * stems
    )
    cycle_time_min += delay
    if cycle_time_min <= 0:
        raise ValueError("Derived cycle time must be > 0")
    return _productivity(turn_volume_m3, cycle_time_min)


@dataclass(frozen=True)
class ADV1N40Metadata:
    """
    Cycle-time components for the ADV1N40 Madill 071 downhill skyline study.

    Attributes
    ----------
    outhaul_intercept, outhaul_distance_coeff, inhaul_intercept, inhaul_distance_coeff:
        Regression coefficients describing skyline travel times.
    hook_minutes, unhook_minutes:
        Average hook/unhook times (minutes).
    default_delay_minutes:
        Default in-cycle delay appended to the regression.
    default_turn_volume_m3, default_yarding_distance_m:
        Default payload and distance values for CLI fallbacks.
    note:
        Citation rendered in CLI help.
    """

    outhaul_intercept: float
    outhaul_distance_coeff: float
    inhaul_intercept: float
    inhaul_distance_coeff: float
    hook_minutes: float
    unhook_minutes: float
    default_delay_minutes: float
    default_turn_volume_m3: float
    default_yarding_distance_m: float
    note: str


@lru_cache(maxsize=1)
def get_adv1n40_metadata() -> ADV1N40Metadata:
    """
    Return cached ADV1N40 regression metadata.

    Returns
    -------
    ADV1N40Metadata
        Dataclass containing skyline coefficients and defaults.

    Raises
    ------
    FileNotFoundError
        If the ADV1N40 dataset JSON is missing.
    """
    if not _ADV1N40_PATH.exists():
        raise FileNotFoundError(f"ADV1N40 dataset not found: {_ADV1N40_PATH}")
    with _ADV1N40_PATH.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    coeffs = payload["regressions"]["cycle_time"]["coefficients"]
    defaults = payload["regressions"]["productivity"]["defaults"]
    note = (
        "[dim]Regression from FPInnovations Advantage Vol. 1 No. 40 "
        "(Madill 071 running/scab downhill skyline for group selection blocks).[/dim]"
    )
    return ADV1N40Metadata(
        outhaul_intercept=float(coeffs.get("outhaul_intercept", 0.0)),
        outhaul_distance_coeff=float(coeffs.get("outhaul_distance", 0.0)),
        inhaul_intercept=float(coeffs.get("inhaul_intercept", 0.0)),
        inhaul_distance_coeff=float(coeffs.get("inhaul_distance", 0.0)),
        hook_minutes=float(coeffs.get("hook_minutes", 0.0)),
        unhook_minutes=float(coeffs.get("unhook_minutes", 0.0)),
        default_delay_minutes=float(
            payload["regressions"]["cycle_time"].get("delay_default_minutes", 0.0)
        ),
        default_turn_volume_m3=float(defaults.get("turn_volume_m3", 2.9)),
        default_yarding_distance_m=float(defaults.get("yarding_distance_m", 103.0)),
        note=note,
    )


def estimate_grapple_yarder_productivity_adv1n40(
    *,
    turn_volume_m3: float,
    yarding_distance_m: float,
    in_cycle_delay_minutes: float | None = None,
) -> float:
    """
    Estimate productivity (m³/PMH₀) for the Madill 071 downhill running/scab skyline (ADV1N40).

    Parameters
    ----------
    turn_volume_m3:
        Cubic metres per turn (must be > 0).
    yarding_distance_m:
        Slope distance (m). Must be ≥ 0.
    in_cycle_delay_minutes:
        Optional per-cycle delay minutes applied after the regression. Defaults to the dataset
        average when ``None``.

    Returns
    -------
    float
        Productivity in cubic metres per PMH₀.
    """

    _validate_inputs(turn_volume_m3, yarding_distance_m)
    if in_cycle_delay_minutes is not None and in_cycle_delay_minutes < 0:
        raise ValueError("in_cycle_delay_minutes must be >= 0")

    metadata = get_adv1n40_metadata()
    delay = (
        metadata.default_delay_minutes if in_cycle_delay_minutes is None else in_cycle_delay_minutes
    )

    outhaul = metadata.outhaul_intercept + metadata.outhaul_distance_coeff * yarding_distance_m
    inhaul = metadata.inhaul_intercept + metadata.inhaul_distance_coeff * yarding_distance_m
    cycle = metadata.hook_minutes + metadata.unhook_minutes + outhaul + inhaul + delay
    if cycle <= 0:
        raise ValueError("Derived cycle time must be > 0")
    return _productivity(turn_volume_m3, cycle)


__all__ += [
    "TN157Case",
    "estimate_grapple_yarder_productivity_tn157",
    "get_tn157_case",
    "list_tn157_case_ids",
    "TN147Case",
    "estimate_grapple_yarder_productivity_tn147",
    "get_tn147_case",
    "list_tn147_case_ids",
    "TR122Treatment",
    "estimate_grapple_yarder_productivity_tr122",
    "get_tr122_treatment",
    "list_tr122_treatment_ids",
    "ADV5N28Block",
    "estimate_grapple_yarder_productivity_adv5n28",
    "get_adv5n28_block",
    "list_adv5n28_block_ids",
    "ADV1N35Metadata",
    "estimate_grapple_yarder_productivity_adv1n35",
    "get_adv1n35_metadata",
    "ADV1N40Metadata",
    "estimate_grapple_yarder_productivity_adv1n40",
    "get_adv1n40_metadata",
]
