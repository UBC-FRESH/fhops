"""Helpers for locating FHOPS package data in source and wheel installs."""

from __future__ import annotations

from pathlib import Path


def data_path(*parts: str) -> Path:
    """Return a path under the FHOPS reference data directory.

    Parameters
    ----------
    *parts:
        Path components beneath the repository/package ``data`` directory. Components must be
        relative names such as ``"productivity"`` or ``"reference/fpinnovations"``; absolute paths
        are not accepted.

    Returns
    -------
    pathlib.Path
        Filesystem path to the requested data file or directory. In a source checkout this resolves
        to the repository-level ``data/`` directory; in a built wheel it resolves to bundled
        ``fhops/data`` package data.

    Raises
    ------
    ValueError
        If any component is absolute.
    """

    if any(Path(part).is_absolute() for part in parts):
        raise ValueError("data_path components must be relative")

    repo_data = Path(__file__).resolve().parents[2] / "data"
    if repo_data.exists():
        return repo_data.joinpath(*parts)
    return Path(__file__).resolve().parent.joinpath("data", *parts)
