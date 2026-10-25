"""Run discovery and manifest handling for the FHOPS web service.

The service reads the artefacts the CLI writes. This module classifies a directory into one of the
three planning lenses (operational, hauling, tactical-operational), collects the known files, and
optionally writes a stable ``run.json`` manifest. It never invents a file or a KPI.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "DOMAINS",
    "RUN_MANIFEST_SCHEMA_VERSION",
    "RunRecord",
    "build_run_manifest",
    "classify_run",
    "discover_runs",
    "load_run_manifest",
    "write_run_manifest",
]

RUN_MANIFEST_SCHEMA_VERSION = "1.0.0"
DOMAINS = ("operational", "hauling", "tactical_operational")
_MANIFEST_NAME = "run.json"
_SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache"}

# Logical artefact name -> candidate filenames/globs. The first match wins.
_KNOWN_FILES: dict[str, tuple[str, ...]] = {
    # Operational
    "assignments": ("assignments.csv", "*_solution.csv", "mip_solution.csv", "sa_solution.csv"),
    "summary": ("summary.json",),
    "telemetry": ("telemetry.jsonl", "telemetry-*.jsonl"),
    "day_summary": ("day_summary.csv",),
    "shift_summary": ("shift_summary.csv",),
    "day_parquet": ("day_summary.parquet",),
    "shift_parquet": ("shift_summary.parquet",),
    "rolling_iterations": ("iterations.csv", "iterations.jsonl"),
    # Hauling
    "haul_flows": ("haul_flows.csv",),
    "haul_truckloads": ("haul_truckloads.csv",),
    "haul_yard_inventory": ("haul_yard_inventory.csv",),
    "haul_block_inventory": ("haul_block_inventory.csv",),
    "haul_contractor_workload": ("haul_contractor_workload.csv",),
    "haul_schedule": ("haul_schedule.csv",),
    "haul_truck_summary": ("haul_truck_summary.csv",),
    "haul_loader_summary": ("haul_loader_summary.csv",),
    "haul_kpis": ("haul_kpis.json",),
    "haul_summary": ("haul_summary.json",),
    # Tactical-operational
    "harvest_decisions": ("harvest_decisions.csv",),
    "production": ("production.csv",),
    "flows": ("flows.csv",),
    "purchases": ("purchases.csv",),
    "inventory": ("inventory.csv",),
    "roads": ("roads.csv",),
    "silviculture": ("silviculture.csv",),
    "fleet": ("fleet.csv",),
    "tactical_summary": ("tactical_summary.json",),
}


@dataclass(slots=True)
class RunRecord:
    """One discovered run directory.

    Attributes
    ----------
    run_id:
        Stable identifier used in API paths.
    path:
        Absolute run directory.
    domain:
        ``operational``, ``hauling``, or ``tactical_operational`` (``None`` when unclassified).
    run_type:
        Best-effort run kind, such as ``solve_heur``, ``haul_solve``, or ``tactical_operational``.
    status:
        Manifest status when present, otherwise ``unknown``.
    manifest:
        Parsed ``run.json`` when present.
    files:
        Logical artefact name -> path relative to the run directory.
    warnings:
        Discovery/classification warnings.
    """

    run_id: str
    path: Path
    domain: str | None
    run_type: str | None
    status: str
    manifest: dict[str, Any] | None = None
    files: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready payload."""
        return {
            "run_id": self.run_id,
            "path": str(self.path),
            "domain": self.domain,
            "run_type": self.run_type,
            "status": self.status,
            "manifest": self.manifest,
            "files": self.files,
            "warnings": self.warnings,
        }


