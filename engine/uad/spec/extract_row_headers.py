"""Table rows Appendix B-1 says always print, whether or not they hold data.

B-1 p140, Utilities and Impact to Value/Marketability: "Electricity, Sanitary
Sewer, and Water always display as row headers and in alphabetical order on
the report."  A fixed row of a table otherwise prints only when it has a value,
so a report with no utility answered dropped the whole table (T-120).  This
reads every such sentence, with the subsection it belongs to (the last
"The ... subsection" sentence before it on the page) and its page.

    python -m uad.spec.extract_row_headers      (from engine/)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

from .extract_section_display import _b1, chapters
from .extract_display_rules import SECTIONS

OUT = Path(__file__).resolve().parents[2] / "spec" / "row_headers.json"

SENTENCE = re.compile(r"([A-Z][^.•▪]*?)\s+always display as row headers\b[^.]*\.")
SUBSECTION = re.compile(r"The ([A-Z][^.•▪]*?) subsection\b")


def _names(text: str) -> list[str]:
    """ "Electricity, Sanitary Sewer, and Water" -> the three."""
    parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", text)
    return [p.strip() for p in parts if p.strip()]


def main() -> None:
    pdf = _b1()
    rows = []
    for number, pages in sorted(chapters(pdf).items()):
        for page, text in pages:
            flat = re.sub(r"\s+", " ", text)
            for m in SENTENCE.finditer(flat):
                before = [s.group(1) for s in SUBSECTION.finditer(flat[:m.start()])]
                rows.append({"section": SECTIONS[number], "subsection": before[-1] if before else "",
                             "rows": _names(m.group(1)), "page": page,
                             "text": m.group(0).strip()})
    OUT.write_text(json.dumps({"source": f"{pdf.name}, \"... always display as row headers\"",
                               "tables": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} rule(s) -> {OUT}")
    for r in rows:
        print(f"  p{r['page']} {r['section']} / {r['subsection']}: {r['rows']}")


if __name__ == "__main__":
    main()
