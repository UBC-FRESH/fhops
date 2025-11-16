"""Productivity model registry (sourced from Arnvik 2024 and others)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductivityModel:
    machine_type: str
    system: str
    region: str
    publication: str
    predictors: Sequence[str]
    coefficients: Mapping[str, float]
    intercept: float | None
    form: str
    r_squared: float | None
    notes: str | None = None
    reference: Mapping[str, str] | None = None


class ProductivityRegistry:
    def __init__(self) -> None:
        self._models: list[ProductivityModel] = []

    def add(self, model: ProductivityModel) -> None:
        self._models.append(model)

    def by_machine(self, machine_type: str) -> list[ProductivityModel]:
        return [model for model in self._models if model.machine_type == machine_type]

    def all(self) -> Sequence[ProductivityModel]:
        return tuple(self._models)


registry = ProductivityRegistry()


__all__ = ["ProductivityModel", "ProductivityRegistry", "registry"]
