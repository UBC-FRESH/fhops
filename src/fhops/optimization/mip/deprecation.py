"""Deprecation notices for the legacy day-level MIP (FHOPS 1.0.1, #127).

The legacy builder (:func:`fhops.optimization.mip.builder.build_model`) is infeasible for every
scenario whose harvest system has a loader role with machines: its loader-buffer constraint
``Σ_{≤s} prod_loader ≤ Σ_{<s} prod_prereq − batch`` cannot hold in the first shift (found in #124;
the bundled tiny7, small21 and med42 examples are proven infeasible by HiGHS, also at v1.0.0).
The canonical, published formulation is the operational MILP
(:mod:`fhops.model.milp`, ``fhops solve-mip-operational``); ``solve_mip`` / ``fhops solve-mip``
delegate to it and the builder is kept importable only for API compatibility.
"""

from __future__ import annotations

__all__ = [
    "LEGACY_BUILDER_MESSAGE",
    "LEGACY_SOLVE_MIP_MESSAGE",
    "LegacyMipDeprecationWarning",
]


class LegacyMipDeprecationWarning(DeprecationWarning):
    """Warning emitted by the deprecated legacy MIP entry points.

    Emitted (``stacklevel=2``) by :func:`fhops.optimization.mip.solve_mip` and
    :func:`fhops.optimization.mip.builder.build_model`. It subclasses :class:`DeprecationWarning`, so
    Python shows it for calls made from ``__main__`` (scripts, notebooks) and under test runners;
    the ``fhops solve-mip`` CLI prints its own one-line notice instead.
    """


LEGACY_SOLVE_MIP_MESSAGE = (
    "fhops.optimization.mip.solve_mip / `fhops solve-mip` are deprecated and delegate to the "
    "operational MILP (fhops.model.milp.driver.solve_operational_milp / "
    "`fhops solve-mip-operational`); the legacy day-level MIP is infeasible for scenarios with "
    "loader roles. They will be removed in a future release."
)

LEGACY_BUILDER_MESSAGE = (
    "fhops.optimization.mip.builder.build_model (legacy day-level MIP) is deprecated: it is "
    "infeasible for scenarios with loader roles and is no longer used by any solver. Use the "
    "operational MILP (fhops.model.milp.operational.build_operational_model / "
    "fhops.model.milp.driver.solve_operational_milp)."
)
