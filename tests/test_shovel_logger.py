from __future__ import annotations

import pytest

from fhops.productivity.shovel_logger import (
    ShovelLoggerSessions2006Inputs,
    estimate_shovel_logger_productivity_sessions2006,
)


def test_sessions2006_default_productivity() -> None:
    inputs = ShovelLoggerSessions2006Inputs(
        passes=4,
        swing_length_m=16.15,
        strip_length_m=100.0,
        volume_per_ha_m3=375.0,
    )
    result = estimate_shovel_logger_productivity_sessions2006(inputs)
    assert result.predicted_m3_per_pmh == pytest.approx(52.9230, rel=1e-3)


def test_sessions2006_custom_parameters() -> None:
    inputs = ShovelLoggerSessions2006Inputs(
        passes=3,
        swing_length_m=18.0,
        strip_length_m=80.0,
        volume_per_ha_m3=320.0,
        swing_time_roadside_s=18.0,
        swing_time_initial_s=28.0,
        swing_time_rehandle_s=32.0,
        payload_per_swing_initial_m3=1.2,
        payload_per_swing_rehandle_m3=2.2,
        travel_speed_index_kph=1.0,
        travel_speed_return_kph=1.0,
        travel_speed_serpentine_kph=0.9,
        effective_minutes_per_hour=55.0,
    )
    result = estimate_shovel_logger_productivity_sessions2006(inputs)
    assert result.predicted_m3_per_pmh > 0
