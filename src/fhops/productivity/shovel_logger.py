"""Primary-transport hoe chucker (shovel logger) helper (Sessions & Boston 2006)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShovelLoggerSessions2006Inputs:
    """Parameter bundle mirroring the Sessions & Boston (2006) serpentine model.

    All distances are expressed in metres, swing times in seconds, payloads in cubic metres, and
    travel speeds in km/h. The defaults match the interior BC case study used in the paper.
    """

    passes: int = 4
    swing_length_m: float = 16.15
    strip_length_m: float = 100.0
    volume_per_ha_m3: float = 375.0
    swing_time_roadside_s: float = 20.0
    payload_per_swing_roadside_m3: float = 1.0
    swing_time_initial_s: float = 30.0
    payload_per_swing_initial_m3: float = 1.0
    swing_time_rehandle_s: float = 30.0
    payload_per_swing_rehandle_m3: float = 2.0
    travel_speed_index_kph: float = 0.7
    travel_speed_return_kph: float = 0.7
    travel_speed_serpentine_kph: float = 0.7
    effective_minutes_per_hour: float = 50.0


@dataclass(frozen=True)
class ShovelLoggerResult:
    """Output of the Sessions & Boston (2006) shovel logger model."""

    predicted_m3_per_pmh: float
    cycle_minutes: float
    payload_m3_per_cycle: float
    passes: int
    parameters: dict[str, float]
    pmh_basis: str = "PMH0"
    reference: str = "Sessions & Boston 2006"


def _speed_to_time_per_m(speed_kph: float) -> float:
    if speed_kph <= 0:
        raise ValueError("Travel speed must be > 0")
    meters_per_min = (speed_kph * 1000.0) / 60.0
    return 1.0 / meters_per_min


def estimate_shovel_logger_productivity_sessions2006(
    inputs: ShovelLoggerSessions2006Inputs,
    *,
    slope_multiplier: float = 1.0,
    bunching_multiplier: float = 1.0,
    custom_multiplier: float = 1.0,
) -> ShovelLoggerResult:
    """Estimate shovel logger productivity (m³/PMH0) using Sessions & Boston (2006).

    Parameters
    ----------
    inputs : ShovelLoggerSessions2006Inputs
        Dataclass capturing the serpentine layout (passes, swing lengths, payloads, travel speeds,
        effective minutes/hour, etc.). Defaults mirror the original paper.
    slope_multiplier : float, default=1.0
        Optional terrain adjustment (values ``<= 0`` are invalid). Use to encode uphill/downhill
        penalties from FPInnovations field notes.
    bunching_multiplier : float, default=1.0
        Optional multiplier for hand-bunched vs. feller-bunched stems.
    custom_multiplier : float, default=1.0
        Extra scaling knob exposed via the CLI for ad‑hoc sensitivity tests.

    Returns
    -------
    ShovelLoggerResult
        Dataclass containing predicted productivity (m³/PMH0), cycle minutes, payload per cycle, pass
        count, and a parameter echo dictionary.

    Notes
    -----
    * Units match the original model: metres for swing/strip lengths, seconds for swing times, m³ for
      payloads, km/h for travel speeds, and minutes/hour for effective time.
    * Multipliers are combined multiplicatively (slope × bunching × custom) so passing ``0`` disables
      the model.
    """

    n = int(inputs.passes)
    if n < 1:
        raise ValueError("passes must be >= 1")
    if inputs.strip_length_m <= 0:
        raise ValueError("strip_length_m must be > 0")
    if inputs.swing_length_m <= 0:
        raise ValueError("swing_length_m must be > 0")
    if inputs.volume_per_ha_m3 <= 0:
        raise ValueError("volume_per_ha_m3 must be > 0")

    z = inputs.swing_length_m
    y = inputs.strip_length_m
    density = inputs.volume_per_ha_m3 / 10000.0  # m³ per square metre.

    def _swing_minutes(seconds: float) -> float:
        if seconds <= 0:
            raise ValueError("Swing seconds must be > 0")
        return seconds / 60.0

    t0 = _swing_minutes(inputs.swing_time_roadside_s)
    t1 = _swing_minutes(inputs.swing_time_initial_s)
    t2 = _swing_minutes(inputs.swing_time_rehandle_s)

    if inputs.payload_per_swing_roadside_m3 <= 0:
        raise ValueError("payload_per_swing_roadside_m3 must be > 0")
    if inputs.payload_per_swing_initial_m3 <= 0:
        raise ValueError("payload_per_swing_initial_m3 must be > 0")
    if inputs.payload_per_swing_rehandle_m3 <= 0:
        raise ValueError("payload_per_swing_rehandle_m3 must be > 0")

    time_roadside = t0 * (y * density * z) / inputs.payload_per_swing_roadside_m3
    time_initial = n * t1 * (y * density * z) / inputs.payload_per_swing_initial_m3
    time_rehandle = (
        0.5 * (n - 1) * n * t2 * (y * density * z) / inputs.payload_per_swing_rehandle_m3
    )

    walk_time = (
        y * _speed_to_time_per_m(inputs.travel_speed_index_kph)
        + n * z * _speed_to_time_per_m(inputs.travel_speed_return_kph)
        + n * (y + z) * _speed_to_time_per_m(inputs.travel_speed_serpentine_kph)
    )

    total_minutes = time_roadside + time_initial + time_rehandle + walk_time
    if total_minutes <= 0:
        raise ValueError("Derived total minutes must be > 0")

    payload_per_cycle = (n + 1) * z * y * density
    if payload_per_cycle <= 0:
        raise ValueError("Derived payload per cycle must be > 0")

    productivity_per_minute = payload_per_cycle / total_minutes
    predicted = productivity_per_minute * inputs.effective_minutes_per_hour
    combined_multiplier = slope_multiplier * bunching_multiplier * custom_multiplier
    if combined_multiplier <= 0:
        raise ValueError("Combined multiplier must be > 0")
    predicted *= combined_multiplier
    if predicted <= 0:
        raise ValueError("Derived productivity must be > 0")

    params: dict[str, float] = {
        "passes": float(n),
        "swing_length_m": inputs.swing_length_m,
        "strip_length_m": inputs.strip_length_m,
        "volume_per_ha_m3": inputs.volume_per_ha_m3,
        "swing_time_roadside_s": inputs.swing_time_roadside_s,
        "swing_time_initial_s": inputs.swing_time_initial_s,
        "swing_time_rehandle_s": inputs.swing_time_rehandle_s,
        "payload_per_swing_roadside_m3": inputs.payload_per_swing_roadside_m3,
        "payload_per_swing_initial_m3": inputs.payload_per_swing_initial_m3,
        "payload_per_swing_rehandle_m3": inputs.payload_per_swing_rehandle_m3,
        "travel_speed_index_kph": inputs.travel_speed_index_kph,
        "travel_speed_return_kph": inputs.travel_speed_return_kph,
        "travel_speed_serpentine_kph": inputs.travel_speed_serpentine_kph,
        "effective_minutes_per_hour": inputs.effective_minutes_per_hour,
        "slope_multiplier": slope_multiplier,
        "bunching_multiplier": bunching_multiplier,
        "custom_multiplier": custom_multiplier,
        "applied_multiplier": combined_multiplier,
    }

    return ShovelLoggerResult(
        predicted_m3_per_pmh=predicted,
        cycle_minutes=total_minutes,
        payload_m3_per_cycle=payload_per_cycle,
        passes=n,
        parameters=params,
    )


__all__ = [
    "ShovelLoggerSessions2006Inputs",
    "ShovelLoggerResult",
    "estimate_shovel_logger_productivity_sessions2006",
]
