from __future__ import annotations

import pytest

import pytest

from fhops.cli._utils import (
    OPERATOR_PRESETS,
    operator_preset_help,
    parse_operator_preset,
    parse_operator_weights,
)


def test_parse_operator_weights_success():
    result = parse_operator_weights(["swap=2", "move=0"])
    assert result == {"swap": 2.0, "move": 0.0}


def test_parse_operator_weights_empty():
    assert parse_operator_weights(None) == {}
    assert parse_operator_weights([]) == {}


@pytest.mark.parametrize("value", ["swap", "swap=", "=1.0"])
def test_parse_operator_weights_invalid_format(value):
    with pytest.raises(ValueError):
        parse_operator_weights([value])


def test_parse_operator_weights_non_numeric():
    with pytest.raises(ValueError):
        parse_operator_weights(["swap=abc"])


@pytest.mark.parametrize("preset", list(OPERATOR_PRESETS))
def test_parse_operator_preset_known(preset):
    operators, weights = parse_operator_preset(preset)
    expected = OPERATOR_PRESETS[preset]
    assert weights == {k: float(v) for k, v in expected.items()}
    if operators:
        assert all(name in expected for name in operators)


def test_parse_operator_preset_unknown():
    with pytest.raises(ValueError):
        parse_operator_preset("unknown")


def test_operator_preset_help_lists_presets():
    help_text = operator_preset_help()
    for name in OPERATOR_PRESETS:
        assert name in help_text
