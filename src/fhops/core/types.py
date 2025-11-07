"""Backwards compatibility shims for legacy imports.

Prefer importing from ``fhops.scenario.contract`` and ``fhops.scenario.io``.
"""

from __future__ import annotations

from warnings import warn

from fhops.scenario.contract.models import (  # noqa: F401,F403
    Block,
    CalendarEntry,
    Day,
    Landing,
    Machine,
    Problem,
    ProductionRate,
    Scenario,
)

warn(
    "fhops.core.types is deprecated; import from fhops.scenario.contract.models instead",
    DeprecationWarning,
    stacklevel=1,
)

__all__ = [
    "Day",
    "Block",
    "Machine",
    "Landing",
    "CalendarEntry",
    "ProductionRate",
    "Scenario",
    "Problem",
]
