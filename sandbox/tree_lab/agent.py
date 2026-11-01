"""Local agent bridge for generating candidate Tree Lab cases.

The bridge reuses :func:`fhops.web.agent.run_agent`, which shells out to the
installed ``opencode`` CLI. It is disabled unless the app is started with
``--allow-agent``. Every prompt, duration, command, and validation result is
appended to ``runs/agent_log.jsonl``; provider credentials are never read or
logged.

Guardrails
----------
* the agent runs with the repository root as its workspace but is instructed to
  write only under ``sandbox/cases/_candidates/``;
* a before/after ``git status`` snapshot rejects any run that touched tracked
  files outside the candidate directory;
* candidate directories are validated against the case schema, the inventory
  contract, the scenario loader, and a smoke ``fhops tree system`` run before
  they can be accepted;
* acceptance is a separate, explicit user action and never overwrites an
  existing case.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fhops.web.agent import AgentError, AgentRequest, run_agent
from sandbox.tree_lab.cases import CaseError, load_case, validate_case

CANDIDATE_DIRNAME = "_candidates"
ALLOWED_TOP_LEVEL = {
    "case.json",
    "assignments.csv",
    "system_args.json",
    "README.md",
    "scenario",
    "tree_inventory",
}
MAX_CANDIDATE_FILES = 64
MAX_CANDIDATE_BYTES = 32 * 1024 * 1024

__all__ = [
    "AgentGuardError",
    "accept_candidate",
    "agent_status",
    "build_prompt",
    "candidates_root",
    "list_candidates",
    "run_candidate_agent",
    "validate_candidate",
]

PROMPT_TEMPLATE = """\
You are the FHOPS Tree Lab case generator. Work only inside this repository and
only inside `sandbox/cases/_candidates/`.

Create a new candidate case directory named `sandbox/cases/_candidates/{slug}/`
that satisfies the Tree Lab case schema in `sandbox/schemas/case.schema.json`.

Use the exemplar case at `sandbox/cases/{exemplar}/` as the structural template.
Copy the whole exemplar directory first, then change only the declared case
inputs: scenario YAML, scenario data CSVs, tree inventory CSV and metadata,
assignments CSV, and case.json. The scenario references `data/*.csv`, so the
candidate MUST include `scenario/data/` (blocks, machines, landings, calendar,
prod_rates, harvest_systems) even when those files are unchanged.

Keep the derived numbers consistent after any tree-list change:
* `scenario/data/blocks.csv`: `work_required`, `avg_stem_size_m3`,
  `volume_per_ha_m3`, `stem_density_per_ha`;
* `assignments.csv`: `production` equals the new merchantable volume;
* `case.json`: `stand.tree_count`, `stand.merchantable_volume_m3`,
  `stand.volume_per_ha_m3`.
Compute merchantable volume with the FHOPS reference stem model
(`fhops.stem.ReferenceStemModel`) so the numbers reconcile. Keep every path in
`case.json` relative to the candidate directory.

Hard rules:
1. Do NOT edit FHOPS source, tests, docs, repository settings, or any existing
   case outside `sandbox/cases/_candidates/`.
2. Do NOT use absolute paths, `..` traversal, or symlinks.
3. Keep the tree inventory in the `fhops.tree.inventory.v1` contract: the
   metadata `inventory_sha256` must match the CSV, and `block_ids` must match
   the scenario block.
4. Keep `case.json` `case_id` equal to the candidate directory name and
   `schema_version` equal to `fhops.tree_lab.case.v1`.
5. Keep `work_required`, `avg_stem_size_m3`, `volume_per_ha_m3`, and
   `stem_density_per_ha` consistent with the generated tree list.
6. Label the tree list synthetic and preserve the caveats.
7. Do not run arbitrary shell commands beyond reading files and running
   `fhops` validation commands if needed.
8. The inventory is the STAND, not the cut list. For a partial harvest keep every
   tree in the inventory and set `case.json.harvest` to
   `{"type": "partial", "marking_rule": "proportional", "target_basal_area_fraction": 0.30}`
   (rules: `proportional`, `from_below`, `diameter_limit` + `diameter_limit_cm`).
   The runner derives the cut list and records it in run.json. Never delete
   trees from the inventory to express a partial cut.
   `python -m sandbox.scripts.make_partial_case` is the reference implementation.

Requested change:
{prompt}

