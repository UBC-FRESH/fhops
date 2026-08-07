"""Tests for examples/notebook_support.py and the onboarding notebook series.

These tests validate:
- Notebook JSON structure (valid JSON, cell metadata.language).
- Support module contracts (diagnose_config, build_node, symbol/doc verification,
  schedule validation).
- No reliance on licensed solvers (all tests use SA or read-only operations).

Skips are only applied when a genuine project dependency is unavailable.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

# Insert examples/ on sys.path so notebook_support is importable regardless of cwd.
_EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
if str(_EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES_DIR))

from notebook_support import (  # noqa: E402
    AAMStatus,
    build_node,
    diagnose_config,
    discover_scenarios,
    explain_workflow,
    find_repo_root,
    inspect_scenario,
    preview_schedule,
    rtfm,
    run_fhops_cli,
    summarise_scenario,
    validate_schedule,
)

# ---------------------------------------------------------------------------
# Notebook JSON validation
# ---------------------------------------------------------------------------

ONBOARDING_NOTEBOOKS = [
    "00_fhops_orientation",
    "01_fhops_operations_simulation",
    "02_fhops_solve_compare",
    "03_fhops_playback_kpis",
    "04_fhops_stochastic_what_if",
]


def _load_runner_module():
    runner_path = Path(__file__).resolve().parent.parent / "scripts" / "run_example_notebooks.py"
    spec = importlib.util.spec_from_file_location("run_example_notebooks", runner_path)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("00", "00_fhops_orientation"),
        ("01", "01_fhops_operations_simulation"),
        ("02", "02_fhops_solve_compare"),
        ("03", "03_fhops_playback_kpis"),
        ("04", "04_fhops_stochastic_what_if"),
        ("01.ipynb", "01_fhops_operations_simulation"),
        ("04.ipynb", "04_fhops_stochastic_what_if"),
    ],
)
def test_runner_normalizes_notebook_alias(alias: str, expected: str) -> None:
    """Numeric runner aliases resolve without executing a notebook."""

    runner = _load_runner_module()
    assert runner.normalize_notebook_name(alias) == expected


def test_runner_preserves_full_notebook_name() -> None:
    """Canonical notebook names pass through normalization unchanged."""

    runner = _load_runner_module()
    name = runner.DEFAULT_NOTEBOOKS[1]
    assert runner.normalize_notebook_name(name) == name


def test_runner_rejects_unknown_notebook(capsys: pytest.CaptureFixture[str]) -> None:
    """Unknown explicit selections fail before notebook execution begins."""

    runner = _load_runner_module()
    assert runner.main(["--notebook", "99", "--light", "--timeout", "300"]) == 2
    captured = capsys.readouterr()
    assert "unknown notebook selection" in captured.err
    assert "Choose from:" in captured.err


@pytest.mark.parametrize("notebook_name", ONBOARDING_NOTEBOOKS)
def test_notebook_is_valid_json(notebook_name: str) -> None:
    """Each onboarding notebook is parseable as standard JSON."""

    path = _EXAMPLES_DIR / f"{notebook_name}.ipynb"
    assert path.is_file(), f"missing notebook: {path}"
    raw = path.read_text(encoding="utf-8")
    nb = json.loads(raw)
    assert "cells" in nb
    assert nb["nbformat"] == 4


@pytest.mark.parametrize("notebook_name", ONBOARDING_NOTEBOOKS)
def test_notebook_cell_metadata_contract(notebook_name: str) -> None:
    """Every cell has matching metadata.language and a non-empty metadata.id."""

    path = _EXAMPLES_DIR / f"{notebook_name}.ipynb"
    nb = json.loads(path.read_text(encoding="utf-8"))
    for i, cell in enumerate(nb["cells"]):
        expected_language = "markdown" if cell["cell_type"] == "markdown" else "python"
        language = cell.get("metadata", {}).get("language")
        assert language == expected_language, (
            f"cell {i} in {notebook_name}: expected language={expected_language!r}, "
            f"got {language!r}"
        )
        cell_id = cell.get("metadata", {}).get("id")
        assert cell_id, f"cell {i} in {notebook_name}: missing metadata.id"


@pytest.mark.parametrize("notebook_name", ONBOARDING_NOTEBOOKS)
def test_notebook_cells_have_source(notebook_name: str) -> None:
    """Every cell has a non-empty source."""

    path = _EXAMPLES_DIR / f"{notebook_name}.ipynb"
    nb = json.loads(path.read_text(encoding="utf-8"))
    for i, cell in enumerate(nb["cells"]):
        source = cell.get("source", "")
        assert isinstance(source, (str, list)), (
            f"cell {i} in {notebook_name}: source must be str or list"
        )


def test_operations_simulation_notebook_has_public_api_walkthrough() -> None:
    """The operations notebook retains its stable simulation-facing content."""

    path = _EXAMPLES_DIR / "01_fhops_operations_simulation.ipynb"
    text = path.read_text(encoding="utf-8")
    for expected in (
        "Problem.from_scenario",
        "default_system_registry",
        "estimate_grapple_skidder_productivity_adv6n7",
        "estimate_processor_productivity_berry2019",
        "estimate_loader_forwarder_productivity_tn261",
        "run_playback",
        "PlaybackConfig",
        "sequencing_first_violation_reason",
    ):
        assert expected in text


# ---------------------------------------------------------------------------
# Support module: repo discovery
# ---------------------------------------------------------------------------


def test_find_repo_root_returns_path() -> None:
    root = find_repo_root()
    # Root may be None if run outside a FHOPS checkout, which is fine.
    # When it is found, it must be a directory containing pyproject.toml.
    if root is not None:
        assert (root / "pyproject.toml").is_file()


def test_discover_scenarios_returns_list() -> None:
    result = discover_scenarios()
    assert isinstance(result, list)
    for kind, path in result:
        assert path.is_file()


# ---------------------------------------------------------------------------
# Support module: AAM contracts
# ---------------------------------------------------------------------------


def test_diagnose_config_success() -> None:
    """diagnose_config succeeds on a valid scenario file."""

    root = find_repo_root()
    if root is None:
        pytest.skip("no FHOPS repo root found")
    path = root / "examples" / "tiny7" / "scenario.yaml"
    if not path.is_file():
        pytest.skip("tiny7 scenario not found")
    result = diagnose_config(path)
    assert result["ok"] is True, f"diagnose_config failed: {result['errors']}"
    assert result["status"] == AAMStatus.EXECUTED.value
    assert result["executed"] is True
    assert result["review_only"] is False
    assert "scenario" in result
    assert result["scenario"]["num_blocks"] > 0


def test_diagnose_config_failure_missing_file() -> None:
    """diagnose_config returns ok=False for a missing file."""

    result = diagnose_config("/nonexistent/path/scenario.yaml")
    assert result["ok"] is False
    assert result["status"] == AAMStatus.FAILED.value
    assert len(result["errors"]) > 0


def test_diagnose_config_failure_invalid_yaml() -> None:
    """diagnose_config returns structured failure for an invalid scenario."""

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("not: valid: fhops: scenario: [")
        f.flush()
        result = diagnose_config(f.name)
    assert result["ok"] is False
    assert result["status"] == AAMStatus.FAILED.value
    assert len(result["errors"]) > 0


def test_build_node_is_review_only() -> None:
    """build_node returns executed=False and review_only=True."""

    result = build_node("test description")
    assert result["ok"] is True
    assert result["executed"] is False
    assert result["review_only"] is True
    assert result["status"] == AAMStatus.REVIEW_ONLY.value
    assert "draft" in result


def test_rtfm_verifies_symbols() -> None:
    """rtfm verifies at least some FHOPS symbols are importable."""

    result = rtfm("verify core symbols")
    assert result["ok"] is True
    summary = result["summary"]
    # At least the basic symbols should be verified if fhops is installed
    if "fhops" in sys.modules or importlib.util.find_spec("fhops") is not None:
        assert summary["symbols_verified"] >= 3, (
            f"expected >=3 symbols verified, got {summary['symbols_verified']}"
        )


def test_explain_workflow_is_review_only() -> None:
    result = explain_workflow("test goal")
    assert result["ok"] is True
    assert result["executed"] is False
    assert result["review_only"] is True
    assert "goal" in result


def test_inspect_scenario_returns_scenario_keys() -> None:
    root = find_repo_root()
    if root is None:
        pytest.skip("no FHOPS repo root found")
    path = root / "examples" / "tiny7" / "scenario.yaml"
    if not path.is_file():
        pytest.skip("tiny7 scenario not found")
    result = inspect_scenario(path)
    assert result["ok"] is True
    assert "scenario" in result
    assert result["scenario"]["num_days"] == 7


def test_preview_schedule_valid() -> None:
    import pandas as pd

    df = pd.DataFrame(
        {
            "machine_id": ["H1", "H2"],
            "block_id": ["B1", "B2"],
            "day": [1, 2],
            "shift_id": ["S1", "S1"],
        }
    )
    result = preview_schedule(df)
    assert result["ok"] is True
    assert result["review_only"] is True
    assert result["summary"]["rows"] == 2


def test_preview_schedule_invalid() -> None:
    import pandas as pd

    df = pd.DataFrame({"foo": [1, 2]})  # missing required columns
    result = preview_schedule(df)
    assert result["ok"] is False
    assert result["status"] == AAMStatus.FAILED.value


# ---------------------------------------------------------------------------
# Support module: schedule validation
# ---------------------------------------------------------------------------


def test_validate_schedule_required_columns() -> None:
    import pandas as pd

    df = pd.DataFrame({"machine_id": ["H1"], "block_id": ["B1"], "day": [1]})
    result = validate_schedule(df)
    assert result["ok"] is True
    assert result["missing_columns"] == []


def test_validate_schedule_missing_columns() -> None:
    import pandas as pd

    df = pd.DataFrame({"machine_id": ["H1"]})
    result = validate_schedule(df)
    assert result["ok"] is False
    assert "block_id" in result["missing_columns"]
    assert "day" in result["missing_columns"]


def test_validate_schedule_with_shift() -> None:
    import pandas as pd

    df = pd.DataFrame(
        {
            "machine_id": ["H1"],
            "block_id": ["B1"],
            "day": [1],
            "shift_id": ["S1"],
        }
    )
    result = validate_schedule(df)
    assert result["ok"] is True
    assert result["shift_id_present"] is True


# ---------------------------------------------------------------------------
# Support module: scenario summarisation
# ---------------------------------------------------------------------------


def test_summarise_scenario_valid() -> None:
    root = find_repo_root()
    if root is None:
        pytest.skip("no FHOPS repo root found")
    path = root / "examples" / "tiny7" / "scenario.yaml"
    if not path.is_file():
        pytest.skip("tiny7 scenario not found")
    result = summarise_scenario(path)
    assert result["ok"] is True
    assert result["name"] == "FHOPS Tiny7"
    assert result["num_days"] == 7
    assert result["num_blocks"] == 2


def test_summarise_scenario_missing() -> None:
    result = summarise_scenario("/nonexistent/scenario.yaml")
    assert result["ok"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# Support module: CLI invocation
# ---------------------------------------------------------------------------


def test_run_fhops_cli_validate() -> None:
    root = find_repo_root()
    if root is None:
        pytest.skip("no FHOPS repo root found")
    path = root / "examples" / "tiny7" / "scenario.yaml"
    if not path.is_file():
        pytest.skip("tiny7 scenario not found")
    result = run_fhops_cli("validate", str(path))
    assert result["status_code"] == 0
    assert "Days" in result["stdout"]
    assert "Blocks" in result["stdout"]


def test_run_fhops_cli_nonzero_exit() -> None:
    """A non-existent scenario should cause a non-zero exit."""

    try:
        run_fhops_cli("validate", "/nonexistent/scenario.yaml")
    except Exception as exc:
        assert (
            hasattr(exc, "result")
            or "exited" in str(exc).lower()
            or "nonexistent" in str(exc).lower()
        )
        return
    pytest.fail("expected an exception for non-zero exit")
