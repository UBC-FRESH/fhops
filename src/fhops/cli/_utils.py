"""CLI helper utilities for FHOPS."""

from __future__ import annotations

from typing import Sequence


OPERATOR_PRESETS: dict[str, dict[str, float]] = {
    "balanced": {"swap": 1.0, "move": 1.0},
    "swap-only": {"swap": 1.0, "move": 0.0},
    "move-only": {"swap": 0.0, "move": 1.0},
    "swap-heavy": {"swap": 2.0, "move": 0.5},
}


def parse_operator_weights(weight_args: Sequence[str] | None) -> dict[str, float]:
    """Parse name=value weight strings into a dictionary."""
    weights: dict[str, float] = {}
    if not weight_args:
        return weights
    for arg in weight_args:
        if "=" not in arg:
            raise ValueError(f"Operator weight must be in name=value format (got '{arg}')")
        name, raw_value = arg.split("=", 1)
        name = name.strip()
        if not name:
            raise ValueError(f"Operator weight missing operator name in '{arg}'")
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise ValueError(
                f"Operator weight for '{name}' must be numeric (got '{raw_value}')"
            ) from exc
        weights[name.lower()] = value
    return weights


def parse_operator_preset(preset: str | None):
    """Return (operators, weights) for a preset."""
    if not preset:
        return None, {}
    key = preset.lower()
    config = OPERATOR_PRESETS.get(key)
    if config is None:
        raise ValueError(
            f"Unknown operator preset '{preset}'. Available: {', '.join(sorted(OPERATOR_PRESETS))}"
        )
    weights = {name.lower(): float(weight) for name, weight in config.items()}
    operators = [name for name, weight in weights.items() if weight > 0]
    return operators or None, weights


def operator_preset_help() -> str:
    return ", ".join(sorted(OPERATOR_PRESETS))


__all__ = [
    "parse_operator_weights",
    "parse_operator_preset",
    "operator_preset_help",
    "OPERATOR_PRESETS",
]
