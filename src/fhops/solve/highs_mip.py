"""Deprecated import path; use ``fhops.optimization.mip.highs_driver``."""

from __future__ import annotations

from warnings import warn

from fhops.optimization.mip.highs_driver import solve_mip  # noqa: F401

warn(
    "fhops.solve.highs_mip is deprecated; import from fhops.optimization.mip.highs_driver",
    DeprecationWarning,
    stacklevel=1,
)

__all__ = ["solve_mip"]
