#!/usr/bin/env python3
"""Compute or verify the SoftwareX ``assets_hash`` recorded in ``benchmark_runs.log``.

Recipe ``v2`` (#144), run from the repository root:

1. File set: every file under ``docs/softwarex/assets/`` that git would commit, i.e.
   ``git ls-files --cached --others --exclude-standard -- docs/softwarex/assets`` (tracked files
   plus new files that are not git-ignored), without files missing from the working tree and
   without ``docs/softwarex/assets/benchmark_runs.log`` itself. Without a git checkout (e.g. an
   unpacked sdist, which ships exactly the tracked files) the set is every file under
   ``docs/softwarex/assets/`` except the log.
2. One ``sha256sum`` line per file, ``<hex digest><two spaces><repo-relative POSIX path>\\n``,
   ordered by the path's bytes (``LC_ALL=C``).
3. ``assets_hash`` is the SHA-256 hex digest of the concatenated lines.

Equivalent shell (clean checkout)::

    git ls-files -z --cached --others --exclude-standard -- docs/softwarex/assets \\
      | grep -zv '^docs/softwarex/assets/benchmark_runs.log$' \\
      | LC_ALL=C sort -zu | xargs -0 sha256sum | sha256sum

Equivalent shell (unpacked sdist, no ``.git``)::

    find docs/softwarex/assets -type f ! -path docs/softwarex/assets/benchmark_runs.log -print0 \\
      | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum

``verify`` recomputes the hash and compares it with the last log entry that records an
``assets_hash``; that entry must declare ``hash_recipe: v2`` (entries without the field used the
legacy recipe, see the manuscript README).
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

ASSETS_REL = "docs/softwarex/assets"
LOG_REL = f"{ASSETS_REL}/benchmark_runs.log"
RECIPE = "v2"


def _git_listing(repo_root: Path) -> list[str] | None:
    """Return the git file listing under the assets directory, or ``None`` outside a checkout."""
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if inside.returncode != 0:
        return None
    if Path(inside.stdout.strip()).resolve() != repo_root.resolve():
        # A parent repository (e.g. an sdist unpacked inside another checkout) is not ours.
        return None
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", ASSETS_REL],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def asset_files(repo_root: Path) -> list[str]:
    """Return the repo-relative POSIX paths covered by the hash, sorted by their bytes."""
    listing = _git_listing(repo_root)
    if listing is None:
        base = repo_root / ASSETS_REL
        listing = [p.relative_to(repo_root).as_posix() for p in base.rglob("*") if p.is_file()]
    files = {
        rel for rel in listing if rel != LOG_REL and (repo_root / rel).is_file()
    }  # deleted-but-tracked files will not be committed
    for rel in files:
        if "\\" in rel or "\n" in rel:
            raise ValueError(f"Unsupported character in asset path (sha256sum escapes it): {rel!r}")
    return sorted(files, key=lambda rel: rel.encode("utf-8"))


def manifest(repo_root: Path) -> str:
    """Return the ``sha256sum`` listing the hash is computed over."""
    lines = []
    for rel in asset_files(repo_root):
        digest = hashlib.sha256((repo_root / rel).read_bytes()).hexdigest()
        lines.append(f"{digest}  {rel}\n")
    return "".join(lines)


def assets_hash(repo_root: Path) -> str:
    return hashlib.sha256(manifest(repo_root).encode("utf-8")).hexdigest()


def parse_log(text: str) -> list[dict[str, str]]:
    """Split ``benchmark_runs.log`` into entries (``key: value`` lines separated by ``----``)."""
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in text.splitlines():
        if line.strip() == "----":
            if current:
                entries.append(current)
            current = {}
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            current[key.strip()] = value.strip()
    if current:
        entries.append(current)
    return entries


def verify(repo_root: Path, log_path: Path) -> tuple[bool, str]:
    entries = [e for e in parse_log(log_path.read_text(encoding="utf-8")) if "assets_hash" in e]
    if not entries:
        return False, f"no entry with assets_hash in {log_path}"
    entry = entries[-1]
    label = entry.get("run_started") or entry.get("audit_note") or "?"
    recipe = entry.get("hash_recipe")
    if recipe != RECIPE:
        return False, (
            f"last entry ({label}) uses hash recipe {recipe or 'v1 (legacy)'}; only {RECIPE} "
            "entries can be verified"
        )
    actual = assets_hash(repo_root)
    expected = entry["assets_hash"]
    if actual != expected:
        return False, f"MISMATCH for entry {label}: logged {expected}, recomputed {actual}"
    return True, f"OK: entry {label} assets_hash {actual} ({len(asset_files(repo_root))} files)"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="FHOPS repository (or unpacked sdist) root.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("compute", help="Print the assets hash.")
    sub.add_parser("list", help="Print the sha256sum manifest the hash is computed over.")
    verify_parser = sub.add_parser("verify", help="Check the last log entry's assets_hash.")
    verify_parser.add_argument(
        "--log", type=Path, default=None, help=f"Log file (default: <repo-root>/{LOG_REL})."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    if args.command == "compute":
        print(assets_hash(repo_root))
        return 0
    if args.command == "list":
        sys.stdout.write(manifest(repo_root))
        return 0
    ok, message = verify(repo_root, args.log or repo_root / LOG_REL)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
