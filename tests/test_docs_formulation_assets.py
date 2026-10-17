"""Drift checks for the canonical operational MILP formulation and its generated includes.

The Markdown source is rendered to TeX and RST by
``docs/softwarex/manuscript/scripts/export_docs_assets.py`` (pandoc). These checks run without
pandoc: they verify that the labels and the Pyomo names of the equation-to-code mapping appear
in all three files and that every mapped ``model.<name>`` exists in the MILP code.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "docs/softwarex/manuscript/sections/includes/fhops_operational_formulation.md"
TEX = MD.with_suffix(".tex")
RST = ROOT / "docs/includes/softwarex/fhops_operational_formulation.rst"
MILP = ROOT / "src/fhops/model/milp"

LABELS = [
    "OBJ",
    "OBJ2",
    "INIT",
    "D1",
    *(f"E{i}" for i in range(1, 14) if i != 8),
    "E8a",
    "E8b",
    "E8c",
]


def _model_names(text: str) -> set[str]:
    return set(re.findall(r"(?<![\w.])model\.([A-Za-z_]+)", text.replace("\\_", "_")))


def test_every_label_has_a_mapping_row_and_is_rendered() -> None:
    md = MD.read_text(encoding="utf-8")
    tex = TEX.read_text(encoding="utf-8")
    rst = RST.read_text(encoding="utf-8")
    for label in LABELS:
        assert f"| **{label}** |" in md, f"no mapping row for {label}"
        assert f"\\textbf{{{label}}}" in tex, f"{label} missing from the TeX include"
        assert f"**{label}**" in rst, f"{label} missing from the RST include"


def test_generated_includes_match_the_markdown_mapping() -> None:
    names = _model_names(MD.read_text(encoding="utf-8"))
    assert names, "mapping lists no Pyomo names"
    assert _model_names(TEX.read_text(encoding="utf-8")) == names
    assert _model_names(RST.read_text(encoding="utf-8")) == names


def test_mapped_pyomo_names_exist_in_the_milp_code() -> None:
    code = "".join(
        (MILP / name).read_text(encoding="utf-8")
        for name in ("operational.py", "driver.py", "data.py")
    )
    defined = set(re.findall(r"model\.([A-Za-z_]+)\s*=", code))
    missing = sorted(_model_names(MD.read_text(encoding="utf-8")) - defined)
    assert not missing, f"mapping cites Pyomo components the code does not define: {missing}"
