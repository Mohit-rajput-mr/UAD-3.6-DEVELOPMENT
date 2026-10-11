"""When B-1 prints a static italic note, as B-1 states it.

B-1 writes a note's condition beside the note: "When
PersonalPropertyIncludedIndicator (UID: 0600.0004, FID: 20.007) = "true",
display static text in italics, "Personal property is not included in the
appraiser's final opinion of value" below the label Personal Property
Conveyed."  The note itself is C-1 static text with no field ID, so without
this the report printed it for every sales contract -- D-1 prints it only on
SF1, the one sample answering "true".

B-1 also words a note's condition the other way round: "If
SketchExistsIndicator (UID: 3300.0002, FID: 7.000) = "false", "Sketch or Floor
Plan Not Available" displays." (p162).  Those rules carry ``"shape":
"displays"`` and the field ID the note is set against.

And a value slot that shows one thing only: "When CarStorageType (UID:
3200.0006, FID: 13.000) = "None", display "None"" (p228) -- otherwise the
Vehicle Storage table below carries the storage.  Those carry ``"shape":
"value"``.

    python -m uad.spec.extract_italic_rules      (from engine/)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

from .extract_section_display import _b1

OUT = Path(__file__).resolve().parents[2] / "spec" / "italic_rules.json"

RULE = re.compile(
    r"When (?P<name>[A-Z]\w+) \(UID: [\d.]+, FID: [\d.]+\) = [“\"](?P<value>\w+)[”\"], "
    r"display static text in italics(?: \(FID: (?P<fid>[\d.]+)\))?,? [“\"](?P<text>[^”\"]+)[”\"]")
VALUE = re.compile(
    r"When (?P<name>[A-Z]\w+) \(UID: [\d.]+, FID: (?P<fid>[\d.]+)\) = [“\"](?P<value>[\w ]+)[”\"], "
    r"display [“\"](?P<text>[^”\"]+)[”\"](?:; the (?P<hides>[^.;]+?) does not display)?")
DISPLAYS = re.compile(
    r"If (?P<name>[A-Z]\w+) \(UID: [\d.]+, FID: (?P<fid>[\d.]+)\) = [“\"](?P<value>\w+)[”\"], "
    r"[“\"](?P<text>[^”\"]+)[”\"] displays")


def extract(pdf: Path) -> list[dict]:
    doc = pymupdf.open(pdf)
    out = []
    for n in range(doc.page_count):
        text = " ".join(doc[n].get_text().split())
        for m in RULE.finditer(text):
            out.append({"text": m["text"].replace("’", "'").strip(), "name": m["name"],
                        "value": m["value"], "fid": m["fid"] or "", "page": n + 1})
        for m in VALUE.finditer(text):
            out.append({"text": m["text"].strip(), "name": m["name"], "value": m["value"],
                        "fid": m["fid"], "page": n + 1, "shape": "value",
                        **({"hides": m["hides"].strip()} if m["hides"] else {})})
        for m in DISPLAYS.finditer(text):
            out.append({"text": m["text"].replace("’", "'").strip(), "name": m["name"],
                        "value": m["value"], "fid": m["fid"], "page": n + 1,
                        "shape": "displays"})
    return out


def main() -> None:
    rules = extract(_b1())
    OUT.write_text(json.dumps({"source": "Appendix B-1 URAR Implementation Guide v1.4",
                               "rules": rules}, indent=1), encoding="utf-8")
    print(f"{len(rules)} italic rules -> {OUT}")


if __name__ == "__main__":
    main()
