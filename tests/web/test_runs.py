"""Tests for live run start, status, SSE, and control."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from fhops.web.app import ServiceConfig, create_app
from fhops.web.runs import RunRequest, build_command

FAKE_CLI = r"""
import json
import sys
import time
from pathlib import Path

args = sys.argv[1:]
def value(flag):
    return args[args.index(flag) + 1] if flag in args else None

if "--out-dir" in args:
    out = Path(value("--out-dir"))
elif "--out" in args:
    out = Path(value("--out")).parent
elif "--out-json" in args:
    out = Path(value("--out-json")).parent
else:
    out = Path.cwd()
out.mkdir(parents=True, exist_ok=True)
telemetry = Path(value("--telemetry-log")) if "--telemetry-log" in args else out / "telemetry.jsonl"
for step in range(1, 4):
    with telemetry.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"record_type": "step", "step": step, "objective": 100 - step, "best_objective": 100 - step}) + "\n")
    time.sleep(0.25)
with telemetry.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({"record_type": "run", "metrics": {"total_production": 97.0}}) + "\n")
if "solve-heur" in args or "solve-mip-operational" in args:
    (out / "assignments.csv").write_text(
        "machine_id,block_id,day,shift_id\nH1,b1,1,DAY\n", encoding="utf-8"
    )
