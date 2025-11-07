"""Deprecated import path; use ``fhops.optimization.mip.builder`` instead."""

from __future__ import annotations

from warnings import warn

from fhops.optimization.mip.builder import build_model  # noqa: F401

warn(
    "fhops.model.pyomo_builder is deprecated; import from fhops.optimization.mip.builder",
    DeprecationWarning,
    stacklevel=1,
)

__all__ = ["build_model"]
