"""MIP tooling for FHOPS.

``solve_mip`` and ``build_model`` are deprecated since 1.0.1 (#127): ``solve_mip`` delegates to the
operational MILP (:mod:`fhops.model.milp`) and ``build_model`` builds the legacy day-level MIP,
which is infeasible for scenarios with loader roles. Both emit
:class:`~fhops.optimization.mip.deprecation.LegacyMipDeprecationWarning`.
"""

from .builder import build_model
from .deprecation import LegacyMipDeprecationWarning
from .highs_driver import solve_mip

__all__ = ["LegacyMipDeprecationWarning", "build_model", "solve_mip"]
