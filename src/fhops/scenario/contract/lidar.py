"""Scenario pin and support rows for FEMIC LidarBC bundles.

The bundle loader lives in :mod:`fhops.scenario.lidar`; these models only record the stable pin and
the aggregated support evidence that a planner wants to keep beside a scenario. Every field is
optional at the scenario level.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

__all__ = ["LidarProductPin", "LidarProductRef", "LidarSupport", "LidarSupportUnit"]

LidarSupportUnit = Literal["block", "landing", "road"]
AggregationMethod = Literal["mean", "area_weighted_mean", "median", "minimum", "maximum", "p95"]
_CHECKSUM = re.compile(r"^[0-9a-fA-F]{64}$")


class LidarProductPin(BaseModel):
    """One product file recorded in a scenario bundle pin."""

    product: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    sha256: str
    crs: str = Field(min_length=1)
    resolution_m: float | None = Field(default=None, gt=0)
    vertical_datum: str = Field(min_length=1)
    source_tile_ids: list[str] = Field(default_factory=list)

    @field_validator("sha256")
    @classmethod
    def _checksum(cls, value: str) -> str:
        if not _CHECKSUM.fullmatch(value):
            raise ValueError("LidarProductPin.sha256 must be a SHA-256 digest")
        return value.lower()


class LidarProductRef(BaseModel):
    """A scenario-level pin to one FEMIC bundle version.

    The fields mirror :func:`fhops.scenario.lidar.bundle_pin`; ``manifest_sha256`` is the digest of
    the bundle manifest, not of an individual raster.
    """

    bundle_id: str = Field(min_length=1)
    bundle_version: str = Field(min_length=1)
    manifest_sha256: str | None = None
    licence_id: str | None = None
    manifest_path: str | None = None
    crs: str | None = None
    aoi_bbox: tuple[float, float, float, float] | None = None
    selection: dict[str, object] | None = None
    products: list[LidarProductPin] | None = None

    @field_validator("bundle_id", "bundle_version")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("LidarProductRef bundle id/version must be non-empty")
        return value.strip()

    @field_validator("manifest_sha256")
    @classmethod
    def _checksum(cls, value: str | None) -> str | None:
        if value is not None and not _CHECKSUM.fullmatch(value):
            raise ValueError("LidarProductRef.manifest_sha256 must be a SHA-256 digest")
        return value.lower() if value else None

    @model_validator(mode="after")
    def _aoi_and_products(self) -> LidarProductRef:
        if self.aoi_bbox is not None:
            west, south, east, north = self.aoi_bbox
            if east <= west or north <= south:
                raise ValueError("LidarProductRef.aoi_bbox must be west,south,east,north")
        if self.products is not None:
            names = [product.product for product in self.products]
            if len(names) != len(set(names)):
                raise ValueError("LidarProductRef.products names must be unique")
        return self


class LidarSupport(BaseModel):
    """Aggregated LidarBC evidence for one block, landing, or road.

    The values are the output of a FEMIC raster summary (for example
    :func:`fhops.scenario.lidar.summarize_femic_lidar_for_polygons`). Native resolution, product
    name, aggregation, valid-pixel count, and support footprint preserve how the summary was made.
    """

    support_unit: LidarSupportUnit
    support_id: str = Field(min_length=1)
    bundle_id: str = Field(min_length=1)
    bundle_version: str = Field(min_length=1)
    product: str = Field(min_length=1)
    aggregation: AggregationMethod = "area_weighted_mean"
    native_resolution_m: float = Field(gt=0)
    support_area_m2: float | None = Field(default=None, ge=0)
    valid_pixels: int | None = Field(default=None, ge=0)
    slope_percent: float | None = Field(default=None, ge=0)
    aspect_degrees: float | None = Field(default=None, ge=0, le=360)
    roughness_m: float | None = Field(default=None, ge=0)
    canopy_cover_percent: float | None = Field(default=None, ge=0, le=100)
    canopy_height_m: float | None = Field(default=None, ge=0)
    vertical_structure_index: float | None = Field(default=None, ge=0)
    vertical_structure_class: str | None = None
    provenance: str | None = None

    @field_validator("support_id", "bundle_id", "bundle_version", "product")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("LidarSupport ids/product must be non-empty")
        return value.strip()
