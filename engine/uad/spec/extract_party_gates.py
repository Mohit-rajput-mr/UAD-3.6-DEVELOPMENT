"""Subsections Appendix B-1 shows only when a party exists.

B-1 p106: "Information about the Supervisory Appraiser displays based on
PartyRoleType ... If there is no Supervisory Appraiser, the subsection does
not display."  p108: "The Significant Real Property Appraisal Assistance
subsection displays when there are one or more contacts with PartyRoleType
...".  The printed report followed these; the editor showed every such
subsection's empty fields whether or not the party had been added (T-1074).
This reads each sentence and the PartyRoleType it names (the A-1 enumeration
whose display text or name is the subsection's).

    python -m uad.spec.extract_party_gates      (from engine/)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

from .extract_section_display import _b1

SPEC = Path(__file__).resolve().parents[2] / "spec"
OUT = SPEC / "party_gates.json"

PATTERNS = (
    re.compile(r"If there is no ([A-Z][A-Za-z ]+?), the subsection does not display"),
    re.compile(r"The ([A-Z][A-Za-z ]+?) subsection displays when there are one or more contacts with PartyRoleType"),
)


def _squash(v: str) -> str:
    return re.sub(r"[^a-z]", "", v.lower())


def _roles() -> dict[str, str]:
    """squashed display text / enumeration name -> PartyRoleType value."""
    rows = json.loads((SPEC / "enumerations.json").read_text(encoding="utf-8"))
    shown = next(k for k in rows[0] if k.startswith("Output Report Display"))
    out = {}
    for r in rows:
        if r.get("MISMO Data Point / Attribute Name") != "PartyRoleType":
            continue
        value = r["Supported Enumerations"]
        out.setdefault(_squash(value), value)
        text = str(r.get(shown, "")).split("\n")[0]
        if "Does Not Display" not in text:
            out.setdefault(_squash(text), value)
    return out


def main() -> None:
    pdf = _b1()
    roles = _roles()
    found = {}
    doc = pymupdf.open(str(pdf))
    for pno in range(len(doc)):
        flat = re.sub(r"\s+", " ", doc[pno].get_text())
        for pat in PATTERNS:
            for m in pat.finditer(flat):
                name = m.group(1).strip()
                role = roles.get(_squash(name))
                if role and name not in found:
                    found[name] = {"subsection": name, "role": role, "page": pno + 1,
                                   "text": m.group(0).strip() + "."}
    OUT.write_text(json.dumps({"source": f"{pdf.name}: subsections that display only when a party exists",
                               "gates": list(found.values())}, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    print(f"{len(found)} gate(s) -> {OUT}")
    for g in found.values():
        print(f"  p{g['page']} {g['subsection']} <- PartyRoleType {g['role']}")


if __name__ == "__main__":
    main()
