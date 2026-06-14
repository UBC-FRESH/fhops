"""Tests for package resource resolution."""

from __future__ import annotations

import pytest

from fhops.resources import data_path


def test_data_path_resolves_source_checkout_data() -> None:
    """The resolver should find repository data during editable/source test runs."""

    path = data_path("productivity", "processor_berry2019.json")
    assert path.is_file()
    assert path.name == "processor_berry2019.json"


def test_data_path_rejects_absolute_components() -> None:
    """Absolute paths are not accepted as package-data components."""

    with pytest.raises(ValueError, match="relative"):
        data_path("/tmp", "processor_berry2019.json")
