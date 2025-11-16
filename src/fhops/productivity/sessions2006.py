"""Shovel logging productivity helper based on Sessions & Boston (2006)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShovelLoggingParameters:
    """Model parameters extracted from Sessions & Boston (2006)."""

    swing_length_m: float = 16.15
    tonnes_per_hectare: float = 375.0
    seconds_per_swing_initial: float = 30.0
    seconds_per_swing_rehandle: float = 30.0
    seconds_per_swing_roadside: float = 20.0
    tonnes_per_swing_initial: float = 1.0
    tonnes_per_swing_rehandle: float = 2.0
    walking_speed_road_kph: float = 0.7
    walking_speed_unit_kph: float = 0.7
    walking_speed_serpentine_kph: float = 0.7
    shovel_cost_per_hour: float = 125.0
    price_per_tonne: float = 4.0
    road_cost_per_km: float = 6211.0
    work_minutes_per_day: float = 480.0
    density_tonnes_per_m3: float = 1.0


@dataclass(frozen=True)
class ShovelLoggingResult:
    passes: int
    road_spacing_m: float
    rack_length_m: float
    daily_volume_tonnes: float
    productivity_tonnes_per_pmh: float
    productivity_m3_per_pmh: float
    cost_per_tonne: float
    daily_profit: float
    shovel_cost_per_day: float
    road_cost_per_day: float


def estimate_shovel_logging_productivity(passes: int, params: ShovelLoggingParameters) -> ShovelLoggingResult:
    """Evaluate shovel logging productivity/costs for a given number of passes.

    The formulation follows Sessions & Boston (2006), "Optimization of Road Spacing for
    Log Length Shovel Logging on Gentle Terrain" (International Journal of Forest Engineering 17(1)).
    """

    if passes < 1:
        raise ValueError("passes must be >= 1")
    if params.swing_length_m <= 0:
        raise ValueError("swing_length_m must be > 0")

    def minutes_per_meter(speed_kph: float) -> float:
        if speed_kph <= 0:
            raise ValueError("walking speeds must be > 0")
        return 60.0 / (speed_kph * 1000.0)

    z = params.swing_length_m
    n = passes
    w = params.tonnes_per_hectare / 10000.0
    t0 = params.seconds_per_swing_roadside / 60.0
    t1 = params.seconds_per_swing_initial / 60.0
    t2 = params.seconds_per_swing_rehandle / 60.0
    b0 = params.tonnes_per_swing_initial
    b1 = params.tonnes_per_swing_initial
    b2 = params.tonnes_per_swing_rehandle
    if b0 <= 0 or b1 <= 0 or b2 <= 0:
        raise ValueError("tonnes per swing must be > 0")

    v1 = minutes_per_meter(params.walking_speed_road_kph)
    v2 = minutes_per_meter(params.walking_speed_unit_kph)
    v3 = minutes_per_meter(params.walking_speed_serpentine_kph)

    s_y = (
        t0 * z * w / b0
        + n * t1 * z * w / b1
        + 0.5 * (n - 1) * n * t2 * z * w / b2
        + v1
        + n * v3
    )
    s_const = n * z * (v2 + v3)

    if s_const >= params.work_minutes_per_day:
        raise ValueError("Walking time exceeds available working minutes.")

    daily_volume = (params.work_minutes_per_day - s_const) * w * (n + 1) * z / s_y
    rack_length = daily_volume / (w * (n + 1) * z)
    timber_density = params.density_tonnes_per_m3
    productivity_t_per_pmh = daily_volume / (params.work_minutes_per_day / 60.0)
    productivity_m3_per_pmh = productivity_t_per_pmh / timber_density

    b_common = z * w * rack_length
    t1_minutes = t0 * b_common / b0
    t2_minutes = n * t1 * b_common / b1
    t3_minutes = 0.5 * (n - 1) * n * t2 * b_common / b2
    t4_minutes = rack_length * v1 + n * z * v2 + n * (rack_length + z) * v3
    total_minutes = t1_minutes + t2_minutes + t3_minutes + t4_minutes

    cost_per_minute = params.shovel_cost_per_hour / 60.0
    c_side = cost_per_minute * total_minutes
    w_per_side = (n + 1) * z * rack_length * w
    road_cost_per_meter = params.road_cost_per_km / 1000.0
    road_cost = road_cost_per_meter * rack_length

    cost_per_tonne = (road_cost + 2.0 * c_side) / (2.0 * w_per_side)
    daily_profit = max(params.price_per_tonne - cost_per_tonne, float("-inf")) * (2.0 * w_per_side)

    return ShovelLoggingResult(
        passes=passes,
        road_spacing_m=2.0 * (n + 1) * z,
        rack_length_m=rack_length,
        daily_volume_tonnes=daily_volume,
        productivity_tonnes_per_pmh=productivity_t_per_pmh,
        productivity_m3_per_pmh=productivity_m3_per_pmh,
        cost_per_tonne=cost_per_tonne,
        daily_profit=daily_profit,
        shovel_cost_per_day=2.0 * c_side,
        road_cost_per_day=road_cost,
    )


__all__ = [
    "ShovelLoggingParameters",
    "ShovelLoggingResult",
    "estimate_shovel_logging_productivity",
]
