"""Scenario package exposing contracts, IO helpers, and synthetic generators."""

from .contract import (
    Block,
    CalendarEntry,
    Day,
    Landing,
    LidarProductPin,
    LidarProductRef,
    LidarSupport,
    Machine,
    Problem,
    ProductionRate,
    Scenario,
)
from .io import load_scenario, read_csv
from .lidar import (
    FemicLidarBundle,
    FemicLidarError,
    FemicLidarProduct,
    FemicLidarValidation,
    LidarPolygonSummary,
    bundle_pin,
    load_femic_lidar_bundle,
    summarize_femic_lidar_for_polygons,
    validate_femic_lidar_bundle,
)
from .lidar_registration import RegistrationResult, register_femic_lidar_bundle

__all__ = [
    "Day",
    "Block",
    "Machine",
    "Landing",
    "CalendarEntry",
    "ProductionRate",
    "Scenario",
    "Problem",
    "LidarProductPin",
    "LidarProductRef",
    "LidarSupport",
    "load_scenario",
    "read_csv",
    "FemicLidarBundle",
    "FemicLidarError",
    "FemicLidarProduct",
    "FemicLidarValidation",
    "LidarPolygonSummary",
    "bundle_pin",
    "load_femic_lidar_bundle",
    "summarize_femic_lidar_for_polygons",
    "validate_femic_lidar_bundle",
    "RegistrationResult",
    "register_femic_lidar_bundle",
]
