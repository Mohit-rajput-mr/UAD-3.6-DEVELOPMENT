"""Extract the column layout from Appendix E Part 2.

Part 2 states, section by section, which labels set on the left-hand side of
the page and which on the right, and which subsections carry a grey H1 bar.
Rather than transcribe that by hand it is parsed out of the guide's own text
into ``engine/spec/layout.json``, which the renderer then follows.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SOURCE = ROOT / "_work" / "prose" / "E_style.txt"
TARGET = ROOT / "engine" / "spec" / "layout.json"

LEFT, RIGHT, FULL = "left", "right", "full"

# '"Site" sets as TAB.' introduces a section.
_TAB = re.compile(r"[“\"]([^”\"]{3,60})[”\"]\s+sets? as TAB", re.I)
# 'Contact Information (H1)' introduces a grey-bar subsection.
_H1 = re.compile(r"^(?P<name>[A-Z][^\n]{2,80}?)\s*\((?:H1|H2|H2-1|CK-H2)\)\s*$")
_SIDE = re.compile(r"^(Left|Right)-hand side of page", re.I)
_FULL = re.compile(r"^Full page width", re.I)
# Field labels are quoted in the guide.
_LABEL = re.compile(r"[“\"]([^”\"]{2,80})[”\"]")

# Part 2 occupies pages 33-81 of the guide.  Anchoring on the page markers
# avoids matching the same headings where they appear in the table of contents.
PART2_FIRST_PAGE = 33
PART2_LAST_PAGE = 81


def _pages(text: str, first: int, last: int) -> list[str]:
    out: list[str] = []
    current = 0
    for line in text.splitlines():
        marker = re.match(r"<<<PAGE (\d+) of \d+>>>", line.strip())
        if marker:
            current = int(marker.group(1))
            continue
        if first <= current <= last:
            out.append(line.strip())
    return out


def extract(source: Path = SOURCE) -> dict:
    text = source.read_text(encoding="utf-8")
    lines = _pages(text, PART2_FIRST_PAGE, PART2_LAST_PAGE)

    layout: dict[str, dict] = {}
    section = None
    subsection = ""
    side = FULL

    for line in lines:
        if not line or line.startswith(("Appendix E", "Page ", "Version ")):
            continue

        if match := _TAB.search(line):
            section = match.group(1).strip()
            layout.setdefault(section, {"columns": {}, "subsections": []})
            subsection, side = "", FULL
            continue

        if match := _H1.match(line):
            name = match.group("name").strip()
            if section and not name.lower().startswith(("the ", "if ", "set ")):
                subsection = name
                if name not in layout[section]["subsections"]:
                    layout[section]["subsections"].append(name)
                side = FULL
            continue

        if match := _SIDE.match(line):
            side = LEFT if match.group(1).lower() == "left" else RIGHT
            continue
        if _FULL.match(line):
            side = FULL
            continue

        if section and side in (LEFT, RIGHT):
            for raw in _LABEL.findall(line):
                label = _clean(raw)
                if not label:
                    continue
                layout[section]["columns"].setdefault(label, side)

    layout["Summary"] = SUMMARY_LAYOUT
    return layout


# The guide quotes labels inside running prose, so they arrive with the
# sentence punctuation attached.
_SKIP = {"Yes", "No", "R", "#", "/"}


def _clean(raw: str) -> str:
    label = raw.strip().strip(",;:").strip()
    if label in _SKIP or len(label) < 2:
        return ""
    if label.isupper() and len(label) < 6:
        return ""
    # Full sentences are instructions, not field labels - except the two
    # question-form labels the form really does print.
    if len(label) > 70 and not label.endswith("?"):
        return ""
    return label


# The Summary section is introduced by SUM-HD rather than a black tab, so it is
# transcribed directly from Appendix E p33.
SUMMARY_LAYOUT = {
    "columns": {
        "Opinion of Market Value": LEFT,
        "Effective Date of Appraisal": LEFT,
        "Assignment Reason": LEFT,
        "Borrower Name": LEFT,
        "Current Owner of Public Record": LEFT,
        "Contract Price": LEFT,
        "Listing Status": LEFT,
        "Market Value Condition": RIGHT,
        "Property Valuation Method": RIGHT,
        "Appraiser Name": RIGHT,
        "Construction Method": LEFT,
        "Attachment Type": LEFT,
        "Structure Design": LEFT,
        "Planned Unit Development (PUD)": LEFT,
        "Condominium": LEFT,
        "Cooperative": LEFT,
        "Condop": LEFT,
        "Observed Project Deficiencies": LEFT,
        "Subject Site Owned in Common": LEFT,
        "Units Excluding ADUs": LEFT,
        "Accessory Dwelling Units": LEFT,
        "Property Rights Appraised": LEFT,
        "Property Restriction": LEFT,
        "Encroachment": LEFT,
        "Zoning Compliance": LEFT,
        "HUD Data Plate Attached": LEFT,
        "HUD Label Present for All Sections": LEFT,
        "Overall Quality": RIGHT,
        "Overall Condition": RIGHT,
        "As Is Overall Condition Rating": LEFT,
        "Total Estimated Cost of Items Recommended for Repair": RIGHT,
    },
    "subsections": [
        "Property Description",
        "Apparent Defects, Damages, Deficiencies Requiring Action",
    ],
}


def main() -> None:
    layout = extract()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(layout, indent=1), encoding="utf-8")

    sections = len(layout)
    labels = sum(len(v["columns"]) for v in layout.values())
    subs = sum(len(v["subsections"]) for v in layout.values())
    print(f"{sections} sections, {labels} column assignments, {subs} subsections")
    for name, body in list(layout.items())[:6]:
        left = sum(1 for s in body["columns"].values() if s == LEFT)
        right = sum(1 for s in body["columns"].values() if s == RIGHT)
        print(f"   {name[:38]:40s} left={left:>3} right={right:>3} subs={len(body['subsections'])}")


if __name__ == "__main__":
    main()
