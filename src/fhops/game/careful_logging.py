"""Careful-logging trade-offs for selection-cut game levels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "CarefulLoggingCurve",
    "CarefulLoggingLevel",
    "DEFAULT_CAREFUL_LOGGING_CURVE",
]


@dataclass(frozen=True, slots=True)
class CarefulLoggingLevel:
    """One hidden careful-logging setting.

    The level is a player-facing ordinal setting. The productivity, premium, and
    residual-damage values are server-side scoring inputs and are not sent to the
    client as an exact mapping before the attempt completes.
    """

    level: float
    label: str
    care_productivity_multiplier: float
    care_premium_per_m3: float
    residual_damage_fraction: float


@dataclass(frozen=True, slots=True)
class CarefulLoggingCurve:
    """Selection-cut productivity, care-cost, and residual-damage curve."""

    levels: tuple[CarefulLoggingLevel, ...]
    base_selection_cut_productivity_multiplier: float = 0.80
    public_premium_range_per_m3: tuple[float, float] = (0.0, 14.0)
    public_productivity_multiplier_range: tuple[float, float] = (0.72, 1.0)
    public_residual_damage_fraction_range: tuple[float, float] = (0.04, 0.20)

    def __post_init__(self) -> None:
        if not 0.0 < self.base_selection_cut_productivity_multiplier <= 1.0:
            raise ValueError("base selection-cut productivity multiplier must be in (0, 1].")
        if len(self.levels) < 2:
            raise ValueError("careful-logging curve needs at least two levels.")
        seen: set[float] = set()
        for item in self.levels:
            if item.level in seen:
                raise ValueError(f"duplicate careful-logging level {item.level!r}")
            seen.add(item.level)
            if not 0.0 < item.care_productivity_multiplier <= 1.0:
                raise ValueError("care productivity multiplier must be in (0, 1].")
            if item.care_premium_per_m3 < 0.0:
                raise ValueError("care premium must be non-negative.")
            if not 0.0 <= item.residual_damage_fraction <= 1.0:
                raise ValueError("residual damage fraction must be in [0, 1].")
        if self.levels != tuple(sorted(self.levels, key=lambda item: item.level)):
            raise ValueError("careful-logging levels must be sorted.")

    def get(self, level: float) -> CarefulLoggingLevel:
        """Return the exact server-side setting for an ordinal level."""
        for item in self.levels:
            if abs(item.level - level) <= 1e-9:
                return item
        raise KeyError(f"Unknown careful-logging level {level!r}")

    def evaluate(
        self,
        level: float,
        *,
        harvest_volume_m3: float,
        residual_asset_value: float,
        base_machine_cost: float,
    ) -> dict[str, Any]:
        """Evaluate the profit penalty for one careful-logging setting.

        ``base_machine_cost`` is the cost at the level's standard machine rate.
        The selection-cut base multiplier and care multiplier both reduce
        productivity, so the machine cost is divided by their product.
        """
        if harvest_volume_m3 < 0.0 or residual_asset_value < 0.0 or base_machine_cost < 0.0:
            raise ValueError("evaluate inputs must be non-negative.")
        item = self.get(level)
        effective = (
            self.base_selection_cut_productivity_multiplier * item.care_productivity_multiplier
        )
        machine_cost = base_machine_cost / effective
        care_premium = harvest_volume_m3 * item.care_premium_per_m3
        residual_damage_loss = residual_asset_value * item.residual_damage_fraction
        return {
            "level": item.level,
            "label": item.label,
            "effective_productivity_multiplier": effective,
            "machine_cost": machine_cost,
            "care_premium": care_premium,
            "residual_damage_loss": residual_damage_loss,
            "total_penalty": machine_cost + care_premium + residual_damage_loss,
        }

    def best_level(
        self,
        *,
        harvest_volume_m3: float,
        residual_asset_value: float,
        base_machine_cost: float,
    ) -> dict[str, Any]:
        """Return the lowest-penalty setting for the supplied economics."""
        rows = [
            self.evaluate(
                item.level,
                harvest_volume_m3=harvest_volume_m3,
                residual_asset_value=residual_asset_value,
                base_machine_cost=base_machine_cost,
            )
            for item in self.levels
        ]
        return min(rows, key=lambda row: float(row["total_penalty"]))

    def public_summary(self) -> dict[str, Any]:
        """Return the range-only briefing; never expose the exact mapping."""
        return {
            "levels": [item.level for item in self.levels],
            "labels": [item.label for item in self.levels],
            "selection_cut_base_productivity_multiplier": (
                self.base_selection_cut_productivity_multiplier
            ),
            "care_premium_per_m3_range": list(self.public_premium_range_per_m3),
            "productivity_multiplier_range": list(self.public_productivity_multiplier_range),
            "residual_damage_fraction_range": list(self.public_residual_damage_fraction_range),
            "note": (
                "Only plausible consequence ranges are shown before play; the exact "
                "productivity, premium, and damage mapping is hidden until debrief."
            ),
        }


DEFAULT_CAREFUL_LOGGING_CURVE = CarefulLoggingCurve(
    levels=(
        CarefulLoggingLevel(0.0, "standard", 1.00, 0.0, 0.20),
        CarefulLoggingLevel(0.25, "light care", 0.96, 2.0, 0.13),
        CarefulLoggingLevel(0.50, "moderate care", 0.90, 3.0, 0.085),
        CarefulLoggingLevel(0.75, "high care", 0.82, 7.0, 0.055),
        CarefulLoggingLevel(1.00, "maximum care", 0.72, 14.0, 0.04),
    )
)
