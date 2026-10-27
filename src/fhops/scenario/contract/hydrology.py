"""Scenario pin records for FEMIC hydrology response bundles.

The bundle validator lives in :mod:`fhops.scenario.hydrology`; these models
record the stable pin and readiness evidence that a planner keeps beside a
scenario. The section is optional, so scenarios without hydrology remain valid.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = [
    "HydrologyArtifactPin",
    "HydrologyBundleRef",
    "HydrologyReadinessStatus",
]

HydrologyReadinessStatus = Literal[
    "not_available",
    "provisional",
    "conditionally_ready",
    "ready",
    "blocked",
]
_CHECKSUM = re.compile(r"^[0-9a-fA-F]{64}$")


class HydrologyArtifactPin(BaseModel):
    """One artifact recorded in a hydrology bundle pin."""

    role: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str

    @field_validator("role", "relative_path", "schema_version", "media_type")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("HydrologyArtifactPin fields must be non-empty")
        return value.strip()

    @field_validator("sha256")
    @classmethod
    def _checksum(cls, value: str) -> str:
        if not _CHECKSUM.fullmatch(value):
            raise ValueError("HydrologyArtifactPin.sha256 must be a SHA-256 digest")
        return value.lower()


class HydrologyBundleRef(BaseModel):
    """A scenario-level pin to one FEMIC hydrology bundle version.

    The fields mirror :func:`fhops.scenario.hydrology.bundle_pin`. The pin is a
    reference, not a copy of the bundle.
    """

    bundle_id: str = Field(min_length=1)
    bundle_version: str = Field(min_length=1)
    manifest_sha256: str
    domain_id: str = Field(min_length=1)
    ledger_id: str = Field(min_length=1)
    response_surface_id: str = Field(min_length=1)
    manifest_path: str | None = None
    readiness_status: HydrologyReadinessStatus = "not_available"
    readiness_evidence_sha256: str | None = None
    artifacts: list[HydrologyArtifactPin] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    consumer_contract: dict[str, object] = Field(default_factory=dict)

    @field_validator(
        "bundle_id",
        "bundle_version",
        "domain_id",
        "ledger_id",
        "response_surface_id",
    )
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("HydrologyBundleRef identifiers must be non-empty")
        return value.strip()

    @field_validator("manifest_sha256")
    @classmethod
    def _manifest_checksum(cls, value: str) -> str:
        if not _CHECKSUM.fullmatch(value):
            raise ValueError("HydrologyBundleRef.manifest_sha256 must be a SHA-256 digest")
        return value.lower()

    @field_validator("readiness_evidence_sha256")
    @classmethod
    def _evidence_checksum(cls, value: str | None) -> str | None:
        if value is not None and not _CHECKSUM.fullmatch(value):
            raise ValueError(
                "HydrologyBundleRef.readiness_evidence_sha256 must be a SHA-256 digest"
            )
        return value.lower() if value else None

    @model_validator(mode="after")
    def _unique_roles(self) -> HydrologyBundleRef:
        roles = [artifact.role for artifact in self.artifacts]
        if len(roles) != len(set(roles)):
            raise ValueError("HydrologyBundleRef artifact roles must be unique")
        return self
