"""Scenario reference to an individual-tree inventory.

The inventory validator lives in :mod:`fhops.tree_inventory`; this model records
the stable reference and provenance that a planner keeps beside a scenario. The
section is optional, so scenarios without tree-scale data remain valid.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = ["TreeInventoryRef"]

TreeInventoryReviewStatus = Literal[
    "not_reviewed",
    "review_pending",
    "reviewed",
    "reviewed_with_conditions",
]
_CHECKSUM = re.compile(r"^[0-9a-fA-F]{64}$")


class TreeInventoryRef(BaseModel):
    """A scenario-level reference to one validated tree inventory.

    The inventory is referenced, not copied. ``inventory_sha256`` and
    ``metadata_sha256`` pin the CSV and metadata bytes; the remaining fields
    preserve identity, CRS, review, and producer provenance.

    Attributes
    ----------
    inventory_id : str
        Stable inventory identifier from the metadata.
    inventory_sha256 : str
        SHA-256 digest of the inventory CSV.
    metadata_sha256 : str
        SHA-256 digest of the metadata JSON.
    inventory_path : str
        Inventory CSV path, relative to the scenario when possible.
    metadata_path : str
        Metadata JSON path, relative to the scenario when possible.
    crs : str
        Inventory coordinate reference system.
    review_status : str
        ``not_reviewed``, ``review_pending``, ``reviewed``, or
        ``reviewed_with_conditions``.
    reviewed_by : str | None
        Reviewer identifier when reviewed.
    source_id : str
        Producer source identifier.
    producer : str
        Producer name.
    method : str
        Detection/segmentation method.
    tree_count : int
        Number of tree records.
    block_ids : list[str]
        Declared block memberships.
    caveats : list[str]
        Inventory caveats.
    """

    inventory_id: str = Field(min_length=1)
    inventory_sha256: str
    metadata_sha256: str
    inventory_path: str = Field(min_length=1)
    metadata_path: str = Field(min_length=1)
    crs: str = Field(min_length=1)
    review_status: TreeInventoryReviewStatus = "not_reviewed"
    reviewed_by: str | None = None
    source_id: str = Field(min_length=1)
    producer: str = Field(min_length=1)
    method: str = Field(min_length=1)
    tree_count: int = Field(ge=0)
    block_ids: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)

    @field_validator(
        "inventory_id", "inventory_path", "metadata_path", "crs", "source_id", "producer", "method"
    )
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("TreeInventoryRef fields must be non-empty")
        return value.strip()

    @field_validator("inventory_sha256", "metadata_sha256")
    @classmethod
    def _checksum(cls, value: str) -> str:
        if not _CHECKSUM.fullmatch(value):
            raise ValueError("TreeInventoryRef checksums must be SHA-256 digests")
        return value.lower()

    @model_validator(mode="after")
    def _review_and_blocks(self) -> TreeInventoryRef:
        if self.review_status in {"reviewed", "reviewed_with_conditions"} and not self.reviewed_by:
            raise ValueError("Reviewed TreeInventoryRef requires reviewed_by")
        if len(self.block_ids) != len(set(self.block_ids)):
            raise ValueError("TreeInventoryRef block_ids must be unique")
        return self