def discover_runs(roots: Sequence[Path], *, max_depth: int = 2) -> list[RunRecord]:
    """Discover run directories under one or more roots.

    Parameters
    ----------
    roots:
        Directories to scan. A root may itself be a run directory.
    max_depth:
        Maximum child depth below each root. ``1`` scans immediate children, ``2`` grandchildren.

    Returns
    -------
    list[RunRecord]
        Sorted by ``run_id``. Directories with no known artefact are skipped.
    """
    discovered: dict[Path, RunRecord] = {}
    for root in roots:
        root = root.expanduser().resolve()
        if not root.exists():
            continue
        if _is_run_dir(root):
            record = _record_for(root, root)
            discovered[record.path] = record
            continue
        for candidate in _walk_candidates(root, max_depth=max_depth):
            if _is_run_dir(candidate):
                record = _record_for(candidate, root)
                discovered[record.path] = record
    return sorted(discovered.values(), key=lambda record: record.run_id)


def _walk_candidates(root: Path, *, max_depth: int) -> Iterable[Path]:
    yield from _walk(root, depth=1, max_depth=max_depth)


def _walk(path: Path, *, depth: int, max_depth: int) -> Iterable[Path]:
    if depth > max_depth:
        return
    try:
        children = sorted(path.iterdir(), key=lambda item: item.name)
    except OSError:
        return
    for child in children:
        if not child.is_dir() or child.name in _SKIP_DIRS or child.name.startswith("."):
            continue
        yield child
        yield from _walk(child, depth=depth + 1, max_depth=max_depth)


def _is_run_dir(path: Path) -> bool:
    return (path / _MANIFEST_NAME).exists() or bool(_scan_files(path))


def _record_for(run_dir: Path, root: Path) -> RunRecord:
    manifest, warnings = _read_manifest(run_dir)
    files = _scan_files(run_dir)
    warnings = list(warnings)
    domain = manifest.get("domain") if manifest else None
    run_type = manifest.get("run_type") if manifest else None
    if domain is None or run_type is None:
        classified_domain, classified_type, classification_warnings = classify_run(files)
        domain = domain or classified_domain
        run_type = run_type or classified_type
        warnings.extend(classification_warnings)
    if domain not in DOMAINS and domain is not None:
        warnings.append(f"Unknown domain in run.json: {domain!r}")
    run_id = _run_id(run_dir, root, manifest)
    return RunRecord(
        run_id=run_id,
        path=run_dir,
        domain=domain,
        run_type=run_type,
        status=(
            str(manifest.get("status", "unknown")) if manifest else _infer_status(run_dir, files)
        ),
        manifest=manifest,
        files=files,
        warnings=warnings,
    )


def _run_id(run_dir: Path, root: Path, manifest: dict[str, Any] | None) -> str:
    if manifest and manifest.get("run_id"):
        return str(manifest["run_id"])
    try:
        relative = run_dir.relative_to(root)
        text = str(relative).replace("\\", "/").strip("/")
    except ValueError:
        text = run_dir.name
    if not text or text == ".":
        text = run_dir.name
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")
    return slug or "run"


