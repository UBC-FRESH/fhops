"""Deprecated playback event fields warn at the caller, visible from user scripts (#139).

The warnings are emitted inside pydantic validators; a fixed ``stacklevel`` attributed them to
pydantic, where the default warning filters hide :class:`DeprecationWarning`.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import warnings
from pathlib import Path

import pytest

from fhops.evaluation.playback.events import (
    DowntimeEventConfig,
    SamplingConfig,
    WeatherEventConfig,
)

SRC = str(Path(__file__).resolve().parents[1] / "src")


@pytest.mark.parametrize(
    ("build", "field"),
    [
        (lambda: WeatherEventConfig(correlated_days=False), "correlated_days"),
        (lambda: DowntimeEventConfig(seed_offset=3), "seed_offset"),
        (
            lambda: SamplingConfig.model_validate({"weather": {"correlated_days": False}}),
            "correlated_days",
        ),
        (lambda: SamplingConfig.model_validate({"landing": {"seed_offset": 1}}), "seed_offset"),
    ],
)
def test_warning_is_attributed_to_the_caller(build, field: str) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        build()
    relevant = [w for w in caught if field in str(w.message)]
    assert len(relevant) == 1
    assert issubclass(relevant[0].category, DeprecationWarning)
    assert relevant[0].filename == __file__


def _run_script(tmp_path: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    script = tmp_path / "user_script.py"
    script.write_text(
        textwrap.dedent(
            """
            from fhops.evaluation.playback.events import DowntimeEventConfig, WeatherEventConfig

            WeatherEventConfig(correlated_days=False)
            DowntimeEventConfig(seed_offset=3)
            print("done")
            """
        )
    )
    return subprocess.run(
        [sys.executable, *flags, str(script)],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": SRC, "PATH": ""},
        check=False,
    )


def test_user_script_sees_the_warnings_with_default_filters(tmp_path: Path) -> None:
    result = _run_script(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "user_script.py:4: DeprecationWarning: WeatherEventConfig.correlated_days" in (
        result.stderr
    )
    assert "user_script.py:5: DeprecationWarning: DowntimeEventConfig.seed_offset" in result.stderr


def test_user_script_fails_under_w_error(tmp_path: Path) -> None:
    result = _run_script(tmp_path, "-W", "error::DeprecationWarning")
    assert result.returncode != 0
    assert "DeprecationWarning: WeatherEventConfig.correlated_days" in result.stderr
    assert "done" not in result.stdout
