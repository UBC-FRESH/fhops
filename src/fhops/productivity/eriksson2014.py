"""Forwarder productivity helpers derived from Eriksson & Lindroos (2014)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class _ForwarderModel:
    """Light-weight container for the log-linear productivity model."""

    intercept: float
    coeff_ln_mfd_sq: float
    coeff_ln_mean_stem: float
    coeff_ln_mfd_load: float
    rmse: float

    def predict(
        self, mean_extraction_distance_m: float, mean_stem_size_m3: float, load_capacity_m3: float
    ) -> float:
        """
        Predict forwarder productivity (m³/PMH₀) for the configured regression.

        Parameters
        ----------
        mean_extraction_distance_m:
            Mean forwarding distance (m). Must be > 0.
        mean_stem_size_m3:
            Mean stem size (m³). Must be > 0.
        load_capacity_m3:
            Payload capacity per trip (m³). Must be > 0.

        Returns
        -------
        float
            Delay-free productivity in cubic metres per productive machine hour.
        """
        if mean_extraction_distance_m <= 0:
            raise ValueError("mean_extraction_distance_m must be > 0")
        if mean_stem_size_m3 <= 0:
            raise ValueError("mean_stem_size_m3 must be > 0")
        if load_capacity_m3 <= 0:
            raise ValueError("load_capacity_m3 must be > 0")

        ln_mfd = math.log(mean_extraction_distance_m)
        ln_mean_stem = math.log(mean_stem_size_m3)
        ln_mfd_load = math.log(mean_extraction_distance_m * load_capacity_m3)

        ln_productivity = (
            self.intercept
            + self.coeff_ln_mfd_sq * (ln_mfd**2)
            + self.coeff_ln_mean_stem * ln_mean_stem
            + self.coeff_ln_mfd_load * ln_mfd_load
        )

        # The models were calibrated in log space. Eriksson & Lindroos note that the
        # intercepts are not bias-corrected, so we add RMSE^2 / 2 before exponentiation.
        bias = (self.rmse**2) / 2.0
        return math.exp(ln_productivity + bias)


# Model coefficients captured from Table 6 (Eriksson & Lindroos 2014).
_FINAL_FELLING_MODEL = _ForwarderModel(
    intercept=0.327,
    coeff_ln_mfd_sq=-0.073,
    coeff_ln_mean_stem=0.188,
    coeff_ln_mfd_load=0.636,
    rmse=0.30,
)

_THINNING_MODEL = _ForwarderModel(
    intercept=2.798,
    coeff_ln_mfd_sq=-0.029,
    coeff_ln_mean_stem=0.296,
    coeff_ln_mfd_load=0.166,
    rmse=0.28,
)


def estimate_forwarder_productivity_final_felling(
    mean_extraction_distance_m: float,
    mean_stem_size_m3: float,
    load_capacity_m3: float,
) -> float:
    """
    Estimate forwarder productivity (m³/PMH₀) for final-felling stands.

    Parameters
    ----------
    mean_extraction_distance_m:
        Mean logging road extraction distance (m). Must be > 0.
    mean_stem_size_m3:
        Mean stem size (m³). Must be > 0.
    load_capacity_m3:
        Payload capacity (m³) per cycle. Must be > 0.

    Returns
    -------
    float
        Delay-free productivity in m³ per productive machine hour.
    """

    return _FINAL_FELLING_MODEL.predict(
        mean_extraction_distance_m, mean_stem_size_m3, load_capacity_m3
    )


def estimate_forwarder_productivity_thinning(
    mean_extraction_distance_m: float,
    mean_stem_size_m3: float,
    load_capacity_m3: float,
) -> float:
    """
    Estimate forwarder productivity (m³/PMH₀) for thinning sites.

    Parameters
    ----------
    mean_extraction_distance_m:
        Mean forwarding distance (m). Must be > 0.
    mean_stem_size_m3:
        Mean stem size (m³). Must be > 0.
    load_capacity_m3:
        Payload capacity (m³) per cycle. Must be > 0.

    Returns
    -------
    float
        Delay-free productivity in m³ per productive machine hour.
    """

    return _THINNING_MODEL.predict(mean_extraction_distance_m, mean_stem_size_m3, load_capacity_m3)


__all__ = [
    "estimate_forwarder_productivity_final_felling",
    "estimate_forwarder_productivity_thinning",
]
