"""Hydrology documentation checker tests (P18.4)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[1]


def _module() -> ModuleType:
    path = REPO / "scripts" / "check_hydrology_docs.py"
    spec = importlib.util.spec_from_file_location("check_hydrology_docs", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the hydrology docs checker.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docs_checker_passes_on_repository() -> None:
    checker = _module()
    assert checker.check_doc_references(REPO) == []
    assert checker.check_schema_mentions(REPO) == []


def test_docs_checker_detects_broken_local_reference(tmp_path: Path) -> None:
    checker = _module()
    doc = tmp_path / "page.rst"
    doc.write_text(":doc:`missing-page`\n", encoding="utf-8")
    errors = checker.check_doc_references(tmp_path, files=(Path("page.rst"),))
    assert any("unresolved" in error for error in errors)


def test_docs_checker_detects_stale_schema(tmp_path: Path) -> None:
    checker = _module()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "module.py").write_text("", encoding="utf-8")
    docs = tmp_path / "docs" / "reference"
    docs.mkdir(parents=True)
    (docs / "hydrology_contract_index.rst").write_text(
        "`fhops.hydrology.missing.v1`\n",
        encoding="utf-8",
    )
    errors = checker.check_schema_mentions(tmp_path)
    assert any("absent from src" in error for error in errors)
