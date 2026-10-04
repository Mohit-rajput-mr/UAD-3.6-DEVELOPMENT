"""Extract the in-section table definitions from Appendix E Part 2.

The URAR is a table-driven form: beyond the sales comparison grid, Part 2
defines 41 tables — parcels, site influences, utilities, defects, level and
room detail, amenities, transfer history, approaches to value and the rest —
each with its own column heads and widths.

Those definitions are parsed out of the guide into
``engine/spec/tables.json`` so the renderer builds them from the source rather
than from a transcription.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SOURCE = ROOT / "_work" / "prose" / "E_style.txt"
TARGET = ROOT / "engine" / "spec" / "tables.json"

PART2_FIRST_PAGE, PART2_LAST_PAGE = 33, 81

_TAB = re.compile(r"[“\"]([^”\"]{3,60})[”\"]\s+sets? as TAB", re.I)
_TABLE = re.compile(r"^(?:.*?-\s*)?(?P<name>[A-Z][A-Za-z ,/\-\(\)\[\]]{2,60}) table\s*$")
_QUOTED = re.compile(r"[“\"]([^”\"]{1,70})[”\"]")
# "set as TCH in 5 equal column table x 45 picas"
_WIDTH = re.compile(r"x\s*(\d+)\s*picas", re.I)
_EQUAL = re.compile(r"(\d+)\s+equal(?:\s+width)?\s+column", re.I)


def _lines(text: str) -> list[str]:
    out, page = [], 0
    for line in text.splitlines():
        marker = re.match(r"<<<PAGE (\d+) of \d+>>>", line.strip())
        if marker:
            page = int(marker.group(1))
            continue
        if PART2_FIRST_PAGE <= page <= PART2_LAST_PAGE:
            out.append(line.strip())
    return out


def _clean(label: str) -> str:
    label = label.strip().strip(",;:—-").strip()
    return "" if label in {"Yes", "No", "R", "#"} or len(label) < 1 else label


def extract(source: Path = SOURCE) -> list[dict]:
    lines = _lines(source.read_text(encoding="utf-8"))
    tables: list[dict] = []
    section = ""

    for index, line in enumerate(lines):
        if match := _TAB.search(line):
            section = match.group(1).strip()
            continue

        match = _TABLE.match(line)
        if not match:
            continue

        name = match.group("name").strip()
        if name.lower().startswith(("the ", "this ", "a ", "standard")):
            continue

        # The guide names the heads either side of the phrase "set as TCH",
        # then moves on to the cell widths and the row content.  Read until
        # that turn, whichever order the heads came in.
        window_lines: list[str] = []
        for candidate in lines[index + 1 : index + 16]:
            if re.match(r"(Content sets|Columns? \d|Column \d|Cells in)", candidate):
                break
            window_lines.append(candidate)
        window = " ".join(window_lines)
        if "TCH" not in window:
            continue

        heads = [h for raw in _QUOTED.findall(window) if (h := _clean(raw))]
        if len(heads) < 2:
            continue

        tail = " ".join(lines[index + 1 : index + 22])
        width = _WIDTH.search(tail)
        equal = _EQUAL.search(tail)
        if equal:
            # The guide states the column count; trust it over the quote count.
            heads = heads[: int(equal.group(1))]
        tables.append(
            {
                "name": name,
                "section": section,
                "columns": heads[:12],
                "width_picas": int(width.group(1)) if width else 45,
                "equal_columns": int(equal.group(1)) if equal else None,
            }
        )
    return tables


def main() -> None:
    tables = extract()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(tables, indent=1), encoding="utf-8")
    print(f"{len(tables)} tables extracted")
    for t in tables:
        print(f"   {t['section'][:22]:24s} {t['name'][:34]:36s} {len(t['columns'])} cols")


if __name__ == "__main__":
    main()
