"""Support helpers for the FHOPS onboarding notebook series.

This module is *notebook-local*: it provides lightweight wrappers around the
installed ``fhops`` Python package and CLI for use in the ``examples/``
Jupyter notebooks (``00_fhops_orientation.ipynb`` through ``04_fhops_stochastic_what_if.ipynb``).
It is intentionally **not** a public package API — treat everything here as
example code.

The module covers:

* Repository and scenario dataset discovery (no hard-coded paths).
* Structured ``fhops`` CLI invocation that tolerates an installed console
  script, a source-checkout ``python -m`` entry point, and a Typer/Click
  fallback.
* Compact schedule validation and display-friendly scenario/schedule summaries.
* Notebook-local AAM-style helper callables (``explain_workflow``,
  ``diagnose_config``, ``build_node``, ``rtfm``) that ground referenced FHOPS
  symbols and documentation paths with importlib/file checks.

All AAM callables return structured, displayable dictionaries/dataclasses
with explicit ``ok``, ``operation``/``name``, ``errors``, ``provenance``, and
a clear ``executed`` vs review-only distinction.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class ScenarioKind(Enum):
    """Recognised bundled scenario directories under ``examples/``."""

    TINY7 = "tiny7"
    SMALL21 = "small21"
    MED42 = "med42"
    SYNTHETIC_SMALL = "synthetic-small"
    SYNTHETIC_MEDIUM = "synthetic-medium"
    SYNTHETIC_LARGE = "synthetic-large"


_SCENARIO_SUBDIRS: dict[ScenarioKind, str] = {
    ScenarioKind.TINY7: "tiny7",
    ScenarioKind.SMALL21: "small21",
    ScenarioKind.MED42: "med42",
    ScenarioKind.SYNTHETIC_SMALL: "synthetic/small",
    ScenarioKind.SYNTHETIC_MEDIUM: "synthetic/medium",
    ScenarioKind.SYNTHETIC_LARGE: "synthetic/large",
}


def find_repo_root(start: Path | None = None) -> Path | None:
    """Walk upward from ``start`` to locate the directory holding ``pyproject.toml`` with
    ``project.name == "fhops"``. Returns ``None`` if nothing is found."""

    probe = (start or Path.cwd()).resolve()
    while True:
        candidate = probe / "pyproject.toml"
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8")
            except OSError:
                probe = probe.parent
                continue
            if 'name = "fhops"' in text or "name='fhops'" in text:
                return probe
        parent = probe.parent
        if parent == probe:
            return None
        probe = parent


def discover_scenarios(
    repo_root: Path | None = None,
    kind: ScenarioKind | None = None,
) -> list[tuple[ScenarioKind, Path]]:
    """Return a list of (kind, scenario.yaml) pairs.

    Parameters
    ----------
    repo_root:
        Explicit FHOPS repository root. If ``None``, :func:`find_repo_root`
        is invoked from ``Path.cwd()``.
    kind:
        When supplied, only the matching scenario directory is returned.

    Returns
    -------
    list[tuple[ScenarioKind, Path]]
        Empty list when the repo cannot be located or the requested scenario
        is missing.
    """

    root = repo_root or find_repo_root()
    if root is None:
        return []

    if kind is not None:
        subdir = _SCENARIO_SUBDIRS.get(kind)
        if subdir is None:
            return []
        path = root / "examples" / subdir / "scenario.yaml"
        return [(kind, path)] if path.is_file() else []

    results: list[tuple[ScenarioKind, Path]] = []
    for sc_kind, subdir in _SCENARIO_SUBDIRS.items():
        path = root / "examples" / subdir / "scenario.yaml"
        if path.is_file():
            results.append((sc_kind, path))
    return results


def resolve_scenario_path(repo_root: Path | None, relative: str) -> Path:
    """Return an absolute Path for ``relative`` (e.g. ``"examples/tiny7"``)."""

    root = repo_root or find_repo_root()
    if root is None:
        raise FileNotFoundError(f"Cannot resolve scenario path without a repo root: {relative!r}")
    return (root / relative).resolve()


# ---------------------------------------------------------------------------
# CLI invocation
# ---------------------------------------------------------------------------


def _find_fhops_console_script() -> str | None:
    """Locate the ``fhops`` console script on ``PATH``."""

    return shutil.which("fhops")


def _find_source_main() -> Path | None:
    """Return the path to ``src/fhops/cli/main.py`` if it exists, else None."""

    root = find_repo_root()
    if root is None:
        return None
    # Prefer the explicit main.py entry; __main__.py is a fallback.
    candidate = root / "src" / "fhops" / "cli" / "main.py"
    if candidate.is_file():
        return candidate
    alt = root / "src" / "fhops" / "cli" / "__main__.py"
    return alt if alt.is_file() else None


def _resolve_python_interpreter() -> str:
    """Pick the most appropriate Python interpreter for CLI invocation."""

    root = find_repo_root()
    if root is not None:
        venv_python = root / ".venv" / "bin" / "python"
        if venv_python.is_file():
            return str(venv_python)
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            text = pyproject.read_text(encoding="utf-8")
            if "requires-python" in text and ">=3.11" in text:
                pass
    return sys.executable


def run_fhops_cli(
    *args: str,
    cwd: Path | str | None = None,
    timeout: int | None = None,
    capture_output: bool = True,
) -> dict[str, Any]:
    """Run ``fhops <args>`` and return a structured result.

    Parameters
    ----------
    *args:
        CLI arguments passed to the ``fhops`` command (without the leading
        ``fhops`` token).
    cwd:
        Working directory for the subprocess. Defaults to the repo root.
    timeout:
        Wall-clock seconds before the subprocess is killed. ``None`` means
        no limit.
    capture_output:
        Whether to capture stdout/stderr. Defaults to ``True``.

    Returns
    -------
    dict[str, Any]
        ``{"status_code": int, "stdout": str, "stderr": str, "args": list[str],
        "command": str}``. Non-zero exit codes raise :class:`SubprocessError`.

    Raises
    ------
    SubprocessError
        Raised when the CLI exits with a non-zero status code. The exception
        carries ``result`` and ``args`` attributes for programmatic inspection.
    RuntimeError
        Raised when no ``fhops`` entry point can be located.
    """

    root = cwd if cwd is not None else (find_repo_root() or Path.cwd())
    if isinstance(root, str):
        root = Path(root)

    executable = _find_fhops_console_script()
    subprocess_env = dict(os.environ)
    if executable is None:
        src_main = _find_source_main()
        if src_main is not None:
            python = _resolve_python_interpreter()
            cmd = [python, "-m", "fhops.cli.main", *args]
            # Ensure src/ is on PYTHONPATH for the subprocess.
            src_dir = root / "src"
            prev = subprocess_env.get("PYTHONPATH", "")
            if str(src_dir) not in prev:
                subprocess_env["PYTHONPATH"] = str(src_dir) + (":" + prev if prev else "")
        else:
            raise RuntimeError(
                "No 'fhops' console script or source-checkout entry point found. "
                "Install fhops (`pip install -e .`) or run from a source checkout."
            )
    else:
        cmd = [executable, *args]

    result_dict: dict[str, Any] = {
        "status_code": -1,
        "stdout": "",
        "stderr": "",
        "args": list(args),
        "command": " ".join(cmd),
    }

    proc = subprocess.run(
        cmd,
        cwd=str(root),
        capture_output=capture_output,
        timeout=timeout,
        text=True,
        env=subprocess_env,
    )
    result_dict["status_code"] = proc.returncode
    result_dict["stdout"] = proc.stdout or ""
    result_dict["stderr"] = proc.stderr or ""

    if proc.returncode != 0:
        exc = subprocess.SubprocessError(
            f"fhops {' '.join(args)} exited with code {proc.returncode}"
        )
        exc.result = result_dict
        exc.args = list(args)
        raise exc

    return result_dict


# ---------------------------------------------------------------------------
# Schedule validation
# ---------------------------------------------------------------------------

_REQUIRED_ASSIGNMENT_COLUMNS = {"machine_id", "block_id", "day"}


def validate_schedule(
    assignments: Any,  # pd.DataFrame
) -> dict[str, Any]:
    """Perform a compact validation of a solver/assignment DataFrame.

    Returns
    -------
    dict[str, Any]
        ``ok``, ``column_set``, ``missing_columns``, ``rows``, ``day_range``,
        ``block_ids``, ``machine_ids``, ``shift_id_present``, ``sample_ids``.
    """

    missing = list(_REQUIRED_ASSIGNMENT_COLUMNS - set(assignments.columns))
    ok = len(missing) == 0

    rows = int(len(assignments))
    day_range: list[int] = []
    if ok and "day" in assignments.columns:
        days = assignments["day"].dropna().astype(int)
        if len(days) > 0:
            day_range = [int(days.min()), int(days.max())]

    result: dict[str, Any] = {
        "ok": ok,
        "column_set": sorted(assignments.columns.tolist()),
        "missing_columns": missing,
        "rows": rows,
        "day_range": day_range,
        "block_ids": sorted(assignments["block_id"].dropna().unique().tolist()) if ok else [],
        "machine_ids": sorted(assignments["machine_id"].dropna().unique().tolist()) if ok else [],
        "shift_id_present": "shift_id" in assignments.columns,
        "sample_ids": (
            sorted(assignments["sample_id"].unique().tolist())
            if ok and "sample_id" in assignments.columns
            else None
        ),
    }
    return result


# ---------------------------------------------------------------------------
# Scenario/schedule summaries
# ---------------------------------------------------------------------------


def summarise_scenario(scenario_path: Path | str) -> dict[str, Any]:
    """Return a compact, display-friendly summary of a FHOPS scenario.

    Loads the scenario via :func:`fhops.scenario.io.load_scenario` and builds
    a :class:`fhops.scenario.contract.Problem`. Never guesses — every field
    comes from the loaded object or an explicit load failure.
    """

    from fhops.scenario.contract import Problem
    from fhops.scenario.io import load_scenario

    path = Path(scenario_path)
    if not path.is_file():
        return {
            "ok": False,
            "name": None,
            "error": f"scenario file not found: {path}",
            "source": str(path),
        }

    try:
        scenario = load_scenario(str(path))
        problem = Problem.from_scenario(scenario)
    except Exception as exc:  # noqa: BLE001 - surface structured failure
        return {
            "ok": False,
            "name": None,
            "error": repr(exc),
            "source": str(path),
        }

    machine_roles = sorted({m.role for m in scenario.machines})
    harvest_systems = sorted(scenario.harvest_systems.keys()) if scenario.harvest_systems else []
    shift_labels = sorted({s.shift_id for s in problem.shifts})

    return {
        "ok": True,
        "name": scenario.name,
        "num_days": scenario.num_days,
        "num_blocks": len(scenario.blocks),
        "num_machines": len(scenario.machines),
        "num_landings": len(scenario.landings),
        "num_production_rates": len(scenario.production_rates),
        "machine_roles": machine_roles,
        "harvest_systems": harvest_systems,
        "num_shifts": len(shift_labels),
        "shift_labels": shift_labels,
        "blocks": [
            {
                "id": b.id,
                "work_required": float(b.work_required),
                "window": (b.earliest_start, b.latest_finish),
                "landing": b.landing_id,
            }
            for b in scenario.blocks
        ],
        "mobilisation": bool(scenario.mobilisation),
        "timeline": bool(scenario.timeline),
    }


def summarise_schedule(assignments: Any) -> dict[str, Any]:
    """Compact display-friendly summary of a schedule DataFrame."""

    v = validate_schedule(assignments)
    if v["ok"] and v["rows"] > 0:
        completed_blocks = len(v["block_ids"])
        machines_used = len(v["machine_ids"])
    else:
        completed_blocks = 0
        machines_used = 0

    return {
        "ok": v["ok"],
        "rows": v["rows"],
        "blocks_completed": completed_blocks,
        "machines_used": machines_used,
        "days_covered": v["day_range"],
        "has_shift_id": v["shift_id_present"],
        "missing_columns": v["missing_columns"],
    }


# ---------------------------------------------------------------------------
# AAM-style helpers (notebook-local)
# ---------------------------------------------------------------------------


class AAMStatus(StrEnum):
    """Outcome of an AAM-style operation."""

    EXECUTED = "executed"
    REVIEW_ONLY = "review_only"
    FAILED = "failed"


@dataclass
class AAMResult:
    """Structured return value for all AAM helpers."""

    ok: bool
    operation: str
    name: str
    status: AAMStatus
    provenance: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    result: Any = None
    executed: bool = False
    review_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "operation": self.operation,
            "name": self.name,
            "status": self.status.value,
            "provenance": list(self.provenance),
            "errors": list(self.errors),
            "executed": self.executed,
            "review_only": self.review_only,
            "result_type": type(self.result).__name__ if self.result is not None else None,
        }


# --- Symbol / doc verification -----------------------------------------------


def _verify_symbol(module: str, symbol: str) -> tuple[bool, str]:
    """Check whether ``symbol`` is importable from ``module``."""

    try:
        mod = importlib.import_module(module)
        if hasattr(mod, symbol):
            return True, f"{module}.{symbol}"
        return False, f"{module} has no {symbol}"
    except ImportError as exc:
        return False, f"{module} import failed: {exc}"


def _verify_doc_path(path: Path) -> tuple[bool, str]:
    """Return (exists, readable_description) for a documentation path."""

    if path.is_file():
        try:
            size = path.stat().st_size
            return True, f"{path} ({size} bytes)"
        except OSError:
            return False, f"{path} unreadable"
    return False, f"{path} not found"


def _available_symbols() -> dict[str, tuple[str, str]]:
    """Return a mapping of commonly-used FHOPS symbols to (module, symbol) pairs."""

    return {
        "load_scenario": ("fhops.scenario.io", "load_scenario"),
        "Problem": ("fhops.scenario.contract", "Problem"),
        "Scenario": ("fhops.scenario.contract", "Scenario"),
        "Block": ("fhops.scenario.contract", "Block"),
        "Machine": ("fhops.scenario.contract", "Machine"),
        "Landing": ("fhops.scenario.contract", "Landing"),
        "solve_sa": ("fhops.optimization.heuristics", "solve_sa"),
        "run_playback": ("fhops.evaluation.playback", "run_playback"),
        "run_stochastic_playback": ("fhops.evaluation.playback", "run_stochastic_playback"),
        "SamplingConfig": ("fhops.evaluation.playback.events", "SamplingConfig"),
        "compute_kpis": ("fhops.evaluation.metrics.kpis", "compute_kpis"),
        "shift_dataframe": ("fhops.evaluation.playback.aggregates", "shift_dataframe"),
        "day_dataframe": ("fhops.evaluation.playback.aggregates", "day_dataframe"),
    }


def _available_docs() -> list[tuple[Path, str]]:
    """Return a list of (path, description) for documentation files we reference."""

    root = find_repo_root()
    docs: list[tuple[Path, str]] = []
    if root is None:
        return docs

    candidates = [
        ("docs/howto/data_contract.rst", "Data contract specification"),
        ("docs/howto/evaluation.rst", "Evaluation how-to"),
        ("docs/howto/heuristic_presets.rst", "Heuristic presets how-to"),
        ("docs/howto/ils.rst", "Iterated Local Search how-to"),
        ("docs/howto/optimization_formulation.rst", "Optimization formulation"),
        ("README.md", "Project README"),
    ]
    for rel, desc in candidates:
        path = root / rel
        docs.append((path, desc))
    return docs


# --- The AAM helper callables -----------------------------------------------


def explain_workflow(goal: str) -> dict[str, Any]:
    """Explain the workflow needed to reach ``goal``.

    Review-only: does **not** invoke any solver or writer.
    """

    verified: list[str] = []
    for sym_name, (mod, sym) in _available_symbols().items():
        ok, info = _verify_symbol(mod, sym)
        if ok:
            verified.append(info)

    return {
        "ok": True,
        "operation": "explain_workflow",
        "name": "workflow explanation",
        "status": AAMStatus.REVIEW_ONLY.value,
        "provenance": [f"{mod}.{sym}" for mod, sym in _available_symbols().values()],
        "errors": [],
        "verified_symbols": verified,
        "executed": False,
        "review_only": True,
        "goal": goal,
        "draft_steps": [
            "Load scenario via fhops.scenario.io.load_scenario",
            "Build Problem via fhops.scenario.contract.Problem.from_scenario",
            "Run fhops.optimization.heuristics.solve_sa (or CLI solve-heur)",
            "Compute KPIs via fhops.evaluation.compute_kpis",
        ],
    }


def diagnose_config(scenario_path: str | Path) -> dict[str, Any]:
    """Diagnose the configuration of a FHOPS scenario file.

    Loads the scenario through :func:`fhops.scenario.io.load_scenario` and
    :func:`fhops.scenario.contract.Problem.from_scenario`, returning a
    structured failure if either step does not succeed. Does **not** guess
    at missing data.
    """

    path = Path(scenario_path)
    if not path.is_file():
        return {
            "ok": False,
            "operation": "diagnose_config",
            "name": str(path),
            "status": AAMStatus.FAILED.value,
            "provenance": [],
            "errors": [f"scenario file not found: {path}"],
            "executed": False,
            "review_only": False,
        }

    try:
        from fhops.scenario.contract import Problem
        from fhops.scenario.io import load_scenario
    except ImportError as exc:
        return {
            "ok": False,
            "operation": "diagnose_config",
            "name": str(path),
            "status": AAMStatus.FAILED.value,
            "provenance": [],
            "errors": [f"fhops import failed: {exc}"],
            "executed": False,
            "review_only": False,
        }

    try:
        scenario = load_scenario(str(path))
        problem = Problem.from_scenario(scenario)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "operation": "diagnose_config",
            "name": str(path),
            "status": AAMStatus.FAILED.value,
            "provenance": [],
            "errors": [repr(exc)],
            "executed": False,
            "review_only": False,
        }

    verified_symbols = []
    for sym_name, (mod, sym) in _available_symbols().items():
        ok, info = _verify_symbol(mod, sym)
        if ok:
            verified_symbols.append(info)

    return {
        "ok": True,
        "operation": "diagnose_config",
        "name": scenario.name,
        "status": AAMStatus.EXECUTED.value,
        "provenance": [str(path)],
        "errors": [],
        "verified_symbols": verified_symbols,
        "executed": True,
        "review_only": False,
        "scenario": {
            "num_days": scenario.num_days,
            "num_blocks": len(scenario.blocks),
            "num_machines": len(scenario.machines),
            "num_landings": len(scenario.landings),
            "has_timeline": scenario.timeline is not None,
            "has_mobilisation": scenario.mobilisation is not None,
            "has_harvest_systems": scenario.harvest_systems is not None,
            "num_production_rates": len(scenario.production_rates),
            "num_shifts": len(problem.shifts),
        },
    }


def build_node(description: str) -> dict[str, Any]:
    """Draft a review-only scheduling 'node' description.

    This is **review-only**: it does **not** invoke a solver and does not
    write any assignments. The returned dict can be inspected in a notebook
    and passed to a Solver Worker if the user wishes to execute it.
    """

    return {
        "ok": True,
        "operation": "build_node",
        "name": "draft node",
        "status": AAMStatus.REVIEW_ONLY.value,
        "provenance": [],
        "errors": [],
        "executed": False,
        "review_only": True,
        "description": description,
        "draft": {
            "type": "review_draft",
            "message": (
                "This node is a review-only draft. No solver has been invoked. "
                "Pass to a Solver Worker to execute against a real scenario."
            ),
        },
    }


def rtfm(goal: str) -> dict[str, Any]:
    """'Read The F***ing Manual' helper — verify that referenced symbols and
    docs actually exist on disk / are importable."""

    symbol_checks = []
    for sym_name, (mod, sym) in _available_symbols().items():
        ok, info = _verify_symbol(mod, sym)
        symbol_checks.append({"symbol": sym_name, "ok": ok, "detail": info})

    doc_checks = []
    for path, desc in _available_docs():
        ok, info = _verify_doc_path(path)
        doc_checks.append({"path": str(path), "ok": ok, "description": desc, "detail": info})

    return {
        "ok": True,
        "operation": "rtfm",
        "name": "symbol/doc verification",
        "status": AAMStatus.REVIEW_ONLY.value,
        "provenance": [],
        "errors": [],
        "executed": False,
        "review_only": True,
        "goal": goal,
        "symbol_checks": symbol_checks,
        "doc_checks": doc_checks,
        "summary": {
            "symbols_verified": sum(1 for c in symbol_checks if c["ok"]),
            "symbols_total": len(symbol_checks),
            "docs_verified": sum(1 for c in doc_checks if c["ok"]),
            "docs_total": len(doc_checks),
        },
    }


def inspect_scenario(scenario_path: str | Path) -> dict[str, Any]:
    """Inspect a scenario without executing a solver.

    Loads the scenario, builds the Problem, and returns a compact summary.
    """

    diag = diagnose_config(scenario_path)
    if not diag["ok"]:
        return diag

    from fhops.scenario.contract import Problem
    from fhops.scenario.io import load_scenario

    scenario = load_scenario(str(scenario_path))
    problem = Problem.from_scenario(scenario)

    return {
        "ok": True,
        "operation": "inspect_scenario",
        "name": scenario.name,
        "status": AAMStatus.EXECUTED.value,
        "provenance": [str(scenario_path)],
        "errors": [],
        "executed": True,
        "review_only": False,
        "scenario": {
            "num_days": scenario.num_days,
            "num_blocks": len(scenario.blocks),
            "num_machines": len(scenario.machines),
            "num_landings": len(scenario.landings),
            "machine_roles": sorted({m.role for m in scenario.machines}),
            "harvest_systems": sorted(scenario.harvest_systems.keys())
            if scenario.harvest_systems
            else [],
            "num_production_rates": len(scenario.production_rates),
            "num_shifts": len(problem.shifts),
            "shift_labels": sorted({s.shift_id for s in problem.shifts}),
        },
    }


def preview_schedule(assignments: Any) -> dict[str, Any]:
    """Preview a schedule DataFrame without running playback or KPIs."""

    v = validate_schedule(assignments)
    if not v["ok"]:
        return {
            "ok": False,
            "operation": "preview_schedule",
            "name": "preview",
            "status": AAMStatus.FAILED.value,
            "provenance": [],
            "errors": [f"schedule validation failed: {v['missing_columns']}"],
            "executed": False,
            "review_only": True,
        }

    return {
        "ok": True,
        "operation": "preview_schedule",
        "name": "preview",
        "status": AAMStatus.REVIEW_ONLY.value,
        "provenance": [],
        "errors": [],
        "executed": False,
        "review_only": True,
        "summary": summarise_schedule(assignments),
    }
