"""Placeholder for harvest system sequencing constraints."""

from __future__ import annotations

import pyomo.environ as pyo

from fhops.scenario.contract import Problem


def apply_system_sequencing_constraints(model: pyo.ConcreteModel, pb: Problem) -> None:
    """Attach sequencing constraints once system definitions are available."""
    # TODO: Implement precedence constraints based on system registry when available.
    return None


__all__ = ["apply_system_sequencing_constraints"]
