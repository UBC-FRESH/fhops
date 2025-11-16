"""Parse Appendix 11 statistical metadata into JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pdfplumber

PDF_PATH = Path("notes/reference/arnvik-w-20240926.pdf")
OUTPUT = Path("notes/reference/arnvik_tables/appendix11/statistics.json")

PAGE_RANGE = range(137, 152)  # zero-based indexes covering pages 138-152

HEADER_PREFIX = "Author(s)"
PUBLICATION_RE = re.compile(r"^(.*?\(\d{4}[a-z]?\))\s+(.*)$")


def iter_lines() -> list[str]:
    lines: list[str] = []
    with pdfplumber.open(PDF_PATH) as pdf:
        for idx in PAGE_RANGE:
            text = pdf.pages[idx].extract_text() or ""
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("Appendix 11") or line.startswith("Type of observational unit"):
                    continue
                if line.isdigit():
                    continue
                lines.append(line)
    return lines


def looks_observation_token(token: str) -> bool:
    return bool(re.match(r"^[\d/.,-]+$", token))


def is_significance_token(token: str, already_started: bool) -> bool:
    if token in {"SV", "SS"}:
        return True
    if token.startswith("P"):
        return True
    if token.startswith("<") or token.startswith(">"):
        return True
    if token in {"=", "<=", ">="}:
        return True
    if token == "-" and not already_started:
        return True
    return False


def parse_statistics() -> dict[str, dict[str, str]]:
    lines = iter_lines()
    data: dict[str, dict[str, str]] = {}
    current_pub: str | None = None

    for line in lines:
        if line.startswith(HEADER_PREFIX):
            continue
        match = PUBLICATION_RE.match(line)
        if match:
            current_pub = match.group(1)
            remainder = match.group(2)
        else:
            if current_pub is None:
                continue
            remainder = line
        tokens = remainder.split()
        if not tokens:
            continue
        nr = tokens.pop(0)
        if not tokens:
            continue
        observational_unit = tokens.pop(0)
        observations_tokens: list[str] = []
        while tokens and looks_observation_token(tokens[0]):
            observations_tokens.append(tokens.pop(0))
        observations = " ".join(observations_tokens) or "-"
        if len(tokens) < 4:
            continue
        f_value = tokens.pop()
        significance_tokens: list[str] = []
        while len(tokens) > 2 and is_significance_token(tokens[-1], bool(significance_tokens)):
            significance_tokens.insert(0, tokens.pop())
        significance = " ".join(significance_tokens) or "-"
        if len(tokens) < 2:
            continue
        r_squared_adj = tokens.pop()
        r_squared = tokens.pop()
        structure = " ".join(tokens).strip()
        data[f"{current_pub} model {nr}"] = {
            "observational_unit": observational_unit,
            "observations": observations,
            "structure": structure,
            "r_squared": r_squared,
            "r_squared_adj": r_squared_adj,
            "significance": significance,
            "f_stat": f_value,
        }
    return data


def main() -> None:
    data = parse_statistics()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    print(f"Captured {len(data)} statistical rows -> {OUTPUT}")


if __name__ == "__main__":
    main()
