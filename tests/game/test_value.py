"""Tests for game price decks and log-value accounting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from fhops.game.value import PriceSchedule


@dataclass
class _Log:
    product: str
    log_index: int
    volume_m3: float


def test_price_deck_loads_and_values_products() -> None:
    price = PriceSchedule.from_path(Path("examples/game/levels/kc_57254551/prices.yaml"))
    value = price.value_logs(
        [
            _Log("sawlog", 1, 1.0),
            _Log("sawlog", 2, 2.0),
            _Log("pulp", 1, 3.0),
        ]
    )

    assert value["product_volume_m3"] == {
        "sawlog_butt": 1.0,
        "sawlog_upper": 2.0,
        "pulp": 3.0,
    }
    assert value["gross_log_value"] == pytest.approx(140.0 + 200.0 + 135.0)


def test_residual_and_road_costs() -> None:
    price = PriceSchedule(
        products={"sawlog_butt": 1.0},
        residual_asset_per_m3=70.0,
        road_extension_cost_per_m=120.0,
    )

    assert price.residual_asset_value(10.0) == 700.0
    assert price.road_extension_cost(12.5) == 1500.0


def test_unknown_product_fails_closed() -> None:
    price = PriceSchedule(products={"sawlog_butt": 1.0})

    with pytest.raises(KeyError, match="No price for log product"):
        price.value_logs([_Log("sawlog", 1, 1.0), _Log("pulp", 1, 1.0)])
