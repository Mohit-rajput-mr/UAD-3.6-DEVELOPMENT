"""Reconstruct the URAR's page layout from the twelve official sample reports.

Appendix C-1 states the layout in prose and tables; the samples *are* the
layout, rendered.  Reading them back gives the field order, the column each
label sits in, its indent level and the subsection it belongs under -- for
every property type at once, since the twelve samples between them exercise
single family, 2-4 unit, condominium, cooperative and manufactured home.

The reconstruction works from the page furniture measured in
``measure_geometry``: a black bar at 36 pt opens a section, a grey bar spans
the measure to open a subsection, and body text falls on one of six known
x-positions -- label or value, left column or right, at one of three indents.

What comes out is not a guess at the layout but a record of it, with the
samples each field was seen in, so conditionality can be read off as well.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from measure_geometry import report_start, samples

OUT = Path(__file__).resolve().parents[2] / "spec" / "page_layout.json"

# Geometry, as measured.  Kept local so this script stays runnable on its own.
MARGIN = 36.0
COLUMNS = (36.0, 312.0)
LABEL_INSET, VALUE_INSET, INDENT = 4.0, 145.0, 8.0
TAB_FILL = {"#231f20", "#000000"}
BAR_FILLS = {"#e6e7e8", "#58595b", "#a7a9ac"}
TOL = 2.5

CONTINUED = re.compile(r"\s*\(continued\)\s*$", re.I)

# A tab may name the instance it belongs to -- "Unit Interior - Building 1 -
# Unit 1", "Outbuilding - Barn".  The section is the part before the first
# dash; the rest identifies which structure or unit is being described, and
# belongs to the data, not to the layout.
INSTANCE_SUFFIX = re.compile(r"\s+[-–]\s+.*$")

# The 29 sections, from Appendix F-1 "URAR Section Organization" (p11-12).
CANONICAL = {
    "Summary", "Assignment Information", "Subject Property", "Site",
    "Disaster Mitigation", "Energy Efficient and Green Features", "Sketch",
    "Dwelling Exterior", "Manufactured Home", "Unit Interior",
    "Functional Obsolescence", "Outbuilding", "Vehicle Storage",
    "Subject Property Amenities", "Overall Quality and Condition",
    "Highest and Best Use", "Market", "Project Information",
    "Subject Listing Information", "Sales Contract",
    "Prior Sale and Transfer History", "Sales Comparison Approach",
    "Rental Information", "Income Approach", "Cost Approach",
    "Reconciliation", "Revision History", "Supplemental Information",
    "Certifications",
}


def normalise(tab: str) -> tuple[str, str]:
    """Split a tab into its section and the instance it names, if any."""
    text = CONTINUED.sub("", " ".join(tab.split()))
    if text in CANONICAL:
        return text, ""
    base = INSTANCE_SUFFIX.sub("", text)
    if base in CANONICAL:
        return base, text[len(base):].lstrip(" -–")
    return text, ""


def _hex(c) -> str:
    return "none" if c is None else "#%02x%02x%02x" % tuple(round(v * 255) for v in c)


@dataclass
class Field:
    label: str
    column: int
    indent: int
    kind: str                       # label | heading | value-only | checkbox
    subsection: str = ""
    order: int = 0
    seen_in: set[str] = field(default_factory=set)
    values: set[str] = field(default_factory=set)
    instances: set[str] = field(default_factory=set)

    def to_json(self) -> dict:
        return {"label": self.label, "column": self.column, "indent": self.indent,
                "kind": self.kind, "subsection": self.subsection,
                "order": self.order, "seen_in": sorted(self.seen_in),
                "instances": sorted(self.instances),
                "example_values": sorted(self.values)[:4]}


def _classify(x0: float) -> tuple[int, int, str] | None:
    """Which column, indent and role an x-position corresponds to."""
    for col, base in enumerate(COLUMNS):
        for indent in range(4):
            if abs(x0 - (base + LABEL_INSET + indent * INDENT)) < TOL:
                return col, indent, "label"
        if abs(x0 - (base + VALUE_INSET)) < TOL:
            return col, 0, "value"
    return None


def extract() -> dict:
    sections: dict[str, dict[str, Field]] = defaultdict(dict)
    order = defaultdict(int)
    section_order: list[str] = []

    for pdf in samples():
        key = pdf.stem
        doc = pymupdf.open(pdf)
        start = report_start(doc)
        section, subsection, instance = "", "", ""
        for pno in range(start, doc.page_count):
            page = doc[pno]

            # Bars and tabs, keyed by their vertical position so body text can
            # be attributed to whichever one most recently preceded it.
            marks: list[tuple[float, str, str]] = []
            for d in page.get_drawings():
                fill = _hex(d.get("fill"))
                r = d["rect"]
                if fill in TAB_FILL and 12 < r.height < 18 and abs(r.x0 - MARGIN) < TOL:
                    text = " ".join(page.get_text("text", clip=r).split())
                    if text:
                        marks.append((r.y0, "section", text))
                elif fill in BAR_FILLS and r.width > 400 and 10 < r.height < 18:
                    text = " ".join(page.get_text("text", clip=r).split())
                    if text:
                        marks.append((r.y0, "subsection", text))

            rows = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for s in line["spans"]:
                        text = " ".join(s["text"].split())
                        if not text or s["bbox"][1] < 60 or s["bbox"][1] > 935:
                            continue
                        rows.append((round(s["bbox"][1], 1), round(s["bbox"][0], 1),
                                     round(s["size"], 1),
                                     s["font"].split("+")[-1], text))

            # Report page 1 carries no tab: E-1 suppresses the running header
            # and the section opens with the word SUMMARY set in 14 pt.
            if pno == start:
                section, instance, subsection = "Summary", "", ""
                if "Summary" not in section_order:
                    section_order.insert(0, "Summary")

            marks.sort()
            # A tab and a bar carry their own text.  That text is furniture and
            # must not be collected as a field of the section it opens.
            furniture = [(my, my + 15.0) for my, _k, _l in marks]
            for y, x0, size, font, text in sorted(rows):
                if any(a - 0.5 <= y <= b for a, b in furniture):
                    continue
                while marks and marks[0][0] <= y:
                    _my, kind, label = marks.pop(0)
                    if kind == "section":
                        section, instance = normalise(label)
                        if section not in section_order:
                            section_order.append(section)
                        subsection = ""
                    else:
                        subsection = label
                if not section or size not in (9.0, 10.0):
                    continue
                if "Myriad" not in font and "Calibri" not in font:
                    continue
                spot = _classify(x0)
                if spot is None:
                    continue
                col, indent, role = spot
                bold = font.endswith("Bold") or font.endswith("Semibold")

                if size == 10.0 and bold:
                    kind, name = "heading", text
                elif role == "label" and bold:
                    kind, name = "label", text
                elif role == "label" and not bold:
                    kind, name = "sublabel", text
                else:
                    continue

                bucket = sections[section]
                existing = bucket.get(name)
                if existing is None:
                    order[section] += 1
                    existing = Field(label=name, column=col, indent=indent,
                                     kind=kind, subsection=subsection,
                                     order=order[section])
                    bucket[name] = existing
                if instance:
                    existing.instances.add(instance)
                existing.seen_in.add(key)

                # the value that follows this label on the same line
                for vy, vx, _vs, vfont, vtext in rows:
                    if abs(vy - y) < 1.6 and abs(
                            vx - (COLUMNS[col] + VALUE_INSET)) < TOL:
                        if not vfont.endswith("Bold"):
                            existing.values.add(vtext[:40])
                        break
        doc.close()

    return {
        "source": "Appendix D-1 sample appraisal PDFs",
        "samples": [p.stem for p in samples()],
        "section_order": section_order,
        "sections": {
            name: [f.to_json() for f in sorted(fields.values(), key=lambda f: f.order)]
            for name, fields in sections.items()
        },
    }


def main() -> None:
    data = extract()
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    total = sum(len(v) for v in data["sections"].values())
    print(f"-> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    print(f"   sections ... {len(data['sections'])}")
    print(f"   fields ..... {total}\n")
    n_samples = len(data["samples"])
    for name in data["section_order"]:
        fields = data["sections"].get(name, [])
        always = sum(1 for f in fields if len(f["seen_in"]) == n_samples)
        left = sum(1 for f in fields if f["column"] == 0)
        print(f"   {name:<42} {len(fields):>4} fields  "
              f"{always:>3} in all {n_samples}  {left:>3} left / {len(fields) - left} right")


if __name__ == "__main__":
    main()
