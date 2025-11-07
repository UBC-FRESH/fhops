"""Deprecated import path; use ``fhops.evaluation.metrics.kpis``."""

from __future__ import annotations

from warnings import warn

from fhops.evaluation.metrics.kpis import compute_kpis  # noqa: F401

warn(
    "fhops.eval.kpis is deprecated; import from fhops.evaluation.metrics.kpis",
    DeprecationWarning,
    stacklevel=1,
)

__all__ = ["compute_kpis"]
