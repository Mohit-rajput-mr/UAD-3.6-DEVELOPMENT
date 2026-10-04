"""Lift the Summary section's source fields out of Appendix B-1.

B-1 chapter 01 says the Summary "is redisplayed from other sections of the
report" and gives, for each Summary Report Field ID, the Source Field ID and
the section it comes from.  The editor needs that table to keep the Summary
read-only and send the appraiser to where each value is really entered.

    python engine/uad/spec/extract_summary_sources.py

writes ``engine/spec/summary_sources.json``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[3]
PDF = ROOT / "_ref" / "impl" / "Appendix B-1 URAR Implementation Guide v1.4.pdf"
OUT = ROOT / "engine" / "spec" / "summary_sources.json"

FIDS = re.compile(r"\d{1,2}\.\d{2,3}(?:\.\d{1,2}){0,2}")
# a line made only of field IDs, pipes and spaces
FID_LIST = re.compile(r"^\d{1,2}\.\d{2,3}(?:\.\d{1,2}){0,2}[\d.|\s]*$")
HEADINGS = {"Report Field ID", "Report", "Field ID", "Report Label", "Source",
            "Source Section FID", "Original Section", "Source Field ID"}


def _chapter_pages(doc) -> range:
    """From the page that opens "01 Summary" to the one that opens chapter 02."""
    start = end = None
    for i, page in enumerate(doc):
        lines = [ln.strip() for ln in page.get_text().splitlines()]
        if start is None and "01 Summary" in lines and i > 20:
            start = i
        elif start is not None and any(ln.startswith("02 Assignment Information") for ln in lines):
            end = i
            break
    if start is None or end is None:
        raise SystemExit("could not find chapter 01 in B-1")
    return range(start, end + 1)


def _tokens(lines: list[str]) -> list[tuple[str, object]]:
    """Lines as ("ids", [...]) or ("text", str).

    A row's IDs can be a pipe-separated list wrapping over several lines
    ("1.033 | 1.040 | 1.048 |" then "1.055 | 1.063 | 1.069 |" then "1.075"),
    so a list line that follows one ending in a pipe continues it.
    """
    out: list[tuple[str, object]] = []
    prev = ""
    for ln in lines:
        if FID_LIST.match(ln):
            ids = FIDS.findall(ln)
            if out and out[-1][0] == "ids" and prev.rstrip().endswith("|"):
                out[-1][1].extend(ids)
            else:
                out.append(("ids", ids))
        else:
            out.append(("text", ln))
        prev = ln
    return out


def extract() -> dict:
    doc = pymupdf.open(PDF)
    pages = _chapter_pages(doc)
    lines: list[str] = []
    for i in pages:
        for ln in doc[i].get_text().splitlines():
            ln = ln.strip()
            if ln and not ln.startswith(("Page ", "Appendix B-1")):
                lines.append(ln)
    tokens = _tokens(lines)
    summary = lambda ids: all(v.startswith("1.") for v in ids)   # noqa: E731

    out: dict[str, dict] = {}
    i = 0
    while i < len(tokens):
        kind, val = tokens[i]
        if kind != "ids" or not summary(val):
            i += 1
            continue
        label: list[str] = []
        j = i + 1
        while j < len(tokens) and tokens[j][0] == "text" and len(label) < 4:
            if tokens[j][1] not in HEADINGS:
                label.append(tokens[j][1])
            j += 1
        if j < len(tokens) and tokens[j][0] == "ids" and not summary(tokens[j][1]):
            sources = tokens[j][1]
            origin = tokens[j + 1][1] if j + 1 < len(tokens) and tokens[j + 1][0] == "text" else ""
            # The n-th Summary ID redisplays the n-th source ID when the two
            # lists are the same length (the defect table); otherwise each
            # Summary ID draws on all of them.
            paired = len(sources) == len(val)
            for n, fid in enumerate(val):
                src = [sources[n]] if paired else list(sources)
                out.setdefault(fid, {"label": " ".join(label), "sources": src,
                                     "section": int(src[0].split(".")[0]),
                                     "origin": origin})
            i = j + 1
            continue
        i = j
    return {"source": PDF.name, "chapter_pages": [pages.start + 1, pages.stop],
            "fields": out}


def main() -> None:
    data = extract()
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"{len(data['fields'])} Summary fields with a source -> {OUT}")


if __name__ == "__main__":
    main()
