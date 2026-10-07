"""Tests for the SoftwareX asset provenance scripts (#144): hash recipe, recorded paths, Table 5."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "docs" / "softwarex" / "manuscript" / "scripts"
ASSETS = REPO_ROOT / "docs" / "softwarex" / "assets"
sys.path.insert(0, str(SCRIPTS))

import asset_hash  # noqa: E402
import build_tables  # noqa: E402
import relativize_asset_paths  # noqa: E402

HAS_GIT = shutil.which("git") is not None
HAS_SHA256SUM = shutil.which("sha256sum") is not None


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _make_repo(tmp_path: Path, *, init_git: bool) -> Path:
    repo = tmp_path / "repo"
    assets = repo / "docs" / "softwarex" / "assets"
    (assets / "data" / "tuning" / "telemetry" / "steps").mkdir(parents=True)
    (assets / "data" / "b").mkdir(parents=True)
    (assets / "data" / "B.csv").write_text("x\n1\n", encoding="utf-8")
    (assets / "data" / "a.csv").write_text("a\n", encoding="utf-8")
    (assets / "data" / "b" / "z.json").write_text("{}\n", encoding="utf-8")
    (assets / "benchmark_runs.log").write_text("run_started: x\n----\n", encoding="utf-8")
    if init_git:
        (repo / ".gitignore").write_text(
            "docs/softwarex/assets/data/tuning/telemetry/steps/\n", encoding="utf-8"
        )
        _git(repo, "init", "-q")
        _git(repo, "add", "-A")
        _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        steps = assets / "data" / "tuning" / "telemetry" / "steps" / "run.jsonl"
        steps.write_text("ignored\n", encoding="utf-8")
        # Regenerated but not yet committed: covered by the hash.
        (assets / "data" / "new.txt").write_text("new\n", encoding="utf-8")
    return repo


@pytest.mark.skipif(not (HAS_GIT and HAS_SHA256SUM), reason="needs git and sha256sum")
def test_asset_hash_matches_documented_shell_recipe(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, init_git=True)
    files = asset_hash.asset_files(repo)
    assert files == [
        "docs/softwarex/assets/data/B.csv",
        "docs/softwarex/assets/data/a.csv",
        "docs/softwarex/assets/data/b/z.json",
        "docs/softwarex/assets/data/new.txt",
    ]  # LC_ALL=C order, ignored steps/ and the log excluded, untracked new file included
    shell = (
        "git ls-files -z --cached --others --exclude-standard -- docs/softwarex/assets "
        "| grep -zv '^docs/softwarex/assets/benchmark_runs.log$' "
        "| LC_ALL=C sort -zu | xargs -0 sha256sum | sha256sum"
    )
    out = subprocess.run(shell, shell=True, cwd=repo, check=True, capture_output=True, text=True)
    assert out.stdout.split()[0] == asset_hash.assets_hash(repo)


@pytest.mark.skipif(not HAS_SHA256SUM, reason="needs sha256sum")
def test_asset_hash_without_git_matches_sdist_recipe(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, init_git=False)
    shell = (
        "find docs/softwarex/assets -type f ! -path docs/softwarex/assets/benchmark_runs.log "
        "-print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum"
    )
    out = subprocess.run(shell, shell=True, cwd=repo, check=True, capture_output=True, text=True)
    assert out.stdout.split()[0] == asset_hash.assets_hash(repo)


@pytest.mark.skipif(not HAS_GIT, reason="needs git")
def test_asset_hash_skips_deleted_tracked_files_and_ignores_log(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, init_git=True)
    before = asset_hash.assets_hash(repo)
    log = repo / asset_hash.LOG_REL
    log.write_text(log.read_text(encoding="utf-8") + "audit_note: y\n----\n", encoding="utf-8")
    assert asset_hash.assets_hash(repo) == before
    (repo / "docs/softwarex/assets/data/a.csv").unlink()
    assert "docs/softwarex/assets/data/a.csv" not in asset_hash.asset_files(repo)


def test_verify_checks_last_entry_and_rejects_legacy_recipe(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, init_git=False)
    log = repo / asset_hash.LOG_REL
    log.write_text("run_started: old\nassets_hash: abc\n----\n", encoding="utf-8")
    ok, message = asset_hash.verify(repo, log)
    assert not ok and "legacy" in message
    good = asset_hash.assets_hash(repo)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"audit_note: now\nhash_recipe: v2\nassets_hash: {good}\nnote: a: b\n----\n")
    assert asset_hash.verify(repo, log)[0]
    (repo / "docs/softwarex/assets/data/a.csv").write_text("changed\n", encoding="utf-8")
    ok, message = asset_hash.verify(repo, log)
    assert not ok and "MISMATCH" in message
    assert asset_hash.parse_log(log.read_text(encoding="utf-8"))[-1]["note"] == "a: b"


def test_committed_assets_hash_verifies() -> None:
    ok, message = asset_hash.verify(REPO_ROOT, REPO_ROOT / asset_hash.LOG_REL)
    assert ok, message


def test_relativize_rewrites_text_json_escaped_and_sqlite(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    old = "/home/someone/old-checkout"
    (root / "summary.csv").write_text(
        f"scenario_path\n{old}/examples/tiny7/scenario.yaml\n", encoding="utf-8"
    )
    (root / "summary.json").write_text(
        json.dumps({"p": f"{old}/examples/x.yaml"}).replace("/", "\\/"), encoding="utf-8"
    )
    (root / "figure.png").write_bytes(b"\x89PNG" + old.encode())
    db = root / "runs.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE runs (run_id TEXT, scenario_path TEXT, seed INTEGER)")
    conn.execute("INSERT INTO runs VALUES ('r1', ?, 1)", (f"{old}/examples/med42/scenario.yaml",))
    conn.execute("INSERT INTO runs VALUES ('r2', NULL, 2)")
    conn.commit()
    conn.close()

    assert set(relativize_asset_paths.check(root)) == {
        root / "summary.csv",
        root / "summary.json",
        db,
    }
    assert relativize_asset_paths.main([str(root), "--check"]) == 1
    assert relativize_asset_paths.main([str(root), "--prefix", old]) == 0

    assert (root / "summary.csv").read_text(encoding="utf-8").splitlines()[1] == (
        "examples/tiny7/scenario.yaml"
    )
    assert json.loads((root / "summary.json").read_text(encoding="utf-8")) == {
        "p": "examples/x.yaml"
    }
    rows = sqlite3.connect(db).execute("SELECT run_id, scenario_path FROM runs").fetchall()
    assert rows == [("r1", "examples/med42/scenario.yaml"), ("r2", None)]
    assert (root / "figure.png").read_bytes().endswith(old.encode())  # binary untouched
    assert relativize_asset_paths.check(root) == {}


def test_relativize_check_ignores_relative_paths(tmp_path: Path) -> None:
    root = tmp_path / "assets"
    root.mkdir()
    (root / "a.txt").write_text(
        "docs/softwarex/assets/data/tmp/x.yaml examples/home/y.csv operators=(a:1.0)\n",
        encoding="utf-8",
    )
    assert relativize_asset_paths.check(root) == {}


def test_repo_relative(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "examples").mkdir(parents=True)
    assert relativize_asset_paths.repo_relative(repo / "examples" / "a.yaml", repo) == (
        "examples/a.yaml"
    )
    assert relativize_asset_paths.repo_relative("examples/a.yaml", repo) == "examples/a.yaml"
    outside = tmp_path / "elsewhere.yaml"
    assert relativize_asset_paths.repo_relative(outside, repo) == str(outside)


def test_committed_assets_record_no_absolute_paths() -> None:
    assert relativize_asset_paths.check(ASSETS) == {}


def test_format_budget_and_compact_settings() -> None:
    assert build_tables.format_budget({"trials_total": 8, "iters_per_trial": 120}) == (
        r"8 trials $\times$ 120 iters"
    )
    assert build_tables.format_budget({"total_configs": 4, "iters_per_config": 120}) == (
        r"4 configs $\times$ 120 iters"
    )
    assert build_tables.format_budget({"runs_total": 1, "iters_per_run": 900, "tier": "s"}) == (
        r"1 run $\times$ 900 iters"
    )
    with pytest.raises(ValueError):
        build_tables.format_budget({"tier": "short"})
    assert build_tables.compact_settings(
        "batch_size=3; iters=120; operators=(block_insertion:1.4448867651404431, swap:0.6)"
    ) == ("batch_size=3; operator weights block_insertion=1.44, swap=0.6")


def test_tuning_leaderboard_shows_budget_for_every_row(tmp_path: Path) -> None:
    data = ASSETS / "data"
    default_sa = build_tables.build_solver_performance_table(data / "benchmarks", tmp_path)
    sa_iters = build_tables.default_sa_iterations(data / "benchmarks")
    assert sa_iters == {"tiny7": 8000, "small21": 4000, "med42": 20000, "synthetic_small": 6000}
    build_tables.build_tuning_leaderboard_table(
        data / "tuning" / "tuner_comparison.csv",
        data / "tuning" / "tuner_report.csv",
        default_sa,
        tmp_path,
        sa_default_iters=sa_iters,
    )
    table = pd.read_csv(tmp_path / "tuning_leaderboard.csv")
    assert list(table.columns) == [
        "Scenario",
        "Tuner",
        "Best Objective",
        r"$\Delta$ vs SA default",
        "Mean Runtime (s)",
        "Budget",
        "Key Settings",
    ]
    assert table["Budget"].str.contains(r"iters$").all()
    assert table["Key Settings"].notna().all()
    small21 = table[table["Scenario"].str.startswith("Small21")].iloc[0]
    assert small21["Tuner"] == "ILS"
    assert small21["Budget"] == r"1 run $\times$ 160 iters"
    tex = (tmp_path / "tuning_leaderboard.tex").read_text(encoding="utf-8")
    assert "SA default benchmark objective" in tex
    assert "8000 (Tiny7), 4000 (Small21), 20000 (Med42), 6000 (Synthetic-small)" in tex
    # The committed tables are this rendering.
    for name in ("tuning_leaderboard.csv", "tuning_leaderboard.tex", "solver_performance.csv"):
        assert (tmp_path / name).read_text(encoding="utf-8") == (data / "tables" / name).read_text(
            encoding="utf-8"
        )