When finished, reply with a short summary listing the files you created, the
parameters you changed, and the expected tree count and volume.
"""


class AgentGuardError(RuntimeError):
    """Raised when the agent violated the sandbox contract."""


def candidates_root(cases_root: Path) -> Path:
    """Return the candidate directory, creating it if needed."""
    path = cases_root / CANDIDATE_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def agent_status(workspace: Path, *, model: str | None = None) -> dict[str, Any]:
    """Report whether the local agent CLI is available and configured.

    Parameters
    ----------
    workspace : Path
        Repository root used as the agent working directory.
    model : str, optional
        Explicit model override passed to ``opencode run --model``. When set it
        is reported as the effective model and the config default is reported
        separately as ``config_model``.
    """
    executable = shutil.which("opencode")
    status: dict[str, Any] = {
        "available": executable is not None,
        "executable": executable,
        "command": ["opencode", "run", "--format", "json"],
        "workspace": str(workspace),
        "model": model,
        "config_model": None,
        "version": None,
    }
    if executable is None:
        return status
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        status["version"] = (completed.stdout or completed.stderr).strip().splitlines()[-1]
    except (OSError, subprocess.SubprocessError):
        pass
    config_candidates = [
        Path.home() / ".config" / "opencode" / "opencode.json",
        Path.home() / ".config" / "opencode" / "opencode.jsonc",
        workspace / "opencode.json",
    ]
    for config in config_candidates:
        if not config.is_file():
            continue
        try:
            text = config.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if '"model"' in line:
                status["config_model"] = line.split(":", 1)[1].strip().strip(",").strip('"')
                break
        if status["config_model"]:
            break
    if status["model"] is None:
        status["model"] = status["config_model"]
    return status


def build_prompt(request: str, *, exemplar: str) -> str:
    """Render the agent prompt for one request."""
    slug = "candidate-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return PROMPT_TEMPLATE.format(slug=slug, exemplar=exemplar, prompt=request.strip())


def _git_dirty(workspace: Path) -> set[str]:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    paths: set[str] = set()
    for line in completed.stdout.splitlines():
        entry = line[3:].strip()
        if entry:
            paths.add(entry)
    return paths


def _candidate_paths(cases_root: Path) -> set[str]:
    root = cases_root / CANDIDATE_DIRNAME
    return (
        {str(path.relative_to(cases_root)) for path in root.rglob("*")} if root.is_dir() else set()
    )


def _check_candidate_layout(candidate: Path) -> None:
    for child in candidate.iterdir():
        if child.name not in ALLOWED_TOP_LEVEL:
            raise AgentGuardError(f"Candidate contains a disallowed entry: {child.name}")
        if child.is_symlink():
            raise AgentGuardError(f"Candidate contains a symlink: {child.name}")
    files = [path for path in candidate.rglob("*") if path.is_file()]
    if len(files) > MAX_CANDIDATE_FILES:
        raise AgentGuardError(f"Candidate has {len(files)} files (limit {MAX_CANDIDATE_FILES}).")
    total = sum(path.stat().st_size for path in files)
    if total > MAX_CANDIDATE_BYTES:
        raise AgentGuardError(f"Candidate is {total} bytes (limit {MAX_CANDIDATE_BYTES}).")


def list_candidates(cases_root: Path) -> list[dict[str, Any]]:
    """List candidate directories with a lightweight validity hint."""
    root = candidates_root(cases_root)
    items: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), reverse=True):
        if not child.is_dir() or child.name.startswith("."):
            continue
        entry: dict[str, Any] = {"candidate_id": child.name, "path": str(child), "valid": False}
        try:
            case = load_case(child)
        except CaseError as exc:
            entry["error"] = str(exc)
        else:
            entry["case_id"] = case.case_id
            entry["label"] = case.label
            entry["valid"] = True
        items.append(entry)
    return items


def validate_candidate(candidate_dir: Path, *, run_smoke: bool = True) -> dict[str, Any]:
    """Validate a candidate case, including an optional FHOPS smoke run.

    Parameters
    ----------
    candidate_dir : Path
        Candidate directory under ``cases/_candidates``.
    run_smoke : bool, optional
        Run ``fhops tree system`` with a short timeout in a temporary run
        directory. Defaults to ``True``.

    Returns
    -------
    dict[str, Any]
        Validation report with ``valid``, ``errors``, and ``smoke`` sections.
    """
    from sandbox.tree_lab.runner import RunError, run_case

    report: dict[str, Any] = {"candidate_id": candidate_dir.name, "errors": [], "warnings": []}
    try:
        _check_candidate_layout(candidate_dir)
        case = load_case(candidate_dir)
    except (CaseError, AgentGuardError) as exc:
        report["errors"].append(str(exc))
        report["valid"] = False
        return report
    validation = validate_case(case)
    report["case"] = validation
    report["errors"].extend(validation["errors"])
    report["warnings"].extend(validation.get("warnings", []))
    if validation["valid"] and run_smoke:
        try:
            smoke = run_case(case, candidate_dir / "_smoke_runs", run_id="smoke", timeout_s=180.0)
        except RunError as exc:
            report["errors"].append(f"Smoke run failed: {exc}")
            report["smoke"] = {"ok": False}
        else:
            report["smoke"] = {
                "ok": True,
                "tree_count": smoke["kpis"]["tree_count"],
                "processed_volume_m3": smoke["kpis"]["processed_volume_m3"],
                "makespan_s": smoke["kpis"]["makespan_s"],
            }
            shutil.rmtree(candidate_dir / "_smoke_runs", ignore_errors=True)
    report["valid"] = not report["errors"]
    return report


def accept_candidate(candidate_dir: Path, cases_root: Path) -> dict[str, Any]:
    """Accept a validated candidate into ``cases/`` without overwriting.

    Raises
    ------
    AgentGuardError
        If the candidate is outside the candidate root, invalid, or would
        overwrite an existing case.
    """
    root = candidates_root(cases_root).resolve()
    candidate = candidate_dir.resolve()
    if root not in candidate.parents:
        raise AgentGuardError("Candidate is outside sandbox/cases/_candidates.")
    report = validate_candidate(candidate, run_smoke=True)
    if not report["valid"]:
        raise AgentGuardError("Candidate failed validation: " + "; ".join(report["errors"]))
    destination = cases_root / candidate.name
    if destination.exists():
        raise AgentGuardError(f"Case {candidate.name!r} already exists; refusing to overwrite.")
    shutil.copytree(candidate, destination)
    return {"accepted": True, "case_id": candidate.name, "path": str(destination)}


def run_candidate_agent(
    request: str,
    *,
    workspace: Path,
    cases_root: Path,
    enabled: bool,
    timeout_s: float = 300.0,
    log_path: Path | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Run the local agent and return its response plus new candidates.

    Parameters
    ----------
    request : str
        Natural-language case request from the UI.
    workspace : Path
        Repository root used as the agent working directory.
    cases_root : Path
        Root containing cases and ``_candidates``.
    enabled : bool
        Must be ``True``; otherwise the call is refused.
    timeout_s : float, optional
        Agent subprocess timeout in seconds.
    log_path : Path, optional
        JSONL audit log path. Defaults to ``runs/agent_log.jsonl``.
    model : str, optional
        Explicit ``provider/model`` passed to ``opencode run --model``. When
        omitted the local ``opencode`` config default is used.

    Returns
    -------
    dict[str, Any]
        ``response``, ``candidates``, ``duration_s``, and ``guard`` details.
    """
    if not enabled:
        raise AgentGuardError("Agent is disabled; start the app with --allow-agent.")
    if not request.strip():
        raise AgentGuardError("Prompt is empty.")

    candidates = candidates_root(cases_root)
    before = _candidate_paths(cases_root)
    dirty_before = _git_dirty(workspace)
    exemplar = next(
        (path.name for path in sorted(cases_root.iterdir()) if (path / "case.json").is_file()),
        "afrf-gavin",
    )
    prompt = build_prompt(request, exemplar=exemplar)
    started = time.monotonic()
    status = agent_status(workspace, model=model)
    error: str | None = None
    response = ""
    try:
        result = run_agent(
            AgentRequest(message=prompt, model=model),
            workspace=workspace,
            command=("opencode", "run", "--format", "json"),
            timeout=timeout_s,
        )
        response = result["response"]
    except AgentError as exc:
        error = str(exc)
    duration = round(time.monotonic() - started, 3)

    dirty_after = _git_dirty(workspace)
    escaped = sorted(dirty_after - dirty_before)
    escaped = [
        path for path in escaped if not path.startswith(f"sandbox/cases/{CANDIDATE_DIRNAME}/")
    ]
    if escaped:
        error = (
            (error + "; " if error else "")
            + "Agent modified files outside the candidate root: "
            + ", ".join(escaped[:5])
        )

    new_paths = sorted(_candidate_paths(cases_root) - before)
    new_candidates = sorted(
        {
            parts[1]
            for parts in (path.split("/") for path in new_paths)
            if len(parts) > 2 and parts[0] == CANDIDATE_DIRNAME
        }
    )

    records: list[dict[str, Any]] = []
    for name in new_candidates:
        candidate_dir = candidates / name
        if not candidate_dir.is_dir():
            continue
        records.append(validate_candidate(candidate_dir, run_smoke=True))

    log_path = log_path or workspace / "sandbox" / "runs" / "agent_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "utc": datetime.now(UTC).isoformat(),
                    "request": request,
                    "model": status.get("model"),
                    "command": status.get("command"),
                    "duration_s": duration,
                    "error": error,
                    "candidates": [
                        {"candidate_id": item["candidate_id"], "valid": item["valid"]}
                        for item in records
                    ],
                }
            )
            + "\n"
        )
    return {
        "response": response,
        "error": error,
        "duration_s": duration,
        "candidates": records,
        "guard": {"escaped_paths": escaped},
        "agent": status,
    }
