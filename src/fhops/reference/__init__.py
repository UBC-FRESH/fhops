"""Reference data loaders."""

from .arnvik_appendix5 import Appendix5Stand, get_appendix5_profile, load_appendix5_stands
from .tr119_partial_cut import Tr119Treatment, get_tr119_treatment, load_tr119_treatments
from .adv2n21 import (
    ADV2N21StandSnapshot,
    ADV2N21Treatment,
    adv2n21_cost_base_year,
    get_adv2n21_treatment,
    load_adv2n21_treatments,
)
from .unbc_hoe_chucking import (
    UNBCHoeChuckingScenario,
    UNBCProcessingCostScenario,
    UNBCConstructionCost,
    load_unbc_hoe_chucking_data,
    load_unbc_processing_costs,
    load_unbc_construction_costs,
)
from .tr28_subgrade import (
    TR28CostEstimate,
    TR28Machine,
    estimate_tr28_road_cost,
    get_tr28_source_metadata,
    load_tr28_machines,
    tr28_currency_year,
)
from .tn98_handfalling import (
    TN98HandfallingDataset,
    TN98Regression,
    TN98DiameterRecord,
    load_tn98_dataset,
)
from .tn82_ft180 import TN82Dataset, TN82Machine, TN82AreaSummary, load_tn82_dataset
from .adv6n25_helicopters import (
    ADV6N25Dataset,
    ADV6N25Helicopter,
    load_adv6n25_dataset,
)
from .fncy12_tmy45 import (
    Fncy12Dataset,
    Fncy12MonthlyProductivity,
    load_fncy12_dataset,
)
from .helicopter_fpinnovations import (
    HelicopterFPInnovationsDataset,
    HelicopterOperation,
    HelicopterSource,
    get_default_helicopter_operation,
    get_helicopter_operation,
    load_helicopter_fpinnovations_dataset,
)
from .soil_protection import (
    SoilProfile,
    get_soil_profile,
    get_soil_profiles,
    load_soil_profiles,
)
from .partial_cut_profiles import (
    PartialCutProfile,
    get_partial_cut_profile,
    load_partial_cut_profiles,
)
from .support_penalties import (
    TractorDriveEfficiency,
    CompactionRisk,
    adv15n3_baseline_drive_id,
    adv15n3_drive_ids,
    get_adv15n3_drive,
    adv4n7_default_risk_id,
    adv4n7_risk_ids,
    get_adv4n7_risk,
)

__all__ = [
    "Appendix5Stand",
    "load_appendix5_stands",
    "get_appendix5_profile",
    "Tr119Treatment",
    "load_tr119_treatments",
    "get_tr119_treatment",
    "ADV2N21StandSnapshot",
    "ADV2N21Treatment",
    "adv2n21_cost_base_year",
    "load_adv2n21_treatments",
    "get_adv2n21_treatment",
    "UNBCHoeChuckingScenario",
    "load_unbc_hoe_chucking_data",
    "UNBCProcessingCostScenario",
    "load_unbc_processing_costs",
    "UNBCConstructionCost",
    "load_unbc_construction_costs",
    "TR28Machine",
    "TR28CostEstimate",
    "load_tr28_machines",
    "get_tr28_source_metadata",
    "estimate_tr28_road_cost",
    "tr28_currency_year",
    "TN98HandfallingDataset",
    "TN98Regression",
    "TN98DiameterRecord",
    "load_tn98_dataset",
    "TN82Dataset",
    "TN82Machine",
    "TN82AreaSummary",
    "load_tn82_dataset",
    "ADV6N25Dataset",
    "ADV6N25Helicopter",
    "load_adv6n25_dataset",
    "Fncy12Dataset",
    "Fncy12MonthlyProductivity",
    "load_fncy12_dataset",
    "HelicopterFPInnovationsDataset",
    "HelicopterOperation",
    "HelicopterSource",
    "load_helicopter_fpinnovations_dataset",
    "get_helicopter_operation",
    "get_default_helicopter_operation",
    "SoilProfile",
    "load_soil_profiles",
    "get_soil_profile",
    "get_soil_profiles",
    "PartialCutProfile",
    "load_partial_cut_profiles",
    "get_partial_cut_profile",
    "TractorDriveEfficiency",
    "CompactionRisk",
    "adv15n3_baseline_drive_id",
    "adv15n3_drive_ids",
    "get_adv15n3_drive",
    "adv4n7_default_risk_id",
    "adv4n7_risk_ids",
    "get_adv4n7_risk",
]
