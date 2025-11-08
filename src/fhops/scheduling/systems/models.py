"""Harvest system registry models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

@dataclass
class SystemJob:
    """A single job in a harvest system sequence."""

    name: str
    machine_role: str
    prerequisites: Sequence[str]


@dataclass
class HarvestSystem:
    """Harvest system definition with ordered jobs."""

    system_id: str
    jobs: Sequence[SystemJob]
    environment: str | None = None


__all__ = ["SystemJob", "HarvestSystem"]
