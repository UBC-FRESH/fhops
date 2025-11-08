"""Legacy loaders module.

Prefer importing from ``fhops.scenario.io.loaders``.
"""

from __future__ import annotations

from warnings import warn

from fhops.scenario.contract.models import (  # noqa: F401,F403
    Block,
    CalendarEntry,
    Landing,
    Machine,
    ProductionRate,
    Scenario,
)
from fhops.scenario.io.loaders import load_scenario, read_csv  # noqa: F401

warn(
    "fhops.data.loaders is deprecated; import from fhops.scenario.io.loaders instead",
    DeprecationWarning,
    stacklevel=1,
)

__all__ = [
    "load_scenario",
    "read_csv",
    "Scenario",
    "Block",
    "Machine",
    "Landing",
    "CalendarEntry",
    "ProductionRate",
]
