"""Extract bibliography entries from Arnvik (2024)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pdfplumber

PDF_PATH = Path("notes/reference/arnvik-w-20240926.pdf")
OUTPUT = Path("notes/reference/arnvik_tables/references.json")

HEADER_RE = re.compile(r"^([\wÄÅÖÆØÜÉáéíóúñç'`-]+).*?\((\d{4}[a-z]?)\)")
ALT_START_RE = re.compile(r"^[A-Za-zÄÅÖÆØÜÉ][^()\n]+?\(\d{4}[a-z]?\)")


def extract_references_block() -> str:
    with pdfplumber.open(PDF_PATH) as pdf:
        capture = False
        collected: list[str] = []
        for page in pdf.pages:
            lines = (page.extract_text() or "").splitlines()
            for raw in lines:
                line = raw.strip()
                if not capture:
                    if line == "References":
                        capture = True
                    continue
                if line.startswith("Appendix"):
                    return "\n".join(collected)
                collected.append(line)
        return "\n".join(collected)


def normalize_key(header: str) -> str | None:
    match = HEADER_RE.match(header)
    if not match:
        return None
    author, year = match.groups()
    author = re.sub(r"[^\w]+", " ", author).split()[0]
    slug = f"{author}_{year}".lower()
    slug = re.sub(r"[^a-z0-9_]+", "_", slug)
    return slug


def looks_like_author_intro(line: str) -> bool:
    if "," not in line:
        return False
    first, rest = line.split(",", 1)
    first = first.strip()
    rest = rest.lstrip()
    return bool(first and rest and rest[0].isalpha())


def looks_like_start(line: str) -> bool:
    return bool(looks_like_author_intro(line) or ALT_START_RE.match(line))


def collect_references() -> dict[str, dict]:
    refs: dict[str, dict] = {}
    lines = [ln.strip() for ln in extract_references_block().splitlines() if ln.strip()]
    current: list[str] = []

    for line in lines:
        if looks_like_start(line) and current:
            chunk = " ".join(current)
            key = normalize_key(chunk)
            if key:
                refs[key] = {"key": key, "label": current[0], "citation": chunk}
            current = [line]
        else:
            current.append(line)

    if current:
        chunk = " ".join(current)
        key = normalize_key(chunk)
        if key:
            refs[key] = {"key": key, "label": current[0], "citation": chunk}

    return refs


def main() -> None:
    refs = collect_references()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as fh:
        json.dump(refs, fh, indent=2, ensure_ascii=False)
    print(f"Captured {len(refs)} references -> {OUTPUT}")


if __name__ == "__main__":
    main()
