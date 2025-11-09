from __future__ import annotations

import pytest

from fhops.cli._utils import parse_operator_weights


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