(out / "summary.json").write_text(json.dumps({"status": "ok", "objective": 97}), encoding="utf-8")
"""

SLOW_CLI = r"""
import time
time.sleep(30)
"""


def _write_script(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _client(tmp_path: Path, script: Path) -> TestClient:
    (tmp_path / "scenario.yaml").write_text("name: test\n", encoding="utf-8")
    app = create_app(
        ServiceConfig(
            roots=[tmp_path / "runs"],
            host="127.0.0.1",
            workspace=tmp_path,
            cli_command=(sys.executable, str(script)),
        )
    )
    return TestClient(app)


def _wait_for(client: TestClient, run_id: str, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = client.get(f"/api/runs/{run_id}/status").json()
        if payload["finished"]:
            return payload
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def test_start_run_writes_manifest_and_telemetry(tmp_path: Path) -> None:
    client = _client(tmp_path, _write_script(tmp_path, "fake_cli.py", FAKE_CLI))
    response = client.post(
        "/api/runs",
        json={
            "domain": "operational",
            "run_type": "solve_heur",
            "scenario": "scenario.yaml",
            "options": {"iterations": 3, "seed": 1},
        },
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    status = _wait_for(client, run_id)
    assert status["status"] == "ok"
    run_dir = tmp_path / "runs" / run_id
    assert (run_dir / "run.json").exists()
    assert (run_dir / "telemetry.jsonl").exists()
    assert (run_dir / "summary.json").exists()
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "operational"
    assert manifest["status"] == "ok"


def test_events_stream_progress_and_done(tmp_path: Path) -> None:
    client = _client(tmp_path, _write_script(tmp_path, "fake_cli.py", FAKE_CLI))
    response = client.post(
        "/api/runs",
        json={
            "domain": "operational",
            "run_type": "solve_heur",
            "scenario": "scenario.yaml",
            "options": {"iterations": 3, "seed": 1},
        },
    )
    run_id = response.json()["run_id"]
    events = []
    with client.stream("GET", f"/api/runs/{run_id}/events") as stream:
        assert stream.status_code == 200
        for line in stream.iter_lines():
            if line:
                events.append(line)
            if "event: done" in line:
                break
    text = "\n".join(events)
    assert "event: progress" in text
    assert "event: done" in text
    assert "event: kpis" in text
    assert "event: assignment" in text
    assert "objective" in text
    assert client.get(f"/api/runs/{run_id}/events").status_code == 204


def test_control_pause_resume_stop(tmp_path: Path) -> None:
    client = _client(tmp_path, _write_script(tmp_path, "slow_cli.py", SLOW_CLI))
    response = client.post(
        "/api/runs",
        json={
            "domain": "operational",
            "run_type": "solve_heur",
            "scenario": "scenario.yaml",
            "options": {"iterations": 10, "seed": 1},
        },
    )
    run_id = response.json()["run_id"]
    assert (
        client.post(f"/api/runs/{run_id}/control", json={"action": "pause"}).json()["paused"]
        is True
    )
    assert (
        client.post(f"/api/runs/{run_id}/control", json={"action": "resume"}).json()["paused"]
        is False
    )
    stopped = client.post(f"/api/runs/{run_id}/control", json={"action": "stop"}).json()
    assert stopped["finished"] is False
    status = _wait_for(client, run_id)
    assert status["status"] == "stopped"


def test_invalid_run_request_is_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path, _write_script(tmp_path, "fake_cli.py", FAKE_CLI))
    missing = client.post(
        "/api/runs",
        json={
            "domain": "operational",
            "run_type": "solve_heur",
            "scenario": "missing.yaml",
        },
    )
    assert missing.status_code == 400
    bad_type = client.post(
        "/api/runs",
        json={
            "domain": "operational",
            "run_type": "haul_solve",
            "scenario": "scenario.yaml",
        },
    )
    assert bad_type.status_code == 400
    bad_option = client.post(
        "/api/runs",
        json={
            "domain": "operational",
            "run_type": "solve_heur",
            "scenario": "scenario.yaml",
            "options": {"iterations": 0},
        },
    )
    assert bad_option.status_code == 400


def test_unknown_run_events_is_404(tmp_path: Path) -> None:
    client = _client(tmp_path, _write_script(tmp_path, "fake_cli.py", FAKE_CLI))
    assert client.get("/api/runs/nope/events").status_code == 404


def test_scenario_outside_workspace_is_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path, _write_script(tmp_path, "fake_cli.py", FAKE_CLI))
    outside = tmp_path.parent / "outside.yaml"
    outside.write_text("name: outside\\n", encoding="utf-8")
    response = client.post(
        "/api/runs",
        json={
            "domain": "operational",
            "run_type": "solve_heur",
            "scenario": "../outside.yaml",
        },
    )
    assert response.status_code == 400


def test_start_run_all_three_domains(tmp_path: Path) -> None:
    client = _client(tmp_path, _write_script(tmp_path, "fake_cli.py", FAKE_CLI))
    cases = [
        ("operational", "solve_heur", {"iterations": 3, "seed": 1}),
        ("hauling", "haul_solve", {"day": 1, "solver": "sa", "iterations": 3}),
        ("tactical_operational", "tactical_operational", {"time_limit": 10}),
    ]
    for domain, run_type, options in cases:
        response = client.post(
            "/api/runs",
            json={
                "domain": domain,
                "run_type": run_type,
                "scenario": "scenario.yaml",
                "options": options,
            },
        )
        assert response.status_code == 200, response.text
        run_id = response.json()["run_id"]
        status = _wait_for(client, run_id)
        assert status["status"] == "ok", (domain, status)
        manifest = json.loads((tmp_path / "runs" / run_id / "run.json").read_text(encoding="utf-8"))
        assert manifest["domain"] == domain
        assert manifest["run_type"] == run_type


def test_build_command_covers_all_three_domains(tmp_path: Path) -> None:
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text("name: test\\n", encoding="utf-8")
    out = tmp_path / "out"

    operational = build_command(
        RunRequest(
            domain="operational",
            run_type="solve_heur",
            scenario="scenario.yaml",
            options={"iterations": 12, "seed": 3},
        ),
        scenario=scenario,
        out_dir=out,
        cli_command=("fhops",),
    )
    assert operational[:2] == ["fhops", "solve-heur"]
    assert "--telemetry-log" in operational
    assert operational[operational.index("--iters") + 1] == "12"

    hauling = build_command(
        RunRequest(
            domain="hauling",
            run_type="haul_solve",
            scenario="scenario.yaml",
            options={"day": 2, "solver": "mip", "iterations": 20},
        ),
        scenario=scenario,
        out_dir=out,
        cli_command=("fhops",),
    )
    assert hauling[:3] == ["fhops", "haul", "solve"]
    assert hauling[hauling.index("--day") + 1] == "2"
    assert hauling[hauling.index("--solver") + 1] == "mip"

    tactical = build_command(
        RunRequest(
            domain="tactical_operational",
            run_type="tactical_operational",
            scenario="scenario.yaml",
            options={"time_limit": 30},
        ),
        scenario=scenario,
        out_dir=out,
        cli_command=("fhops",),
    )
    assert tactical[:3] == ["fhops", "plan", "tactical-operational"]
    assert tactical[tactical.index("--out-json") + 1] == str(out / "summary.json")
    assert tactical[tactical.index("--time-limit") + 1] == "30"
