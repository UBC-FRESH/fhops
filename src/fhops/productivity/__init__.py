"""Productivity helpers (calibrated on BC whole-tree datasets)."""

from .cable_logging import (
    estimate_cable_skidding_productivity_unver_robust,
    estimate_cable_skidding_productivity_unver_robust_profile,
    estimate_cable_skidding_productivity_unver_spss,
    estimate_cable_skidding_productivity_unver_spss_profile,
    estimate_cable_yarder_cycle_time_tr127_minutes,
    estimate_cable_yarder_productivity_lee2018_downhill,
    estimate_cable_yarder_productivity_lee2018_uphill,
    estimate_cable_yarder_productivity_tr125_multi_span,
    estimate_cable_yarder_productivity_tr125_single_span,
    estimate_cable_yarder_productivity_tr127,
)
from .eriksson2014 import (
    estimate_forwarder_productivity_final_felling,
    estimate_forwarder_productivity_thinning,
)
from .ghaffariyan2019 import (
    ALPACASlopeClass,
    alpaca_slope_multiplier,
    estimate_forwarder_productivity_large_forwarder_thinning,
    estimate_forwarder_productivity_small_forwarder_thinning,
)
from .grapple_bc import (
    estimate_grapple_yarder_productivity_sr54,
    estimate_grapple_yarder_productivity_tr75_bunched,
    estimate_grapple_yarder_productivity_tr75_handfelled,
)
from .forwarder_bc import (
    ForwarderBCModel,
    ForwarderBCResult,
    estimate_forwarder_productivity_bc,
)
from .skidder_ft import (
    Han2018SkidderMethod,
    SkidderProductivityResult,
    estimate_grapple_skidder_productivity_han2018,
)
from .harvester_ctl import (
    ADV6N10HarvesterInputs,
    TN292HarvesterInputs,
    estimate_harvester_productivity_adv5n30,
    estimate_harvester_productivity_adv6n10,
    estimate_harvester_productivity_tn292,
)
from .kellogg_bettinger1994 import LoadType as KelloggLoadType
from .kellogg_bettinger1994 import estimate_forwarder_productivity_kellogg_bettinger
from .lahrsen2025 import (
    LahrsenModel,
    ProductivityDistributionEstimate,
    ProductivityEstimate,
    estimate_productivity,
    estimate_productivity_distribution,
)
from .laitila2020 import estimate_brushwood_harwarder_productivity
from .ranges import load_lahrsen_ranges
from .sessions2006 import (
    ShovelLoggingParameters,
    ShovelLoggingResult,
    estimate_shovel_logging_productivity,
)
from .spinelli2017 import (
    GrappleYarderInputs,
    estimate_grapple_yarder_productivity,
)
from .stoilov2021 import (
    estimate_skidder_harvester_productivity_delay_free,
    estimate_skidder_harvester_productivity_with_delays,
)

__all__ = [
    "LahrsenModel",
    "ProductivityEstimate",
    "ProductivityDistributionEstimate",
    "estimate_productivity",
    "estimate_productivity_distribution",
    "load_lahrsen_ranges",
    "estimate_forwarder_productivity_final_felling",
    "estimate_forwarder_productivity_thinning",
    "estimate_cable_skidding_productivity_unver_spss",
    "estimate_cable_skidding_productivity_unver_robust",
    "estimate_cable_skidding_productivity_unver_spss_profile",
    "estimate_cable_skidding_productivity_unver_robust_profile",
    "estimate_cable_yarder_productivity_lee2018_uphill",
    "estimate_cable_yarder_productivity_lee2018_downhill",
    "estimate_cable_yarder_productivity_tr125_single_span",
    "estimate_cable_yarder_productivity_tr125_multi_span",
    "estimate_cable_yarder_cycle_time_tr127_minutes",
    "estimate_cable_yarder_productivity_tr127",
    "estimate_harvester_productivity_adv6n10",
    "estimate_harvester_productivity_adv5n30",
    "estimate_harvester_productivity_tn292",
    "estimate_forwarder_productivity_small_forwarder_thinning",
    "estimate_forwarder_productivity_large_forwarder_thinning",
    "estimate_forwarder_productivity_kellogg_bettinger",
    "estimate_forwarder_productivity_bc",
    "estimate_grapple_skidder_productivity_han2018",
    "ALPACASlopeClass",
    "alpaca_slope_multiplier",
    "ForwarderBCModel",
    "ForwarderBCResult",
    "KelloggLoadType",
    "estimate_brushwood_harwarder_productivity",
    "estimate_skidder_harvester_productivity_delay_free",
    "estimate_skidder_harvester_productivity_with_delays",
    "estimate_grapple_yarder_productivity_sr54",
    "estimate_grapple_yarder_productivity_tr75_bunched",
    "estimate_grapple_yarder_productivity_tr75_handfelled",
    "GrappleYarderInputs",
    "estimate_grapple_yarder_productivity",
    "ShovelLoggingParameters",
    "ShovelLoggingResult",
    "estimate_shovel_logging_productivity",
    "ADV6N10HarvesterInputs",
    "TN292HarvesterInputs",
    "Han2018SkidderMethod",
    "SkidderProductivityResult",
]
