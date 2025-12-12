"""CLI helper utilities for FHOPS."""

from __future__ import annotations

from collections.abc import Sequence

import typer

OPERATOR_PRESETS: dict[str, dict[str, float]] = {
    "balanced": {
        "swap": 1.0,
        "move": 1.0,
        "block_insertion": 0.6,
        "cross_exchange": 0.6,
        "mobilisation_shake": 0.2,
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
    "explore": {
        "swap": 1.0,
        "move": 1.0,
        "block_insertion": 0.6,
        "cross_exchange": 0.6,
        "mobilisation_shake": 0.2,
    },
    "mobilisation": {
        "swap": 0.8,
        "move": 0.8,
        "block_insertion": 0.4,
        "cross_exchange": 0.4,
        "mobilisation_shake": 1.2,
    },
    "stabilise": {
        "swap": 0.5,
        "move": 1.5,
        "block_insertion": 0.2,
        "cross_exchange": 0.2,
        "mobilisation_shake": 0.0,
    },
}

_OBJECTIVE_WEIGHT_ALIASES: dict[str, str] = {
    "production": "production",
    "prod": "production",
    "mobilisation": "mobilisation",
    "mobilization": "mobilisation",
    "mobilize": "mobilisation",
    "transitions": "transitions",
    "transition": "transitions",
    "landing_surplus": "landing_surplus",
    "landing-slack": "landing_surplus",
    "landing": "landing_surplus",
}

OPERATOR_PRESET_DESCRIPTIONS: dict[str, str] = {
    "balanced": "Default mix enables block insertion/cross-exchange with a moderate mobilisation shake.",
    "swap-only": "Disable move and rely solely on swap moves.",
    "move-only": "Disable swap and allow only move operations.",
    "swap-heavy": "Bias toward swap moves while keeping move available.",
    "diversify": "Encourage both operators equally with higher weights.",
    "explore": "Activate block insertion/cross exchange with moderate mobilisation shake to diversify neighbourhood search.",
    "mobilisation": "Emphasise mobilisation_shake to escape local minima in distance-constrained scenarios.",
    "stabilise": "Favour move operations to consolidate plans while keeping advanced operators at low weights.",
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


def parse_objective_weight_overrides(weight_args: Sequence[str] | None) -> dict[str, float]:
    """Parse objective weight overrides in ``name=value`` format."""

    overrides: dict[str, float] = {}
    if not weight_args:
        return overrides

    valid = {"production", "mobilisation", "transitions", "landing_surplus"}
    for arg in weight_args:
        if "=" not in arg:
            raise ValueError(f"Objective weight must be in name=value format (got '{arg}')")
        raw_name, raw_value = arg.split("=", 1)
        key = raw_name.strip().lower()
        canonical = _OBJECTIVE_WEIGHT_ALIASES.get(key)
        if canonical is None or canonical not in valid:
            allowed = ", ".join(sorted(valid))
            raise ValueError(f"Unknown objective weight '{raw_name}'. Allowed keys: {allowed}.")
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise ValueError(
                f"Objective weight for '{raw_name}' must be numeric (got '{raw_value}')"
            ) from exc
        overrides[canonical] = value
    return overrides


def coerce_solver_option_value(raw_value: str) -> object:
    """Attempt to coerce solver option values into bool/int/float; fallback to string."""

    value = raw_value.strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def parse_solver_options(option_args: Sequence[str] | None) -> dict[str, object]:
    """Parse ``name=value`` solver options supplied via the CLI."""

    parsed: dict[str, object] = {}
    if not option_args:
        return parsed
    for entry in option_args:
        if "=" not in entry:
            raise typer.BadParameter(f"Solver options must be key=value (got '{entry}')")
        key, raw_value = entry.split("=", 1)
        key = key.strip()
        if not key:
            raise typer.BadParameter(f"Solver option missing name in '{entry}'")
        parsed[key] = coerce_solver_option_value(raw_value)
    return parsed


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
    """Return a short string describing available operator presets for Typer help."""

    return ", ".join(
        f"{name} ({OPERATOR_PRESET_DESCRIPTIONS.get(name, '').strip()})".strip()
        for name in sorted(OPERATOR_PRESETS)
    )


def format_operator_presets() -> str:
    """Format the operator preset table used in CLI help/README snippets."""

    lines = []
    for name in sorted(OPERATOR_PRESETS):
        weights = ", ".join(f"{op}={val}" for op, val in OPERATOR_PRESETS[name].items())
        desc = OPERATOR_PRESET_DESCRIPTIONS.get(name, "")
        lines.append(f"{name}: {weights}" + (f" — {desc}" if desc else ""))
    return "\n".join(lines)


__all__ = [
    "parse_operator_weights",
    "parse_objective_weight_overrides",
    "resolve_operator_presets",
    "operator_preset_help",
    "format_operator_presets",
    "OPERATOR_PRESETS",
    "parse_solver_options",
    "coerce_solver_option_value",
]
