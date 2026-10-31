"""Product price and log-value helpers for the serious game."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = ["PriceSchedule"]


@dataclass(frozen=True, slots=True)
class PriceSchedule:
    """Level-owned product and residual-asset prices."""

    products: Mapping[str, float]
    mobilisation_cost: float = 0.0
    road_extension_cost_per_m: float = 0.0
    residual_asset_per_m3: float = 0.0
    currency: str = "CAD"
    note: str = ""

    def __post_init__(self) -> None:
        if not self.products:
            raise ValueError("PriceSchedule.products must not be empty.")
        for name, value in self.products.items():
            if not name or value < 0:
                raise ValueError(f"Invalid product price {name!r}: {value!r}")
        for name, value in (
            ("mobilisation_cost", self.mobilisation_cost),
            ("road_extension_cost_per_m", self.road_extension_cost_per_m),
            ("residual_asset_per_m3", self.residual_asset_per_m3),
        ):
            if value < 0:
                raise ValueError(f"{name} must be non-negative.")

    @classmethod
    def from_path(cls, path: str | Path) -> PriceSchedule:
        """Load a price deck from YAML and validate its schema."""
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("Price deck must be a mapping.")
        if payload.get("schema_version") != "fhops.game.prices.v1":
            raise ValueError("Unsupported price-deck schema.")
        products = payload.get("products")
        if not isinstance(products, Mapping):
            raise ValueError("Price deck products must be a mapping.")
        return cls(
            products={str(key): float(value) for key, value in products.items()},
            mobilisation_cost=float(payload.get("mobilisation_cost", 0.0)),
            road_extension_cost_per_m=float(payload.get("road_extension_cost_per_m", 0.0)),
            residual_asset_per_m3=float(payload.get("residual_asset_per_m3", 0.0)),
            currency=str(payload.get("currency", "CAD")),
            note=str(payload.get("note", "")),
        )

    def log_product(self, product: str, log_index: int) -> str:
        """Map a FHOPS stem log to a priced product class."""
        if product == "sawlog":
            return "sawlog_butt" if log_index == 1 else "sawlog_upper"
        return "pulp" if product == "pulp" else product

    def value_logs(self, logs: Iterable[Any]) -> dict[str, Any]:
        """Return product volumes, product values, and total gross log value."""
        volumes: dict[str, float] = {}
        values: dict[str, float] = {}
        for log in logs:
            product = self.log_product(str(log.product), int(log.log_index))
            if product not in self.products:
                raise KeyError(f"No price for log product {product!r}")
            volume = float(log.volume_m3)
            volumes[product] = volumes.get(product, 0.0) + volume
            values[product] = values.get(product, 0.0) + volume * self.products[product]
        return {
            "product_volume_m3": volumes,
            "product_value": values,
            "gross_log_value": sum(values.values()),
        }

    def residual_asset_value(self, merchantable_volume_m3: float) -> float:
        """Value the residual stand asset used in damage accounting."""
        if merchantable_volume_m3 < 0:
            raise ValueError("residual merchantable volume must be non-negative.")
        return merchantable_volume_m3 * self.residual_asset_per_m3

    def road_extension_cost(self, extension_m: float) -> float:
        """Return the trunk-road extension charge."""
        if extension_m < 0:
            raise ValueError("road extension length must be non-negative.")
        return extension_m * self.road_extension_cost_per_m
