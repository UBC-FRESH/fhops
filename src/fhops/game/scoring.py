"""Score normalization for stand-scale game attempts."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ScoreBounds", "normalize_score"]


@dataclass(frozen=True, slots=True)
class ScoreBounds:
    """Best and worst net profit in a level's finite parameter space."""

    best_net_profit: float
    worst_net_profit: float

    def __post_init__(self) -> None:
        if self.best_net_profit < self.worst_net_profit:
            raise ValueError("best_net_profit must be >= worst_net_profit.")

    @property
    def span(self) -> float:
        """Return the best-minus-worst range."""
        return self.best_net_profit - self.worst_net_profit


def normalize_score(net_profit: float, bounds: ScoreBounds) -> float:
    """Map net profit to a clamped 0–100 score."""
    if not bounds.span:
        return 100.0 if net_profit >= bounds.best_net_profit else 0.0
    score = 100.0 * (net_profit - bounds.worst_net_profit) / bounds.span
    return max(0.0, min(100.0, score))
