"""Roadside processor and loader productivity helpers."""

from __future__ import annotations

from dataclasses import dataclass

_TREE_FORM_PRODUCTIVITY_MULTIPLIERS = {
    0: 1.0,
    1: 1.0 / 1.56,  # 56 % longer processing time → productivity ↓ by 1/1.56
    2: 1.0 / 1.84,  # 84 % longer processing time → productivity ↓ by 1/1.84
}

_BERRY_BASE_SLOPE = 34.7
_BERRY_BASE_INTERCEPT = 11.3
_BERRY_DEFAULT_UTILISATION = 0.91


@dataclass(frozen=True)
class ProcessorProductivityResult:
    base_productivity_m3_per_pmh: float
    tree_form_multiplier: float
    crew_multiplier: float
    delay_multiplier: float
    delay_free_productivity_m3_per_pmh: float
    productivity_m3_per_pmh: float
    piece_size_m3: float
    tree_form_category: int


def estimate_processor_productivity_berry2019(
    *,
    piece_size_m3: float,
    tree_form_category: int = 0,
    crew_multiplier: float = 1.0,
    delay_multiplier: float = _BERRY_DEFAULT_UTILISATION,
) -> ProcessorProductivityResult:
    if piece_size_m3 <= 0:
        raise ValueError("piece_size_m3 must be > 0")
    if tree_form_category not in _TREE_FORM_PRODUCTIVITY_MULTIPLIERS:
        raise ValueError("tree_form_category must be 0, 1, or 2")
    if crew_multiplier <= 0:
        raise ValueError("crew_multiplier must be > 0")
    if not (0.0 < delay_multiplier <= 1.0):
        raise ValueError("delay_multiplier must lie in (0, 1]")

    base_productivity = _BERRY_BASE_SLOPE * piece_size_m3 + _BERRY_BASE_INTERCEPT
    tree_multiplier = _TREE_FORM_PRODUCTIVITY_MULTIPLIERS[tree_form_category]
    delay_free = base_productivity * tree_multiplier * crew_multiplier
    productivity = delay_free * delay_multiplier

    return ProcessorProductivityResult(
        base_productivity_m3_per_pmh=base_productivity,
        tree_form_multiplier=tree_multiplier,
        crew_multiplier=crew_multiplier,
        delay_multiplier=delay_multiplier,
        delay_free_productivity_m3_per_pmh=delay_free,
        productivity_m3_per_pmh=productivity,
        piece_size_m3=piece_size_m3,
        tree_form_category=tree_form_category,
    )
