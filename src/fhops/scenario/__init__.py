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
from .hydrology import (
    FemicHydrologyArtifact,
    FemicHydrologyBundle,
    FemicHydrologyError,
    FemicHydrologyReadiness,
    FemicHydrologyValidation,
    assess_femic_hydrology_readiness,
    load_femic_hydrology_bundle,
    read_femic_hydrology_domain,
    read_femic_hydrology_ledger,
    validate_femic_hydrology_bundle,
)
from .hydrology import (
    bundle_pin as hydrology_bundle_pin,
)
from .hydrology_mapping import (
    FemicHydrologyMappingError,
    HydrologyCrosswalk,
    HydrologyCrosswalkMetadata,
    HydrologyCrosswalkRow,
    HydrologyMapping,
    HydrologyMappingRow,
    load_hydrology_crosswalk,
    map_femic_hydrology_to_scenario,
    write_hydrology_mapping,
)
from .hydrology_registration import (
    FemicHydrologyRegistrationError,
    register_femic_hydrology_bundle,
)
from .hydrology_registration import (
    RegistrationResult as HydrologyRegistrationResult,
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
from .lidar_mapping import MappingResult, map_femic_lidar_to_scenario
from .lidar_operability import (
    BlockOperability,
    OperabilityRules,
    assess_block_operability,
    assess_scenario_operability,
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
    "BlockOperability",
    "MappingResult",
    "OperabilityRules",
    "assess_block_operability",
    "assess_scenario_operability",
    "map_femic_lidar_to_scenario",
    "RegistrationResult",
    "register_femic_lidar_bundle",
    "FemicHydrologyArtifact",
    "FemicHydrologyBundle",
    "FemicHydrologyError",
    "FemicHydrologyReadiness",
    "FemicHydrologyValidation",
    "assess_femic_hydrology_readiness",
    "hydrology_bundle_pin",
    "load_femic_hydrology_bundle",
    "read_femic_hydrology_domain",
    "read_femic_hydrology_ledger",
    "validate_femic_hydrology_bundle",
    "FemicHydrologyRegistrationError",
    "HydrologyRegistrationResult",
    "register_femic_hydrology_bundle",
    "FemicHydrologyMappingError",
    "HydrologyCrosswalk",
    "HydrologyCrosswalkMetadata",
    "HydrologyCrosswalkRow",
    "HydrologyMapping",
    "HydrologyMappingRow",
    "load_hydrology_crosswalk",
    "map_femic_hydrology_to_scenario",
    "write_hydrology_mapping",
]
