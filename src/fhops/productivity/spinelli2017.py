"""Productivity helper derived from Spinelli et al. (2017) grapple yarder study."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GrappleYarderInputs:
    """Input bundle for the Spinelli et al. (2017) regression."""

    piece_volume_m3: float
    pieces_per_load: float
    line_length_m: float
    stacking_distance_m: float
    yarder_type: str = "heavy"  # "heavy" or "medium"
    is_top_team: bool = False


def estimate_grapple_yarder_productivity(inputs: GrappleYarderInputs) -> float:
    """Return net productivity (m^3/PMH) using Spinelli et al. (2017) Table 5 regression.

    References:
        Spinelli, R., A. McEwan, and R. Engelbrecht (2017).
        "A Robust Productivity Model for Grapple Yarding in Fast-Growing Tree Plantations."
        Forests 8(396). DOI:10.3390/ f8100396.

    The regression (Table 5) is:

        P = a + b*Vol + c*N + d*Line + e*Stack +
            f*(Medium * Vol) + g*(Top * Vol) + h*(Top)

    where P is net productivity (m^3 per productive machine hour),
    Vol is mean piece volume (m^3),
    N is number of pieces per load,
    Line is line length (m),
    Stack is stacking distance (m),
    Medium is an indicator variable (1 for medium yarders, 0 otherwise),
    and Top is an indicator for "top teams".
    """

    vol = inputs.piece_volume_m3
    if vol <= 0:
        raise ValueError("piece_volume_m3 must be > 0")
    if inputs.pieces_per_load <= 0:
        raise ValueError("pieces_per_load must be > 0")
    if inputs.line_length_m <= 0 or inputs.stacking_distance_m < 0:
        raise ValueError("Line length must be > 0 and stacking distance >= 0")

    yarder = inputs.yarder_type.lower()
    if yarder not in {"heavy", "medium"}:
        raise ValueError("yarder_type must be 'heavy' or 'medium'")
    medium = 1 if yarder == "medium" else 0
    top = 1 if inputs.is_top_team else 0

    productivity = (
        -50.515
        + 132.724 * vol
        + 14.222 * inputs.pieces_per_load
        - 0.127 * inputs.line_length_m
        - 0.124 * inputs.stacking_distance_m
        - 25.143 * medium * vol
        - 36.148 * top * vol
        + 29.559 * top
    )

    return max(productivity, 0.0)


__all__ = [
    "GrappleYarderInputs",
    "estimate_grapple_yarder_productivity",
]
