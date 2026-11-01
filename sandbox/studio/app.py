"""FastAPI entry point for the FHOPS Scenario Studio prototype.

The Studio is intentionally separate from the Tree Lab runtime app: it reads
immutable case fixtures, writes editable project overlays under ``build``, and
does not alter the public demo. Run it with::

    PYTHONPATH=src:. python -m sandbox.studio.app --port 8790
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sandbox.studio.projects import (
    POLICY_PRESETS,
    StudioError,
    create_project,
    duplicate_project,
    import_project,
    promote_run,
    list_projects,
    load_project,
    materialize_case,
    project_dataset,
    project_path,
    save_project,
)
from sandbox.tree_lab.cases import CaseError, discover_cases, load_case
from sandbox.tree_lab.runner import RunError, run_case

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
TREE_LAB_STATIC = REPO_ROOT / "sandbox" / "tree_lab" / "static"


@dataclass(slots=True)
class StudioConfig:
    """Runtime configuration for the Studio service."""

    cases_root: Path
    projects_root: Path
    workspace: Path = REPO_ROOT


def _case(config: StudioConfig, case_id: str):
    try:
        case = load_case(config.cases_root / case_id)
    except CaseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if case.case_id != case_id:
        raise HTTPException(status_code=404, detail=f"Unknown case {case_id!r}.")
    return case


def create_app(config: StudioConfig) -> FastAPI:
    """Build the Studio FastAPI application."""
    app = FastAPI(title="FHOPS Scenario Studio", version="0.1.0")

    @app.middleware("http")
    async def no_store(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith(("/static", "/api/")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "fhops-scenario-studio",
            "projects_root": str(config.projects_root),
            "cases": len(discover_cases(config.cases_root)),
        }

    @app.get("/api/policies")
    def policies() -> dict[str, Any]:
        return {"presets": POLICY_PRESETS}

    @app.get("/api/cases")
    def cases() -> dict[str, Any]:
        items = []
        for case in discover_cases(config.cases_root):
            items.append(
                {
                    "case_id": case.case_id,
                    "label": case.label,
                    "block_id": case.manifest.get("block_id"),
                    "stand": case.manifest.get("stand", {}),
                    "provenance": case.manifest.get("provenance", {}),
                    "caveats": case.manifest.get("caveats", []),
                    "system_args": case.manifest.get("system_args", {}),
                }
            )
        return {"cases": items}

    @app.get("/api/projects")
    def projects() -> dict[str, Any]:
        return {"projects": list_projects(config.projects_root)}

    @app.post("/api/projects")
    async def create(request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
            case_id = str(payload.get("case_id", ""))
            project = create_project(_case(config, case_id))
            save_project(config.projects_root, project)
        except (StudioError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return project

    @app.get("/api/projects/{project_id}")
    def project(project_id: str) -> dict[str, Any]:
        try:
            return load_project(config.projects_root, project_id)
        except StudioError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/projects/{project_id}/dataset")
    def dataset(project_id: str) -> dict[str, Any]:
        try:
            project = load_project(config.projects_root, project_id)
            case = _case(config, str(project.get("base_case_id", "")))
            return project_dataset(case, project)
        except (StudioError, CaseError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/api/projects/{project_id}")
    async def update(project_id: str, request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
            if str(payload.get("project_id", "")) != project_id:
                raise StudioError("Project id does not match the URL.")
            return save_project(config.projects_root, payload)
        except (StudioError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/projects/{project_id}/duplicate")
    def duplicate(project_id: str) -> dict[str, Any]:
        try:
            return duplicate_project(
                config.projects_root, load_project(config.projects_root, project_id)
            )
        except StudioError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/projects/import")
    async def import_project_endpoint(request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
            base_case_id = str(payload.get("base_case_id", ""))
            _case(config, base_case_id)
            return import_project(config.projects_root, payload)
        except (StudioError, CaseError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/projects/{project_id}/runs/{run_id}/promote")
    def promote(project_id: str, run_id: str) -> dict[str, str]:
        try:
            project = load_project(config.projects_root, project_id)
            return promote_run(config.projects_root, project, run_id)
        except StudioError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/projects/{project_id}")
    def delete(project_id: str) -> dict[str, Any]:
        try:
            path = project_path(config.projects_root, project_id)
        except StudioError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        project_file = path / "project.json"
        if not project_file.is_file():
            raise HTTPException(status_code=404, detail="Unknown project.")
        project_file.unlink()
        return {"deleted": project_id}

    @app.post("/api/projects/{project_id}/run")
    def run_project(project_id: str) -> dict[str, Any]:
        try:
            project = load_project(config.projects_root, project_id)
            base = _case(config, str(project.get("base_case_id", "")))
            derived = materialize_case(config.projects_root, project, base)
            run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            runs_root = project_path(config.projects_root, project_id) / "runs"
            record = run_case(derived, runs_root, run_id=run_id)
            return record
        except (StudioError, CaseError, RunError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _run_path(project_id: str, run_id: str) -> Path:
        if "/" in run_id or ".." in run_id:
            raise HTTPException(status_code=400, detail="Invalid run id.")
        path = project_path(config.projects_root, project_id) / "runs" / run_id
        if not path.is_dir():
            raise HTTPException(status_code=404, detail="Unknown run.")
        return path

    @app.get("/api/projects/{project_id}/runs")
    def runs(project_id: str) -> dict[str, Any]:
        root = project_path(config.projects_root, project_id) / "runs"
        items = []
        if root.is_dir():
            for path in sorted(root.iterdir(), reverse=True):
                record = path / "run.json"
                if record.is_file():
                    try:
                        payload = json.loads(record.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    items.append(payload)
        return {"runs": items}

    @app.get("/api/projects/{project_id}/runs/{run_id}/events")
    def run_events(project_id: str, run_id: str) -> FileResponse:
        path = _run_path(project_id, run_id) / "system" / "system_events.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Run events not found.")
        return FileResponse(path, media_type="application/json")

    @app.get("/api/projects/{project_id}/runs/{run_id}/summary")
    def run_summary(project_id: str, run_id: str) -> FileResponse:
        path = _run_path(project_id, run_id) / "system" / "system_summary.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Run summary not found.")
        return FileResponse(path, media_type="application/json")

    @app.get("/api/projects/{project_id}/runs/{run_id}/scene.gltf")
    def run_scene(project_id: str, run_id: str) -> FileResponse:
        path = _run_path(project_id, run_id) / "scene" / "scene.gltf"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Run scene not found.")
        return FileResponse(path, media_type="model/gltf+json")

    @app.get("/replay")
    def replay() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "studio_replay.html", headers={"Cache-Control": "no-store"}
        )

    @app.get("/3d")
    def edit_3d() -> FileResponse:
        return FileResponse(STATIC_DIR / "studio_3d.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/projects/{project_id}/project.json")
    def project_file(project_id: str) -> FileResponse:
        try:
            path = project_path(config.projects_root, project_id) / "project.json"
        except StudioError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Unknown project.")
        return FileResponse(path, media_type="application/json", filename=f"{project_id}.json")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "studio.html", headers={"Cache-Control": "no-store"})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.mount("/lab", StaticFiles(directory=TREE_LAB_STATIC), name="tree-lab")
    return app


def run(argv: list[str] | None = None) -> int:
    """Run the Studio development server."""
    parser = argparse.ArgumentParser(description="Run the FHOPS Scenario Studio.")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)
    import uvicorn

    config = StudioConfig(
        cases_root=REPO_ROOT / "sandbox" / "cases",
        projects_root=REPO_ROOT / "build" / "studio_projects",
    )
    uvicorn.run(create_app(config), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
