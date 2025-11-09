"""CLI helper utilities for FHOPS."""

from __future__ import annotations

from typing import Sequence


OPERATOR_PRESETS: dict[str, dict[str, float]] = {
    "balanced": {
        "swap": 1.0,
        "move": 1.0,
        "block_insertion": 0.0,
        "cross_exchange": 0.0,
        "mobilisation_shake": 0.0,
    },
    "swap-only": {
        "swap": 1.0,
        "move": 0.0,
        "block_insertion": 0.0,
        "cross_exchange": 0.0,
        "mobilisation_shake": 0.0,
    },
    "move-only": {
        "swap": 0.0,
        "move": 1.0,
        "block_insertion": 0.0,
        "cross_exchange": 0.0,
        "mobilisation_shake": 0.0,
    },
    "swap-heavy": {
        "swap": 2.0,
        "move": 0.5,
        "block_insertion": 0.0,
        "cross_exchange": 0.0,
        "mobilisation_shake": 0.0,
    },
    "diversify": {
        "swap": 1.5,
        "move": 1.5,
        "block_insertion": 0.0,
        "cross_exchange": 0.0,
        "mobilisation_shake": 0.0,
    },
}

OPERATOR_PRESET_DESCRIPTIONS: dict[str, str] = {
    "balanced": "Default swap/move weights (1.0 each).",
    "swap-only": "Disable move and rely solely on swap moves.",
    "move-only": "Disable swap and allow only move operations.",
    "swap-heavy": "Bias toward swap moves while keeping move available.",
    "diversify": "Encourage both operators equally with higher weights.",
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


def resolve_operator_presets(presets: Sequence[str] | None):
    """Resolve preset names into a list of operators and weight mapping."""
    if not presets:
        return None, {}
    combined_weights: dict[str, float] = {}
    for preset in presets:
        key = preset.lower()
        config = OPERATOR_PRESETS.get(key)
        if config is None:
            raise ValueError(
                f"Unknown operator preset '{preset}'. Available: {', '.join(sorted(OPERATOR_PRESETS))}"
            )
        for name, weight in config.items():
            combined_weights[name.lower()] = float(weight)
    operators = [name for name, weight in combined_weights.items() if weight > 0]
    return operators or None, combined_weights


def operator_preset_help() -> str:
    return ", ".join(
        f"{name} ({OPERATOR_PRESET_DESCRIPTIONS.get(name, '').strip()})".strip()
        for name in sorted(OPERATOR_PRESETS)
    )


def format_operator_presets() -> str:
    lines = []
    for name in sorted(OPERATOR_PRESETS):
        weights = ", ".join(f"{op}={val}" for op, val in OPERATOR_PRESETS[name].items())
        desc = OPERATOR_PRESET_DESCRIPTIONS.get(name, "")
        lines.append(f"{name}: {weights}" + (f" — {desc}" if desc else ""))
    return "\n".join(lines)


__all__ = [
    "parse_operator_weights",
    "resolve_operator_presets",
    "operator_preset_help",
    "format_operator_presets",
    "OPERATOR_PRESETS",
]
