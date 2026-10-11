"""Review Master -- every compliance finding in one place.

An appraiser should never learn about a defect from a lender's rejection
notice.  This gathers everything that can be known about a case before it
ships, from three independent authorities, and reports them together:

``schema``       the GSE subschema (Appendix A-1's XSD).  Structural: wrong
                 element order, a value that is not of its declared type, a
                 required container missing.
``compliance``   the 728 published H-1 rules, by Message ID and severity --
                 the same identifiers a checker quotes back -- run against
                 the document as the package will deliver it.
``completeness`` fields Appendix B-1 says should appear on the page for this
                 property but which carry no value.

The verdict is deliberately blunt: a package is either **ready** or it is not,
and the sign-off gate reads that verdict rather than forming its own opinion.
Anything the compliance engine could not execute is carried through as
``review`` so it is visible rather than silently counted as a pass; so is a
finding on a section B-1 leaves out of this report, so it is visible rather
than counted against a report that does not ask for it (``shown_in``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from lxml import etree

from . import compliance, schema

SPEC = Path(__file__).resolve().parents[1] / "spec"

SCHEMA = "schema"
COMPLIANCE = "compliance"
COMPLETENESS = "completeness"

# The 29 sections, from Appendix F-1 "URAR Section Organization".
SECTIONS = {
    1: "Summary", 2: "Assignment Information", 3: "Subject Property", 4: "Site",
    5: "Disaster Mitigation", 6: "Energy Efficient and Green Features",
    7: "Sketch", 8: "Dwelling Exterior", 9: "Manufactured Home",
    10: "Unit Interior", 11: "Functional Obsolescence", 12: "Outbuilding",
    13: "Vehicle Storage", 14: "Subject Property Amenities",
    15: "Overall Quality and Condition", 16: "Highest and Best Use",
    17: "Market", 18: "Project Information", 19: "Subject Listing Information",
    20: "Sales Contract", 21: "Prior Sale and Transfer History",
    22: "Sales Comparison Approach", 23: "Rental Information",
    24: "Income Approach", 25: "Cost Approach", 26: "Reconciliation",
    27: "Revision History", 28: "Supplemental Information",
    29: "Certifications and Scope of Work",
}


@dataclass
class Item:
    """One thing the appraiser may need to act on."""
    source: str                    # schema | compliance | completeness
    severity: str                  # Fatal | Warning | Review
    code: str                      # Message ID, or a schema/completeness key
    message: str
    field_id: str = ""
    section: str = ""
    subsection: str = ""
    label: str = ""
    path: str = ""
    detail: str = ""

    @property
    def section_number(self) -> int:
        head = self.field_id.split(".")[0] if self.field_id else ""
        return int(head) if head.isdigit() else 0

    def to_json(self) -> dict[str, Any]:
        out = self.__dict__.copy()
        out["section_number"] = self.section_number
        return out


@dataclass
class Report:
    items: list[Item] = field(default_factory=list)
    schema_version: str = ""
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def fatal(self) -> list[Item]:
        return [i for i in self.items if i.severity == compliance.FATAL]

    @property
    def warnings(self) -> list[Item]:
        return [i for i in self.items if i.severity == compliance.WARNING]

    @property
    def to_review(self) -> list[Item]:
        return [i for i in self.items if i.severity == "Review"]

    @property
    def ready(self) -> bool:
        """A package may ship only with no fatal finding and a valid schema."""
        return not self.fatal and self.counts.get("schema", 0) == 0

    def by_section(self) -> dict[str, list[Item]]:
        out: dict[str, list[Item]] = {}
        for item in sorted(self.items, key=lambda i: (i.section_number, i.code)):
            name = (SECTIONS.get(item.section_number)
                    or item.section or "Document")
            out.setdefault(f"{item.section_number:02d} {name}"
                           if item.section_number else name, []).append(item)
        return out

    def to_json(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "schema_version": self.schema_version,
            "counts": self.counts,
            "items": [i.to_json() for i in self.items],
        }


@lru_cache(maxsize=1)
def _index() -> dict:
    return json.loads((SPEC / "field_index.json").read_text(encoding="utf-8"))["fields"]


def _schema_items(tree) -> list[Item]:
    out = []
    for err in schema.validate(tree):
        out.append(Item(
            source=SCHEMA, severity=compliance.FATAL, code="XSD",
            message=err.message,
            detail=f"line {err.line}" + (f", {err.path}" if err.path else ""),
            path=err.path,
        ))
    return out


#: H-1's Section column for a data point the report never prints
NOT_DISPLAYED = "Does Not Display"
#: how a finding on a section the report leaves out is carried (``findings``)
NOT_COUNTED = "not counted"


def shown_in(tree):
    """Does the report show where a finding lives?  A predicate per case.

    Read from the report's own visibility, the same calls ``form.build``
    makes: a section B-1 leaves out of this report (``form.section_shown``:
    Project Information outside a project or PUD, the Income Approach not
    developed), or one its own question switched off (``form.print_gate``),
    where only that question stays on the page.  A finding counts when any
    section H-1 places it in is shown; a data point the report never prints
    ("Does Not Display") is governed by H-1's own condition alone.  Only the
    URAR has B-1 sections; the other report types are judged as written.
    """
    from . import report_types
    from .report import form
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    if report_types.kind_of(root) != report_types.URAR:
        return lambda f: True
    ctx = form.Ctx(root)
    off: dict[str, bool] = {}

    def section_off(name: str) -> bool:
        if name not in off:
            off[name] = (form.section_shown(ctx, name) is False
                         or form.print_gate(ctx, name) is False)
        return off[name]

    def shown(f) -> bool:
        names = [s.strip() for s in (f.section or "").split(";")
                 if s.strip() and s.strip() != NOT_DISPLAYED]
        return not names or any(not section_off(s) or f.field_id in form.switch_fields(s)
                                for s in names)
    return shown


def findings(tree) -> list[compliance.Finding]:
    """H-1 (or H-2 / H-3) against the file that ships, with every finding on
    something this report does not show turned into one for a person to
    judge -- never a fatal finding or a warning.

    The package writes some of what A-1 requires itself -- the PDF's file
    name, the indicators A-1 defines from the report -- and leaves out what
    the report never shows and states nothing (``delivery.as_delivered``).
    Judged on the editor's copy, those were fatal findings no appraiser could
    ever clear: a field the report never shows, which nobody can type into,
    and a report made from blank could not be signed (T-506).  What is left on
    a section B-1 leaves out (``shown_in``) holds a value the appraiser gave
    before the report changed; it is shown, not counted.
    """
    from dataclasses import replace

    from . import delivery, report_types
    shown = shown_in(tree)
    out = []
    for f in report_types.evaluate(delivery.as_delivered(tree)):   # H-1, or H-2 / H-3 by kind
        if f.status == compliance.FINDING and not shown(f):
            f = replace(f, status=compliance.REVIEW,
                        reason=f"{NOT_COUNTED}: {f.section} is not in this report (B-1); "
                               "what H-1 found there is still in the file")
        out.append(f)
    return out


def _compliance_items(tree) -> list[Item]:
    """The findings above, as Review Master items."""
    out = []
    for f in findings(tree):
        if f.status == compliance.FINDING:
            out.append(Item(
                source=COMPLIANCE, severity=f.severity, code=f.message_id,
                message=f.text or f"{f.data_point} is required",
                field_id=f.field_id, section=f.section, subsection=f.subsection,
                label=f.label, path=f.path, detail=f.logic,
            ))
        elif f.status == compliance.REVIEW:
            out.append(Item(
                source=COMPLIANCE, severity="Review", code=f.message_id,
                message=f.text or f.logic,
                field_id=f.field_id, section=f.section, subsection=f.subsection,
                label=f.label, path=f.path,
                detail=(f.reason if f.reason.startswith(NOT_COUNTED)
                        else f"not executed automatically: {f.reason}"),
            ))
    return out


def build(tree, *, include_review: bool = True) -> Report:
    """Everything known about a case, from all three authorities."""
    items = _schema_items(tree) + _compliance_items(tree)
    if not include_review:
        items = [i for i in items if i.severity != "Review"]
    counts = {
        "schema": sum(1 for i in items if i.source == SCHEMA),
        "fatal": sum(1 for i in items if i.severity == compliance.FATAL),
        "warning": sum(1 for i in items if i.severity == compliance.WARNING),
        "review": sum(1 for i in items if i.severity == "Review"),
    }
    return Report(items=items, schema_version=schema.schema_version(), counts=counts)


def main() -> None:
    import sys

    from . import templates

    key = sys.argv[1] if len(sys.argv) > 1 else "sf1_appraisal_v1_4"
    tpl = templates.get(key)
    report = build(etree.parse(str(tpl.path)))
    print(f"Review Master -- {tpl.name}")
    print(f"  schema v{report.schema_version}")
    for name, n in report.counts.items():
        print(f"  {name:<10} {n}")
    print(f"  ready to export: {'yes' if report.ready else 'no'}\n")
    for section, items in list(report.by_section().items())[:8]:
        print(f"  {section}  ({len(items)})")
        for item in items[:3]:
            print(f"     [{item.severity[:1]}] {item.code:<10} {item.message[:78]}")


if __name__ == "__main__":
    main()
