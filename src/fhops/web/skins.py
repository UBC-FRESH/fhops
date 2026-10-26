"""Skin manifests for the FHOPS web application.

A skin is a JSON manifest over one application. The loader checks every panel, layer, and action
against a registry and refuses an unknown name with that name. ``read_only`` removes every mutating
action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "ACTIONS",
    "LAYERS",
    "MUTATING_ACTIONS",
    "PANELS",
    "SkinManifest",
    "load_skin",
    "load_skins",
    "validate_skin",
]

PANELS = frozenset(
    {
        "legend",
        "map",
        "schedule",
        "haul",
        "tactical",
        "kpis",
        "reports",
        "compare",
        "scenario",
        "run",
        "lidar",
    }
)
LAYERS = frozenset(
    {
        "blocks",
        "machines",
        "treatments",
        "roads",
        "mills",
        "haul_routes",
        "tactical_units",
        "facilities",
        "lidar_slope",
        "lidar_canopy",
        "lidar_operability",
    }
)
ACTIONS = frozenset(
    {
        "start_run",
        "pause",
        "stop",
        "edit_objective",
        "edit_locks",
        "edit_hauling",
        "edit_tactical",
        "export",
        "compare",
    }
)
MUTATING_ACTIONS = frozenset(
    {
        "start_run",
        "pause",
        "stop",
        "edit_objective",
        "edit_locks",
        "edit_hauling",
        "edit_tactical",
    }
)
_SKIN_DIR = Path(__file__).resolve().parent / "skins"


@dataclass(frozen=True, slots=True)
class SkinManifest:
    """Validated skin manifest.

    Attributes
    ----------
    id / title:
        Identifier and display label.
    panels / layers / actions:
        Names checked against :data:`PANELS`, :data:`LAYERS`, and :data:`ACTIONS`.
    read_only:
        Remove every mutating action.
    """

    id: str
    title: str
    panels: tuple[str, ...]
    layers: tuple[str, ...]
    actions: tuple[str, ...]
    read_only: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready payload."""
        return {
            "id": self.id,
            "title": self.title,
            "panels": list(self.panels),
            "layers": list(self.layers),
            "actions": list(self.actions),
            "read_only": self.read_only,
        }


def validate_skin(payload: dict[str, Any]) -> SkinManifest:
    """Validate a skin payload.

    Parameters
    ----------
    payload:
        Parsed JSON object with ``id``, ``title``, ``panels``, ``layers``, ``actions``, and
        ``read_only``.

    Returns
    -------
    SkinManifest
        Validated manifest.

    Raises
    ------
    ValueError
        When an id/title is missing, a panel/layer/action is unknown, or a read-only skin contains a
        mutating action.
    """
    skin_id = str(payload.get("id", "")).strip()
    title = str(payload.get("title", "")).strip()
    if not skin_id:
        raise ValueError("Skin id must be non-empty")
    if not title:
        raise ValueError(f"Skin {skin_id!r} title must be non-empty")
    panels = _names(payload.get("panels", []), PANELS, skin_id, "panel")
    layers = _names(payload.get("layers", []), LAYERS, skin_id, "layer")
    actions = _names(payload.get("actions", []), ACTIONS, skin_id, "action")
    read_only = bool(payload.get("read_only", False))
    if read_only:
        forbidden = sorted(set(actions) & MUTATING_ACTIONS)
        if forbidden:
            raise ValueError(
                f"Read-only skin {skin_id!r} cannot enable mutating actions: {forbidden}"
            )
    return SkinManifest(
        id=skin_id,
        title=title,
        panels=panels,
        layers=layers,
        actions=actions,
        read_only=read_only,
    )


def _names(raw: object, registry: frozenset[str], skin_id: str, label: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"Skin {skin_id!r} {label}s must be a list of strings")
    unknown = sorted(set(raw) - registry)
    if unknown:
        raise ValueError(f"Skin {skin_id!r} has unknown {label}(s): {unknown}")
    return tuple(raw)


def load_skin(path: Path) -> SkinManifest:
    """Load and validate one skin JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Skin {path} must contain a JSON object")
    return validate_skin(payload)


def load_skins(directory: Path | None = None) -> list[SkinManifest]:
    """Load every skin JSON file from a directory, sorted by id."""
    directory = directory or _SKIN_DIR
    skins = [load_skin(path) for path in sorted(directory.glob("*.json"))]
    return sorted(skins, key=lambda skin: skin.id)
