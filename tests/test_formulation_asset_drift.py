"""Regression check for generated formulation assets staying synchronized."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_formulation_assets_are_synchronized() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/check_formulation_assets.py", "--repo-root", str(repo_root)],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "synchronized" in result.stdout
