"""Public demo wrapper: FHOPS serious game + Tree Lab 3D sandbox."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.routing import Route

from fhops.web.app import ServiceConfig, create_app
from sandbox.tree_lab.app import ServiceConfig as TreeLabConfig
from sandbox.tree_lab.app import create_app as create_tree_lab_app

ROOT = Path(__file__).resolve().parent
LANDING = ROOT / "demo.html"

app: FastAPI = create_app(
    ServiceConfig(
        roots=[ROOT / "build"],
        workspace=ROOT,
        host="127.0.0.1",
        port=8780,
        title="FHOPS Public Demo",
        allow_agent=True,
        game_levels=[
            ROOT / "examples/game/levels/mkrf_684/level.yaml",
            ROOT / "examples/game/levels/gavin_1032/level.yaml",
            ROOT / "examples/game/levels/kc_57254551/level.yaml",
        ],
        game_precomputes=[
            ROOT / "examples/game/precomputed/mkrf_684.json",
            ROOT / "examples/game/precomputed/gavin_1032.json",
            ROOT / "examples/game/precomputed/kc_57254551.json",
        ],
        game_session_store=ROOT / "build" / "demo_game_sessions.json",
        game_explanation_cache=ROOT / "build" / "demo_explanations.json",
    )
)

# Fancy Tree Lab sandbox, mounted at /sandbox. Its assets and API use relative paths.
tree_lab_app = create_tree_lab_app(
    TreeLabConfig(
        cases_root=ROOT / "sandbox" / "cases",
        runs_root=ROOT / "sandbox" / "runs",
        workspace=ROOT,
        allow_agent=True,
        root_path="",
    )
)
app.mount("/sandbox-v20261031i", tree_lab_app)
app.mount("/sandbox", tree_lab_app)

# Simple app-level public-demo guardrails. Nginx should still enforce its own
# request limits; these caps keep a direct loopback client from bypassing them.
_RATE_WINDOW_S = 60.0
_RATE_MAX_REQUESTS = 300
_MAX_BODY_BYTES = 64 * 1024
_request_log: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def public_demo_limits(request: Request, call_next: Any) -> Any:
    """Apply coarse public-demo rate and body-size limits."""
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > _MAX_BODY_BYTES
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(
                    {"detail": "Public demo request body exceeds 64 KiB."},
                    status_code=413,
                )
    forwarded = request.headers.get("x-forwarded-for", "")
    client = (forwarded.split(",")[0].strip() if forwarded else "") or (
        request.client.host if request.client else "unknown"
    )
    now = time.monotonic()
    bucket = _request_log[client]
    while bucket and now - bucket[0] > _RATE_WINDOW_S:
        bucket.popleft()
    if len(bucket) >= _RATE_MAX_REQUESTS:
        return JSONResponse(
            {"detail": "Public demo rate limit reached; try again in a minute."},
            status_code=429,
        )
    bucket.append(now)
    response = await call_next(request)
    response.headers.setdefault("X-FHOPS-Demo", "public-experimental")
    return response


@app.middleware("http")
async def no_store_public_demo(request: Request, call_next: Any) -> Any:
    """Never let browsers cache the demo shell or its modules."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith(("/game", "/sandbox", "/static")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        # Clear old module caches when a document is opened, so a stale
        # viewer.js cannot survive a normal reload or hard refresh.
        if path in (
            "/",
            "/demo",
            "/game",
            "/sandbox",
            "/sandbox/",
            "/sandbox-v20261031i",
            "/sandbox-v20261031i/",
            "/sandbox-v20261031c",
            "/sandbox-v20261031c/",
            "/sandbox-v20261031d",
            "/sandbox-v20261031d/",
            "/sandbox-v20261031e",
            "/sandbox-v20261031e/",
            "/sandbox-v20261031f",
            "/sandbox-v20261031f/",
            "/sandbox-v20261031g",
            "/sandbox-v20261031g/",
            "/sandbox-v20261031h",
            "/sandbox-v20261031h/",
        ):
            response.headers["Clear-Site-Data"] = '"cache"'
    return response


def _landing(_request: Request) -> FileResponse:
    return FileResponse(LANDING, headers={"Cache-Control": "no-store"})


async def _sandbox_redirect(_request: Request) -> RedirectResponse:
    return RedirectResponse("/sandbox-v20261031i/", status_code=302)


app.router.routes.insert(0, Route("/sandbox", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/sandbox/", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/sandbox-v20261031c", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/sandbox-v20261031c/", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/sandbox-v20261031d", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/sandbox-v20261031d/", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/sandbox-v20261031e", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/sandbox-v20261031e/", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/sandbox-v20261031f", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/sandbox-v20261031f/", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/sandbox-v20261031g", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/sandbox-v20261031g/", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/sandbox-v20261031h", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/sandbox-v20261031h/", _sandbox_redirect, methods=["GET"]))
app.router.routes.insert(0, Route("/", _landing, methods=["GET"]))
app.router.routes.insert(0, Route("/demo", _landing, methods=["GET"]))