def _scan_files(run_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for logical, patterns in _KNOWN_FILES.items():
        for pattern in patterns:
            matches = sorted(run_dir.glob(pattern))
            if matches:
                files[logical] = str(matches[0].relative_to(run_dir))
                break
    return files


def classify_run(files: dict[str, str]) -> tuple[str | None, str | None, list[str]]:
    """Classify a run from its logical file names.

    Parameters
    ----------
    files:
        Logical artefact names from :func:`_scan_files` (or a manifest's ``files`` map).

    Returns
    -------
    tuple[str | None, str | None, list[str]]
        ``(domain, run_type, warnings)``. Ambiguous combinations are reported rather than guessed.
    """
    names = set(files)
    warnings: list[str] = []
    hauling = names & {
        "haul_flows",
        "haul_truckloads",
        "haul_schedule",
        "haul_summary",
        "haul_kpis",
    }
    tactical = names & {
        "harvest_decisions",
        "production",
        "flows",
        "inventory",
        "roads",
        "silviculture",
        "fleet",
    }
    operational = names & {
        "assignments",
        "telemetry",
        "day_summary",
        "shift_summary",
        "rolling_iterations",
    }

    domains = [
        name
        for name, present in (
            ("hauling", hauling),
            ("tactical_operational", tactical),
            ("operational", operational),
        )
        if present
    ]
    if len(domains) > 1:
        warnings.append(f"Run contains artefacts from multiple domains: {', '.join(domains)}")
    domain = domains[0] if domains else None

    if domain == "hauling":
        if "haul_schedule" in names:
            run_type = "haul_solve" if "haul_flows" in names else "haul_schedule"
        elif "haul_flows" in names:
            run_type = "haul_plan"
        else:
            run_type = "hauling"
    elif domain == "tactical_operational":
        run_type = "tactical_operational"
    elif domain == "operational":
        if "rolling_iterations" in names:
            run_type = "plan_rolling"
        elif "assignments" in names:
            run_type = "solve"
        elif "day_summary" in names or "shift_summary" in names:
            run_type = "eval_playback"
        else:
            run_type = "operational"
    else:
        run_type = None
        if names:
            warnings.append("Known files did not classify into a planning domain")
    return domain, run_type, warnings


def load_run_manifest(run_dir: Path) -> dict[str, Any] | None:
    """Load ``run.json`` from a run directory, or ``None`` when absent.

    Raises
    ------
    ValueError
        When the manifest is not a JSON object.
    """
    path = run_dir / _MANIFEST_NAME
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _read_manifest(run_dir: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        return load_run_manifest(run_dir), []
    except (OSError, ValueError) as exc:
        return None, [f"Ignored invalid run.json: {exc}"]


def build_run_manifest(
    run_dir: Path,
    *,
    domain: str | None = None,
    run_type: str | None = None,
    command: str | None = None,
    scenario: str | None = None,
    solver: str | None = None,
    seed: int | None = None,
    status: str | None = None,
    run_id: str | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Build (and optionally write) a ``run.json`` manifest for a directory.

    Parameters
    ----------
    run_dir:
        Existing run directory.
    domain / run_type:
        Explicit overrides. When omitted, the manifest is classified from the files.
    command / scenario / solver / seed / status:
        Provenance fields. Existing values are preserved unless overridden.
    run_id:
        Explicit run id. Defaults to the existing manifest value or the directory name/path slug.
    write:
        When ``True``, write ``run.json`` and return the written payload.

    Returns
    -------
    dict[str, Any]
        Manifest payload.
    """
    run_dir = run_dir.expanduser().resolve()
    if not run_dir.exists():
        raise FileNotFoundError(run_dir)
    existing, manifest_warnings = _read_manifest(run_dir)
    files = _scan_files(run_dir)
    classified_domain, classified_type, warnings = classify_run(files)
    warnings.extend(manifest_warnings)
    payload: dict[str, Any] = dict(existing or {})
    payload.update(
        {
            "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
            "run_id": run_id or payload.get("run_id") or _run_id(run_dir, run_dir, None),
            "domain": domain or payload.get("domain") or classified_domain,
            "run_type": run_type or payload.get("run_type") or classified_type,
            "status": status or payload.get("status") or _infer_status(run_dir, files),
            "files": files,
            "warnings": warnings,
            "generated_at": _now(),
        }
    )
    for key, value in (
        ("command", command),
        ("scenario", scenario),
        ("solver", solver),
        ("seed", seed),
    ):
        if value is not None:
            payload[key] = value
    if write:
        (run_dir / _MANIFEST_NAME).write_text(
            json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
        )
    return payload


def write_run_manifest(run_dir: Path, **kwargs: Any) -> dict[str, Any]:
    """Write a ``run.json`` manifest and return it. See :func:`build_run_manifest`."""
    kwargs["write"] = True
    return build_run_manifest(run_dir, **kwargs)


def _infer_status(run_dir: Path, files: dict[str, str]) -> str:
    """Read a status field from a summary artefact when no manifest exists."""
    for logical in ("haul_summary", "tactical_summary", "summary"):
        filename = files.get(logical)
        if not filename:
            continue
        try:
            payload = json.loads((run_dir / filename).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("status"):
            return str(payload["status"])
    return "unknown"


def _now() -> str:
    """Return a UTC timestamp."""
    return datetime.now(UTC).isoformat()
