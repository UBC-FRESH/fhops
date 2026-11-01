"""FastAPI application for the local FHOPS Tree Lab sandbox.

The app is a thin consumer of the released FHOPS tree-scale workflow:

* cases are validated with :mod:`sandbox.tree_lab.cases`;
* runs shell out to ``fhops tree system`` and ``fhops tree scene`` via
  :mod:`sandbox.tree_lab.runner`;
* the agent console reuses :func:`fhops.web.agent.run_agent` through
  :mod:`sandbox.tree_lab.agent`.

It binds to loopback by default and the agent bridge is disabled unless
``--allow-agent`` is passed. It is a demonstration service, not an operational
planning tool.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import fhops
from sandbox.tree_lab.agent import (
    AgentGuardError,
    accept_candidate,
    agent_status,
    candidates_root,
    list_candidates,
    run_candidate_agent,
    validate_candidate,
)
from sandbox.tree_lab.cases import Case, CaseError, discover_cases, load_case, validate_case
from sandbox.tree_lab.runner import RunError, RunManager, list_runs, load_run

DEFAULT_AGENT_MODEL = "opencode-go/deepseek-v4.1-flash"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def build_id() -> str:
    """Return a cache-busting build id: git short SHA plus newest asset mtime."""
    import subprocess

    sha = "dev"
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        sha = completed.stdout.strip() or "dev"
    except (OSError, subprocess.SubprocessError):
        pass
    newest = max(
        (path.stat().st_mtime for path in STATIC_DIR.rglob("*") if path.is_file()), default=0
    )
    return f"{sha}-{int(newest)}"


REPO_ROOT = Path(__file__).resolve().parents[2]

__all__ = ["ServiceConfig", "create_app", "run"]


@dataclass(slots=True)
class ServiceConfig:
    """Runtime configuration for the Tree Lab app.

    Attributes
    ----------
    cases_root : Path
        Root containing case directories and ``_candidates``.
    runs_root : Path
        Root receiving run directories and the agent audit log.
    workspace : Path
        Repository root used as the agent working directory.
    allow_agent : bool
        Enable the local agent bridge. Disabled by default.
    agent_timeout_s : float
        Agent subprocess timeout in seconds.
    """

    cases_root: Path
    runs_root: Path
    workspace: Path = REPO_ROOT
    allow_agent: bool = False
    agent_timeout_s: float = 300.0
    agent_model: str | None = DEFAULT_AGENT_MODEL
    root_path: str = ""


class AgentRunRequest(BaseModel):
    """One natural-language case request from the UI."""

    message: str = Field(min_length=3, max_length=4000)


def _case_or_404(config: ServiceConfig, case_id: str) -> Case:
    try:
        case = load_case(config.cases_root / case_id)
    except CaseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if case.case_id != case_id:
        raise HTTPException(status_code=404, detail=f"Unknown case {case_id!r}.")
    return case


def _run_dir(config: ServiceConfig, case_id: str, run_id: str) -> Path:
    if "/" in run_id or ".." in run_id:
        raise HTTPException(status_code=400, detail="Invalid run id.")
    return config.runs_root / case_id / run_id


def create_app(config: ServiceConfig) -> FastAPI:
    """Build the Tree Lab FastAPI application."""
    app = FastAPI(title="FHOPS Tree Lab", version=fhops.__version__)
    manager = RunManager(cases_root=config.cases_root, runs_root=config.runs_root)

    @app.middleware("http")
    async def no_store_assets(request: Any, call_next: Any) -> Any:
        """Prevent browsers and proxies from pinning stale SPA assets."""
        response = await call_next(request)
        path = request.scope.get("path", "")
        if path == "/" or path.startswith(("/static", "/api/")):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    if config.root_path:
        prefix = "/" + config.root_path.strip("/")

        @app.middleware("http")
        async def strip_root_path(request: Any, call_next: Any) -> Any:
            """Accept both prefix-preserving and prefix-stripping proxies."""
            path = request.scope.get("path", "")
            if path == prefix or path.startswith(prefix + "/"):
                stripped = path[len(prefix) :] or "/"
                request.scope["path"] = stripped
                raw = request.scope.get("raw_path")
                if raw:
                    request.scope["raw_path"] = stripped.encode("ascii")
            return await call_next(request)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        cases = discover_cases(config.cases_root)
        quality: dict[str, Any] | None = None
        quality_path = config.runs_root / "quality.json"
        if quality_path.is_file():
            try:
                payload = json.loads(quality_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict):
                quality = {
                    "green": bool(payload.get("green")),
                    "generated_utc": payload.get("generated_utc"),
                    "failed": [
                        gate.get("name")
                        for gate in payload.get("gates", [])
                        if gate.get("status") == "failed"
                    ],
                }
        return {
            "status": "ok",
            "fhops_version": fhops.__version__,
            "cases": len(cases),
            "agent_enabled": config.allow_agent,
            "runs_root": str(config.runs_root),
            "quality": quality,
            "build": build_id(),
            "demo_only": True,
            "caveat": "Demonstration sandbox; not an operational, financial, or regulatory tool.",
        }

    @app.get("/api/cases")
    def cases() -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for case in discover_cases(config.cases_root):
            runs = list_runs(config.runs_root, case.case_id)
            items.append(
                {
                    "case_id": case.case_id,
                    "label": case.label,
                    "block_id": case.manifest.get("block_id"),
                    "provenance": case.manifest.get("provenance", {}),
                    "caveats": case.manifest.get("caveats", []),
                    "stand": case.manifest.get("stand", {}),
                    "harvest": case.manifest.get("harvest"),
                    "latest_run": runs[0] if runs else None,
                    "run_count": len(runs),
                }
            )
        return {"cases": items}

    @app.get("/api/cases/{case_id}")
    def case_detail(case_id: str) -> dict[str, Any]:
        case = _case_or_404(config, case_id)
        return {
            "case_id": case.case_id,
            "root": str(case.root),
            "manifest": case.manifest,
            "runs": list_runs(config.runs_root, case.case_id),
        }

    @app.post("/api/cases/{case_id}/validate")
    def case_validate(case_id: str) -> dict[str, Any]:
        case = _case_or_404(config, case_id)
        return validate_case(case)

    @app.post("/api/cases/{case_id}/run")
    def case_run(case_id: str) -> dict[str, Any]:
        case = _case_or_404(config, case_id)
        try:
            return manager.start(case)
        except RunError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/cases/{case_id}/runs")
    def runs(case_id: str) -> dict[str, Any]:
        _case_or_404(config, case_id)
        return {"runs": list_runs(config.runs_root, case_id)}

    @app.get("/api/cases/{case_id}/runs/{run_id}")
    def run_detail(case_id: str, run_id: str) -> dict[str, Any]:
        live = manager.get(run_id)
        if live is not None:
            return live
        try:
            return load_run(config.runs_root, case_id, run_id)
        except RunError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/cases/{case_id}/runs/{run_id}/events")
    def run_events(case_id: str, run_id: str) -> FileResponse:
        path = _run_dir(config, case_id, run_id) / "system" / "system_events.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Events file not found.")
        return FileResponse(path, media_type="application/json")

    @app.get("/api/cases/{case_id}/runs/{run_id}/summary")
    def run_summary(case_id: str, run_id: str) -> FileResponse:
        path = _run_dir(config, case_id, run_id) / "system" / "system_summary.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Summary file not found.")
        return FileResponse(path, media_type="application/json")

    @app.get("/api/cases/{case_id}/runs/{run_id}/scene.gltf")
    def run_scene(case_id: str, run_id: str) -> FileResponse:
        path = _run_dir(config, case_id, run_id) / "scene" / "scene.gltf"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Scene not found.")
        return FileResponse(path, media_type="model/gltf+json")

    @app.get("/api/cases/{case_id}/runs/{run_id}/scene.glb")
    def run_scene_glb(case_id: str, run_id: str) -> FileResponse:
        path = _run_dir(config, case_id, run_id) / "scene" / "scene.glb"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Scene not found.")
        return FileResponse(path, media_type="model/gltf-binary")

    @app.get("/api/cases/{case_id}/residual")
    def case_residual(case_id: str) -> dict[str, Any]:
        from fhops.tree_inventory import load_tree_inventory
        from sandbox.tree_lab.harvest import derive_residual, harvest_prescription

        case = _case_or_404(config, case_id)
        stand = load_tree_inventory(case.path("inventory"), metadata_path=case.path("metadata"))
        residual = derive_residual(stand, harvest_prescription(case))
        return {
            "schema_version": "fhops.tree_lab.residual.v1",
            "count": len(residual),
            "caveat": "Residual trees for visualization only; never processed.",
            "trees": [
                {
                    "tree_id": tree.tree_id,
                    "x": tree.x_m,
                    "y": tree.y_m,
                    "z": tree.elevation_m,
                    "dbh_cm": tree.dbh_cm,
                    "height_m": tree.height_m,
                    "crown_radius_m": tree.crown_radius_m,
                    "species_code": tree.species_code,
                }
                for tree in residual
            ],
        }

    @app.get("/api/cases/{case_id}/data")
    def case_data(case_id: str) -> dict[str, Any]:
        case = _case_or_404(config, case_id)
        validation = validate_case(case)
        metadata: dict[str, Any] = {}
        try:
            metadata = json.loads(case.path("metadata").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, CaseError):
            metadata = {}
        sample: list[dict[str, str]] = []
        try:
            with case.path("inventory").open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for index, row in enumerate(reader):
                    if index >= 12:
                        break
                    sample.append(dict(row))
        except (OSError, CaseError):
            sample = []
        scenario_text = ""
        try:
            scenario_text = case.path("scenario").read_text(encoding="utf-8")
        except (OSError, CaseError):
            scenario_text = ""
        return {
            "case_id": case.case_id,
            "manifest": case.manifest,
            "metadata": metadata,
            "inventory_sample": sample,
            "scenario_yaml": scenario_text,
            "validation": validation,
        }

    @app.get("/api/agent/status")
    def get_agent_status() -> dict[str, Any]:
        status = agent_status(config.workspace, model=config.agent_model)
        status["enabled"] = config.allow_agent
        status["candidates"] = list_candidates(config.cases_root)
        return status

    @app.post("/api/agent/run")
    def post_agent_run(request: AgentRunRequest) -> dict[str, Any]:
        if not config.allow_agent:
            raise HTTPException(
                status_code=403,
                detail="Agent is disabled; start the app with --allow-agent to enable it.",
            )
        try:
            return run_candidate_agent(
                request.message,
                workspace=config.workspace,
                cases_root=config.cases_root,
                enabled=True,
                timeout_s=config.agent_timeout_s,
                log_path=config.runs_root / "agent_log.jsonl",
                model=config.agent_model,
            )
        except AgentGuardError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/agent/candidates")
    def get_candidates() -> dict[str, Any]:
        return {"candidates": list_candidates(config.cases_root)}

    @app.post("/api/agent/candidates/{candidate_id}/validate")
    def post_candidate_validate(candidate_id: str) -> dict[str, Any]:
        candidate = _candidate_or_404(config, candidate_id)
        return validate_candidate(candidate)

    @app.post("/api/agent/candidates/{candidate_id}/accept")
    def post_candidate_accept(candidate_id: str) -> dict[str, Any]:
        candidate = _candidate_or_404(config, candidate_id)
        try:
            return accept_candidate(candidate, config.cases_root)
        except AgentGuardError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _candidate_or_404(config: ServiceConfig, candidate_id: str) -> Path:
        root = candidates_root(config.cases_root).resolve()
        candidate = (root / candidate_id).resolve()
        if root not in candidate.parents or not candidate.is_dir():
            raise HTTPException(status_code=404, detail=f"Unknown candidate {candidate_id!r}.")
        return candidate

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.is_file():
            return HTMLResponse("<h1>Tree Lab static assets are missing.</h1>", status_code=500)
        html = index_path.read_text(encoding="utf-8").replace("{{BUILD}}", build_id())
        return HTMLResponse(html)

    return app


def run(argv: list[str] | None = None) -> int:
    """Start the Tree Lab server with loopback defaults."""
    parser = argparse.ArgumentParser(description="Run the local FHOPS Tree Lab sandbox.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8801)
    parser.add_argument("--cases", type=Path, default=REPO_ROOT / "sandbox" / "cases")
    parser.add_argument("--runs", type=Path, default=REPO_ROOT / "sandbox" / "runs")
    parser.add_argument("--allow-agent", action="store_true")
    parser.add_argument("--agent-timeout", type=float, default=300.0)
    parser.add_argument(
        "--agent-model",
        default=DEFAULT_AGENT_MODEL,
        help="provider/model for opencode run --model (default: %(default)s).",
    )
    parser.add_argument(
        "--root-path",
        default="",
        help=(
            "URL prefix when served behind a path-prefixing proxy, e.g. "
            "/jupyterhub03/user/<user>/codeserver/proxy/8801"
        ),
    )
    args = parser.parse_args(argv)

    import uvicorn

    app = create_app(
        ServiceConfig(
            cases_root=args.cases,
            runs_root=args.runs,
            allow_agent=args.allow_agent,
            agent_timeout_s=args.agent_timeout,
            agent_model=args.agent_model or None,
            root_path=args.root_path,
        )
    )
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(run())
