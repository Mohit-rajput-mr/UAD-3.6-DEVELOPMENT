"""Appendix G-1, the GSEs' own map from UAD 3.6 back to legacy UAD 2.6.

G-1 lists every 3.6 data point beside the 2.6 xPath and data point that held
the same fact on the 1004/70 and the 1073/465.  That is what lets a report
written in 2.6 be carried into 3.6 without anyone deciding, field by field,
where each value goes: the specification already decided.

Output: ``spec/g1_crossref.json``, one row per 3.6 data point that G-1 gives a
2.6 source for, with its Report Field ID, the property roles it applies to,
and every 2.6 xPath / data point G-1 names for it (a cell can name several).

    python engine/uad/spec/extract_g1.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "Appendix G-1 Redesign to Legacy UAD Cross Reference Guide v1.4.xlsx"
OUT = Path(__file__).resolve().parents[2] / "spec" / "g1_crossref.json"
SHEET = "Cross Ref Guide (Clean) 1.4"
ROLES = ("Subject Property", "Land Comparable", "Property Analyzed Not Used",
         "Rental Comparable", "Gross Rent Multiplier Comparable", "Sales Comparable")
FID = re.compile(r"(\d{1,2}\.\d{2,3}(?:\.\d{1,2})?)\s*:")


def _cells(value) -> list[str]:
    """G-1 packs alternatives into one cell, one per line."""
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def extract() -> dict:
    wb = openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)
    rows = list(wb[SHEET].iter_rows(values_only=True))
    head = [str(c or "").strip() for c in rows[0]]
    ix = {h: i for i, h in enumerate(head) if h}
    out = []
    for raw in rows[1:]:
        def cell(name):
            i = ix.get(name)
            return raw[i] if i is not None and i < len(raw) else None
        forms = {}
        for form in ("1004/70", "1073/465"):
            paths = _cells(cell(f"xRef 2.6 Form {form} xPath"))
            if not paths or "No Cross" in str(cell(f"xRef 2.6 Form {form} Sort ID") or ""):
                continue
            forms[form] = {
                "sort_id": str(cell(f"xRef 2.6 Form {form} Sort ID") or "").strip(),
                "xpaths": paths,
                "data_points": _cells(cell(f"xRef 2.6 Form {form} Data Point")),
                "field_ids": _cells(cell(f"xRef 2.6 Form {form} Field Identifier")),
                "labels": _cells(cell(f"xRef 2.6 Form {form} Field Label")),
                "comments": str(cell(f"xRef 2.6 Form {form} Comments") or "").strip(),
            }
        if not forms:
            continue
        location = str(cell("Report Location") or "")
        out.append({
            "unique_id": str(cell("Unique ID") or "").strip(),
            "context": str(cell("Additional Context") or "").strip(),
            "fids": FID.findall(location),
            "report_location": location.strip(),
            "xpath": str(cell("MISMO xPath") or "").strip(),
            "container": str(cell("MISMO Parent Container") or "").strip(),
            "data_point": str(cell("MISMO Data Point Name") or "").strip(),
            "attribute": str(cell("MISMO Attribute Name") or "").strip(),
            "enumerations": _cells(str(cell(
                "Supported Data Point Enumerations\n\n(Reference the MISMO Data Point Name column)")
                or "").replace("|", "\n")),
            "roles": [r for r in ROLES if str(cell(r) or "").strip().lower() == "x"],
            "legacy": forms,
        })
    return {"source": SOURCE.name, "sheet": SHEET, "rows": out}


if __name__ == "__main__":
    data = extract()
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    rows = data["rows"]
    print(f"{len(rows)} 3.6 data points with a 2.6 source -> {OUT}")
    print("  1004/70:", sum(1 for r in rows if "1004/70" in r["legacy"]),
          "| 1073/465:", sum(1 for r in rows if "1073/465" in r["legacy"]),
          "| with a Report Field ID:", sum(1 for r in rows if r["fids"]))
