"""Tests for the skin manifest registry."""

from __future__ import annotations

import pytest

from fhops.web.skins import load_skins, validate_skin


def test_committed_skins_are_valid() -> None:
    skins = load_skins()
    assert {skin.id for skin in skins} == {
        "operational-planner",
        "hauling-planner",
        "tactical-planner",
        "reviewer",
    }
    reviewer = next(skin for skin in skins if skin.id == "reviewer")
    assert reviewer.read_only
    assert "start_run" not in reviewer.actions


def test_unknown_panel_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="unknown panel"):
        validate_skin(
            {
                "id": "bad",
                "title": "Bad",
                "panels": ["not-a-panel"],
                "layers": [],
                "actions": [],
                "read_only": False,
            }
        )


def test_read_only_skin_cannot_mutate() -> None:
    with pytest.raises(ValueError, match="mutating actions"):
        validate_skin(
            {
                "id": "bad-reader",
                "title": "Bad reader",
                "panels": ["kpis"],
                "layers": [],
                "actions": ["start_run"],
                "read_only": True,
            }
        )
