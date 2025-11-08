"""Deprecated import path; use ``fhops.optimization.heuristics.sa``."""

from __future__ import annotations

from warnings import warn

from fhops.optimization.heuristics.sa import Schedule, solve_sa  # noqa: F401

warn(
    "fhops.solve.heuristics.sa is deprecated; import from fhops.optimization.heuristics",
    DeprecationWarning,
    stacklevel=1,
)

__all__ = ["Schedule", "solve_sa"]
