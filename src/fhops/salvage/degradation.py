"""Published salvage degradation and product shelf-life curves.

Why this module exists
----------------------
FHOPS models the salvage machine chain and records a
:class:`~fhops.scenario.contract.models.SalvageProcessingMode`, but it does not
model the biological clock that changes what can be recovered from dead wood.
This module is the shared, read-only contract for that clock. It separates three
things that are often mixed together:

* a **retention curve** (how much recoverable volume remains at a given age);
* a **product window** (which products are still plausible at that age); and
* a **source record** (where the numbers came from and what they do not cover).

The first curve is the published mixed-conifer fire-killed net-volume retention
series in Prestemon and Holmes (2008), section 4.2.6. The product windows are the
Canadian boreal shelf-life statements in Barrette et al. (2015). No coefficient
in this module is fitted, extrapolated, or invented by FHOPS. A future BC or
species-specific curve can be added as a new data entry without changing code.

The module deliberately returns fractions and product names, not prices or
objective terms. Callers that need money must supply their own price and label
it as an assumption.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, model_validator

from fhops.resources import data_path

__all__ = [
    "DEFAULT_CURVE_ID",
    "DecayCurve",
    "DecayCurveLibrary",
    "DecayCurvePoint",
    "DecayCurveSource",
    "ProductWindow",
    "get_decay_curve",
    "load_decay_library",
]

#: Default curve used by the salvage report consumer.
DEFAULT_CURVE_ID = "pnw_fire_killed_mixed_conifer"
#: Expected schema identifier in the package data file.
SCHEMA_VERSION = "salvage.decay.v1"
#: Package-data path, relative to the FHOPS ``data/`` root.
DEFAULT_LIBRARY_PARTS = ("reference", "degradation", "salvage_decay.v1.json")


class DecayCurvePoint(BaseModel):
    """One published age/retention pair.

    Attributes
    ----------
    age_years:
        Age since fire or tree death, in years. Must be non-negative.
    retention_fraction:
        Recoverable volume divided by pre-disturbance green volume. Must lie in
        ``[0, 1]``.
    """

    age_years: float = Field(ge=0.0)
    retention_fraction: float = Field(ge=0.0, le=1.0)


class DecayCurveSource(BaseModel):
    """Provenance and applicability boundary for a published curve or window.

    Attributes
    ----------
    citation:
        Human-readable citation, including the section or table when available.
    url:
        Public ``http(s)`` URL for the source document or DOI.
    boundary:
        Plain-language statement of what the source does *not* cover. Consumers
        must surface this text rather than treating the curve as universal.
    retrieved:
        Optional ISO date when the public source was checked.
    """

    citation: str
    url: str
    boundary: str
    retrieved: str | None = None


class DecayCurve(BaseModel):
    """A published retention curve.

    Attributes
    ----------
    curve_id:
        Stable identifier used by the CLI and downstream consumers.
    name:
        Human-readable curve label.
    age_unit:
        Meaning of the age axis, for example ``years_since_fire_or_tree_death``.
    retention_definition:
        What the retention fraction measures (volume, grade, value, and so on).
    points:
        Published age/retention pairs in strictly increasing age order.
    source:
        Citation, URL, and applicability boundary.
    """

    curve_id: str
    name: str
    age_unit: str
    retention_definition: str
    points: list[DecayCurvePoint]
    source: DecayCurveSource

    @model_validator(mode="after")
    def _validate_points(self) -> Self:
        if not self.points:
            raise ValueError(f"decay curve '{self.curve_id}' must contain at least one point")
        ages = [point.age_years for point in self.points]
        if any(current <= previous for previous, current in zip(ages, ages[1:])):
            raise ValueError(
                f"decay curve '{self.curve_id}' points must have strictly increasing ages"
            )
        return self

    def retention_at(self, age_years: float) -> float:
        """Return the retained fraction at ``age_years``.

        Parameters
        ----------
        age_years:
            Age since fire or tree death, in years. Must be non-negative.

        Returns
        -------
        float
            Linear interpolation between the two surrounding published points.
            Ages before the first point use the first fraction; ages after the
            last point use the last fraction. The result is clipped to
            ``[0, 1]`` because the source values are fractions.

        Raises
        ------
        ValueError
            If ``age_years`` is negative or not finite.

        Notes
        -----
        Interpolation is a presentation choice for ages between published years;
        it does not add new coefficients. The published whole-year values are
        returned exactly.
        """

        age = float(age_years)
        if age != age or age in (float("inf"), float("-inf")):
            raise ValueError("age_years must be finite")
        if age < 0.0:
            raise ValueError("age_years must be non-negative")

        first = self.points[0]
        last = self.points[-1]
        if age <= first.age_years:
            return first.retention_fraction
        if age >= last.age_years:
            return last.retention_fraction

        for left, right in zip(self.points, self.points[1:]):
            if left.age_years <= age <= right.age_years:
                span = right.age_years - left.age_years
                if span <= 0.0:  # pragma: no cover - validator forbids duplicates
                    return right.retention_fraction
                weight = (age - left.age_years) / span
                value = left.retention_fraction + weight * (
                    right.retention_fraction - left.retention_fraction
                )
                return min(1.0, max(0.0, value))

        raise AssertionError("unreachable: age lies outside the point range")  # pragma: no cover


class ProductWindow(BaseModel):
    """An advisory product-eligibility window from a published shelf-life review.

    Attributes
    ----------
    product:
        Product name, for example ``lumber``, ``pulp``, or ``bioenergy``.
    min_years:
        Earliest age at which the product is considered plausible. Defaults to
        zero.
    max_years:
        Latest age at which the product is considered plausible. ``None`` means
        the source gives no upper bound (open-ended).
    note:
        The source statement, paraphrased only enough to fit a table cell.
    source:
        Citation, URL, and applicability boundary.
    """

    product: str
    min_years: float = Field(default=0.0, ge=0.0)
    max_years: float | None = Field(default=None, ge=0.0)
    note: str
    source: DecayCurveSource

    @model_validator(mode="after")
    def _validate_window(self) -> Self:
        if self.max_years is not None and self.max_years < self.min_years:
            raise ValueError(f"product window '{self.product}' has max_years below min_years")
        return self

    def contains(self, age_years: float) -> bool:
        """Return whether ``age_years`` falls inside this advisory window."""

        return age_years >= self.min_years and (
            self.max_years is None or age_years <= self.max_years
        )


class DecayCurveLibrary(BaseModel):
    """The validated contents of the packaged ``salvage.decay.v1`` data file.

    Attributes
    ----------
    schema_version:
        Contract identifier. Must equal :data:`SCHEMA_VERSION`.
    curves:
        Published retention curves, keyed by :attr:`DecayCurve.curve_id`.
    product_windows:
        Advisory product windows from the shelf-life source.
    """

    schema_version: str
    curves: list[DecayCurve]
    product_windows: list[ProductWindow]

    @model_validator(mode="after")
    def _validate_library(self) -> Self:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported salvage decay schema '{self.schema_version}'; "
                f"expected '{SCHEMA_VERSION}'"
            )
        curve_ids = [curve.curve_id for curve in self.curves]
        if len(curve_ids) != len(set(curve_ids)):
            raise ValueError("salvage decay curve ids must be unique")
        products = [window.product for window in self.product_windows]
        if len(products) != len(set(products)):
            raise ValueError("salvage product window names must be unique")
        return self

    def curve(self, curve_id: str) -> DecayCurve:
        """Return one curve by id.

        Parameters
        ----------
        curve_id:
            Identifier of the requested curve.

        Returns
        -------
        DecayCurve
            The matching curve.

        Raises
        ------
        KeyError
            If ``curve_id`` is not present. The message lists available ids.
        """

        for curve in self.curves:
            if curve.curve_id == curve_id:
                return curve
        available = ", ".join(sorted(curve.curve_id for curve in self.curves))
        raise KeyError(f"unknown salvage decay curve '{curve_id}'; available: {available}")

    def eligible_products(self, age_years: float) -> tuple[str, ...]:
        """Return advisory product names for ``age_years``.

        Parameters
        ----------
        age_years:
            Age since fire or tree death, in years. Must be non-negative.

        Returns
        -------
        tuple of str
            Product names whose published windows contain the age, in the order
            declared by the data file. The result may contain more than one
            product because the source windows overlap.

        Raises
        ------
        ValueError
            If ``age_years`` is negative or not finite.
        """

        age = float(age_years)
        if age != age or age in (float("inf"), float("-inf")):
            raise ValueError("age_years must be finite")
        if age < 0.0:
            raise ValueError("age_years must be non-negative")
        return tuple(window.product for window in self.product_windows if window.contains(age))


def load_decay_library(path: str | Path | None = None) -> DecayCurveLibrary:
    """Load and validate the packaged salvage decay library.

    Parameters
    ----------
    path:
        Optional explicit JSON path. ``None`` (default) resolves the packaged
        ``data/reference/degradation/salvage_decay.v1.json`` file through
        :func:`fhops.resources.data_path`.

    Returns
    -------
    DecayCurveLibrary
        Validated curve and product-window library.

    Raises
    ------
    FileNotFoundError
        If the JSON file does not exist.
    pydantic.ValidationError
        If the payload is malformed, out of range, or has duplicate ids.
    json.JSONDecodeError
        If the file is not valid JSON.
    """

    resolved = Path(path) if path is not None else data_path(*DEFAULT_LIBRARY_PARTS)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return DecayCurveLibrary.model_validate(payload)


def get_decay_curve(
    curve_id: str = DEFAULT_CURVE_ID,
    library: DecayCurveLibrary | None = None,
) -> DecayCurve:
    """Return a curve by id from the packaged library or a supplied library.

    Parameters
    ----------
    curve_id:
        Curve identifier. Defaults to :data:`DEFAULT_CURVE_ID`.
    library:
        Optional pre-loaded library. ``None`` loads the packaged data.

    Returns
    -------
    DecayCurve
        The requested curve.

    Raises
    ------
    KeyError
        If the curve id is not present.
    """

    resolved = library or load_decay_library()
    return resolved.curve(curve_id)
