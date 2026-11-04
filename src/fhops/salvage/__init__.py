"""Salvage shelf-life and degradation helpers.

The package exposes published decay curves and a read-only report consumer. It
does not contain salvage scheduling logic or solver changes.
"""

from fhops.salvage.degradation import (
    DEFAULT_CURVE_ID,
    DecayCurve,
    DecayCurveLibrary,
    DecayCurvePoint,
    DecayCurveSource,
    ProductWindow,
    get_decay_curve,
    load_decay_library,
)
from fhops.salvage.report import (
    REQUIRED_STORAGE_COLUMNS,
    SalvageReport,
    build_salvage_report,
    write_salvage_report,
)

__all__ = [
    "DEFAULT_CURVE_ID",
    "REQUIRED_STORAGE_COLUMNS",
    "DecayCurve",
    "DecayCurveLibrary",
    "DecayCurvePoint",
    "DecayCurveSource",
    "ProductWindow",
    "SalvageReport",
    "build_salvage_report",
    "get_decay_curve",
    "load_decay_library",
    "write_salvage_report",
]
