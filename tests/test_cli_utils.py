from __future__ import annotations

import pytest

from fhops.cli._utils import (
    OPERATOR_PRESETS,
    format_operator_presets,
    operator_preset_help,
    parse_objective_weight_overrides,
    parse_operator_weights,
    resolve_operator_presets,
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


def test_parse_objective_weight_overrides_success():
    result = parse_objective_weight_overrides(["mobilisation=0.2", "landing=0"])
    assert result == {"mobilisation": 0.2, "landing_slack": 0.0}


def test_parse_objective_weight_overrides_empty():
    assert parse_objective_weight_overrides(None) == {}
    assert parse_objective_weight_overrides([]) == {}


def test_parse_objective_weight_overrides_invalid_key():
    with pytest.raises(ValueError):
        parse_objective_weight_overrides(["unknown=1.0"])


def test_parse_objective_weight_overrides_non_numeric():
    with pytest.raises(ValueError):
        parse_objective_weight_overrides(["production=fast"])


@pytest.mark.parametrize("preset", list(OPERATOR_PRESETS))
def test_resolve_operator_presets_known(preset):
    operators, weights = resolve_operator_presets([preset])
    expected = {k: float(v) for k, v in OPERATOR_PRESETS[preset].items()}
    assert weights == expected
    if operators:
        assert all(name in expected and expected[name] > 0 for name in operators)


def test_resolve_operator_presets_combined():
    operators, weights = resolve_operator_presets(["swap-only", "move-only"])
    assert weights == {
        "swap": 0.0,
        "move": 1.0,
        "block_insertion": 0.0,
        "cross_exchange": 0.0,
        "mobilisation_shake": 0.0,
    }
    assert operators == ["move"]


def test_resolve_operator_presets_unknown():
    with pytest.raises(ValueError):
        resolve_operator_presets(["unknown"])


def test_operator_preset_help_lists_presets():
    help_text = operator_preset_help()
    for name in OPERATOR_PRESETS:
        assert name in help_text


def test_format_operator_presets_includes_descriptions():
    formatted = format_operator_presets()
    for name in OPERATOR_PRESETS:
        assert name in formatted
