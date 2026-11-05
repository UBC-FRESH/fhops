"""Scenario reference to a FEMIC ground-summary CSV.

The summary reader lives in :mod:`fhops.scenario.lidar_ground_summary`; this model records
the stable reference and checksum that a planner keeps beside a scenario. The section is
optional, so scenarios without ground evidence remain valid.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

__all__ = ["GroundSupportRef", "GroundSummaryIdField"]

GroundSummaryIdField = Literal["block_id", "polygon_id"]
_CHECKSUM = re.compile(r"^[0-9a-fA-F]{64}$")


class GroundSupportRef(BaseModel):
    """A scenario-level reference to one validated FEMIC ground summary.

    The summary is referenced, not copied. ``summary_sha256`` pins the CSV bytes, and
    ``schema_version`` pins the producer contract. The summary path is relative to the
    scenario YAML when possible.

    Attributes
    ----------
    schema_version : str
        Supported FEMIC ground-summary schema.
    summary_path : str
        Ground-summary CSV path, relative to the scenario when possible.
    summary_sha256 : str
        SHA-256 digest of the summary CSV.
    id_field : str
        Block identifier column: ``block_id`` or ``polygon_id``.
    producer : str
        Producer name; defaults to ``femic``.
    caveats : list of str
        Ground-evidence caveats carried into the scenario.
    """

    schema_version: Literal["femic.ground-summary.v1"] = "femic.ground-summary.v1"
    summary_path: str = Field(min_length=1)
    summary_sha256: str
    id_field: GroundSummaryIdField = "block_id"
    producer: str = Field(default="femic", min_length=1)
    caveats: list[str] = Field(default_factory=list)

    @field_validator("summary_path", "producer")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("GroundSupportRef fields must be non-empty")
        return value.strip()

    @field_validator("summary_sha256")
    @classmethod
    def _checksum(cls, value: str) -> str:
        if not _CHECKSUM.fullmatch(value):
            raise ValueError("GroundSupportRef.summary_sha256 must be a SHA-256 digest")
        return value.lower()
