"""CLI helper utilities for FHOPS."""

from __future__ import annotations

from typing import Sequence


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


__all__ = ["parse_operator_weights"]
