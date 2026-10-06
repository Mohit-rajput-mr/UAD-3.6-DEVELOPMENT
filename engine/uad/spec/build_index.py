"""Join the spec files into one index keyed by Report Field ID.

The authorities are split across five artifacts and no single one of them can
drive the report on its own:

  A-1 Delivery Specification   what may be delivered, per property role, with
                               conditionality, cardinality and format
  A-1 Enumerations             the allowed values and the text the PDF shows
  B-1 Implementation Guide     when each field appears on the page
  H-1 Compliance Rules         what a checker will reject
  F-1 / B-1 grid supplements   how the comparable grids behave

This module reads all of them and emits one record per Report Field ID so the
builder never has to guess which file settles a question.  Nothing here is
typed in by hand; every value carries the file it came from.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

SPEC = Path(__file__).resolve().parents[2] / "spec"

# "2.057: Assignment Information - Contact Information - Reference ID".  One
# delivery row lists *every* place its data point displays, so the column holds
# several of these run together and each names its own Report Field ID.
LOCATION = re.compile(r"(?:^|\s)(\d{1,2}\.\d{2,3}(?:\.\d{1,2})?)\s*:\s*")
FID_IN_TEXT = re.compile(r"\b(\d{1,2}\.\d{2,3}(?:\.\d{1,2})?)\b")
NO_SUBSECTION = "{No Subsection}"


def parse_locations(raw: str) -> list[tuple[str, str, str, str]]:
    """Split a packed Report Location into (fid, section, subsection, label).

    Attaching a data point to only the first field ID in the string -- which an
    earlier version did -- loses every other place it displays.  "Borrower
    Name" then exists on the Summary and nowhere else, and three quarters of
    the page cannot be bound to any data.
    """
    text = " ".join(str(raw or "").split())
    if not text or text == "Does Not Display":
        return []
    marks = [(m.start(), m.end(), m.group(1)) for m in LOCATION.finditer(text)]
    if not marks:
        return []
    out = []
    for i, (_start, end, fid) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        parts = [p.strip() for p in text[end:stop].split(" - ")]
        if len(parts) < 2:
            continue
        section, label = parts[0], parts[-1]
        subsection = " - ".join(parts[1:-1])
        out.append((fid, section, "" if subsection == NO_SUBSECTION else subsection,
                    label))
    return out

ROLES = ("Subject Property", "Land Comparable", "Property Analyzed Not Used",
         "Rental Comparable", "Gross Rent Multiplier Comparable", "Sales Comparable")


def _load(name: str):
    return json.loads((SPEC / name).read_text(encoding="utf-8"))


def _text(value) -> str:
    return " ".join(str(value or "").split())


ENUM_COLUMN = "Supported Data Point Enumerations"

# 'IF PartyRoleType = "Borrower"' -- A-1 states outright which instance a data
# point belongs to, for 520 of its rows.  That is a far better discriminator
# than one inferred from the Additional Context column, because it is written
# per data point rather than per group of them.
CONDITION = re.compile(
    r'^IF\s+(?P<name>[A-Za-z][\w.]*)\s*=\s*"(?P<value>[^"]+)"'
    r'(?:\s+AND\s+Exists)?\s*$', re.I)


def requires(details: str) -> dict[str, str]:
    """The single equality a data point's conditionality states, if it is one."""
    text = " ".join(str(details or "").split())
    m = CONDITION.match(text)
    return {m.group("name"): m.group("value")} if m else {}


def discriminators(delivery: list[dict]) -> dict[str, dict[str, str]]:
    """How to tell one instance of a repeating container from another.

    A container such as VALUATION_COMMENTARY appears many times, once per
    subject a comment is about, and every instance holds the same element --
    ``ValuationCommentText``.  What distinguishes them is a type element beside
    it, and A-1 says which value goes with which comment through its
    "Additional Context" column: the comment row and the type row share a
    context, and the type row names the single enumeration it takes.

    Without this, every commentary field on the page prints every comment in
    the file joined together.
    """
    enum_col = next((c for c in (delivery[0] if delivery else {})
                     if c.startswith(ENUM_COLUMN)), ENUM_COLUMN)
    seen: dict[str, dict[str, set[str]]] = {}
    containers: dict[str, str] = {}
    for row in delivery:
        context = _text(row.get("Additional Context"))
        name = _text(row.get("MISMO Data Point Name"))
        value = " ".join(str(row.get(enum_col) or "").split("\n"))
        value = _text(value)
        if not context or not name or not value:
            continue
        # Only a single fixed value identifies an instance.  A row offering a
        # choice ("Adverse|Beneficial|Neutral") describes what the appraiser
        # may pick, not which instance this is.
        if " " in value or "," in value or "|" in value:
            continue
        # Nor does a yes/no answer.  A-1's format column says which rows are
        # Boolean, and "true" in one of them answers a question about the
        # report -- "did a supervisory appraiser certify it?" -- rather than
        # naming which instance of a block this is.  Read as an identity,
        # AppraiserSupervisorAdditionalCertificationIndicator was stamped into
        # every report that wrote any Valuation Report field, and H-1 then
        # asked for the licence and expiry of a supervisor who does not exist.
        if _text(row.get("UAD Data Point Format Type")) == "Boolean":
            continue
        seen.setdefault(context, {}).setdefault(name, set()).add(value)
        containers.setdefault(context, _text(row.get("MISMO Parent Container")))

    # A data point only identifies an instance if the context pins it to one
    # value.  Where a context lists several -- "Borrower" in one row and
    # "PropertyOwner" in another -- it is describing alternatives, and taking
    # whichever came last would filter out the very instance being looked for.
    out: dict[str, dict[str, str]] = {}
    for context, points in seen.items():
        fixed = {name: next(iter(values))
                 for name, values in points.items() if len(values) == 1}
        if fixed:
            fixed["__container__"] = containers.get(context, "")
            out[context] = fixed
    return out


def build() -> dict:
    delivery = _load("delivery_spec.json")
    enums = _load("enumerations.json")
    rules = _load("compliance_rules.json")
    display = _load("display_rules.json")["by_field_id"]
    supp = _load("supplements.json")

    fields: dict[str, dict] = {}
    unlocated = 0

    # ---- A-1: the delivery contract -------------------------------------
    for row in delivery:
        location = _text(row.get("Report Location"))
        places = parse_locations(location)
        if not places:
            if location and location != "Does Not Display":
                unlocated += 1
            continue
        conditionality_details = _text(row.get("Conditionality Details"))
        data_point = {
            "unique_id": _text(row.get("Unique ID")),
            "context": _text(row.get("Additional Context")),
            "requires": requires(conditionality_details),
            "mismo": _text(row.get("MISMO Data Point Name")),
            "attribute": _text(row.get("MISMO Attribute Name")),
            "xpath": _text(row.get("MISMO xPath")),
            "container": _text(row.get("MISMO Parent Container")),
            "format_type": _text(row.get("UAD Data Point Format Type")),
            "format_details": _text(row.get("UAD Data Point Format Details")),
            "conditionality": _text(row.get("Conditionality")),
            "conditionality_details": _text(row.get("Conditionality Details")),
            "cardinality": _text(row.get("Cardinality")),
            "definition": _text(row.get("MISMO Data Point / Attribute Definition")),
            "source": "A-1 Delivery Specification",
        }
        roles = {role for role in ROLES if _text(row.get(role))}
        for fid, section, subsection, label in places:
            entry = fields.setdefault(fid, {
                "field_id": fid, "report_location": "", "locations": [],
                "data_points": [], "roles": set(), "display_rules": [],
                "compliance": [], "grid": {},
            })
            place = {"section": section, "subsection": subsection, "label": label}
            if place not in entry["locations"]:
                entry["locations"].append(place)
            if not entry["report_location"]:
                entry["report_location"] = (
                    f"{section} - {subsection or NO_SUBSECTION} - {label}")
            entry["data_points"].append(dict(data_point))
            entry["roles"] |= roles

    # ---- A-1 enumerations, attached to the data point they belong to -----
    # The enumerations sheet names its columns at length -- the display column
    # is "Output Report Display Text (Not to be Included in the XML File)" --
    # so the columns are found by prefix rather than by an exact title that
    # would silently miss and leave every enumeration without its display text.
    def _column(sample: dict, *prefixes: str) -> str:
        for name in sample:
            flat = " ".join(str(name).split()).casefold()
            if any(flat.startswith(p.casefold()) for p in prefixes):
                return name
        return prefixes[0]

    sample = enums[0] if enums else {}
    value_col = _column(sample, "Supported Enumerations",
                        "Supported Data Point Enumerations")
    display_col = _column(sample, "Output Report Display Text", "URAR Display Value")
    define_col = _column(sample, "Supported Enumerations Definitions",
                         "Enumeration Definition")

    # "<<Does Not Display>>" is the sheet's way of saying this value prints
    # nothing.  Several display cells also carry a stray fragment on a second
    # line ("No\nR", "Condominium\no"), so the display text is the first line.
    NOT_SHOWN = "<<Does Not Display>>"

    def _display(raw) -> str:
        first = str(raw or "").split("\n")[0]
        text = _text(first)
        return "" if text == NOT_SHOWN else text

    by_uid: dict[str, list[dict]] = defaultdict(list)
    for row in enums:
        uid = _text(row.get("Unique ID"))
        if uid:
            # the sheet gives a value's text per Report Location ("4.017: Site
            # - ... - Non-Residential Use" prints "false" as "None"; "Does Not
            # Display" prints nothing): kept so a field reads its own row
            where = _text(row.get("Report Location"))
            m = re.match(r"^(\d+(?:\.\d+)+):", where)
            by_uid[uid].append({
                "value": _text(row.get(value_col)),
                "display": _display(row.get(display_col)),
                "definition": _text(row.get(define_col)),
                "location": m.group(1) if m else ("" if where.casefold().startswith("does not display") else where),
            })
    for entry in fields.values():
        for dp in entry["data_points"]:
            options = [o for o in by_uid.get(dp["unique_id"], []) if o["value"]]
            if options:
                dp["enumerations"] = options

    # ---- B-1: when it shows on the page ---------------------------------
    for fid, rec in display.items():
        entry = fields.setdefault(fid, {
            "field_id": fid, "report_location": "", "locations": [],
            "data_points": [], "roles": set(), "display_rules": [],
            "compliance": [], "grid": {},
        })
        if not entry.get("labels"):
            entry["labels"] = rec["labels"]
        entry["display_rules"] = [
            {**s, "source": "B-1 URAR Implementation Guide"} for s in rec["statements"]
        ]

    # ---- H-1: what a checker rejects ------------------------------------
    # Each rule names the Unique ID it polices, which is the same identifier
    # the delivery spec uses, so the two join on that rather than on any
    # field-ID text that happens to appear in the message.
    fid_by_uid: dict[str, list[str]] = defaultdict(list)
    for fid, entry in fields.items():
        for dp in entry["data_points"]:
            if dp["unique_id"]:
                fid_by_uid[dp["unique_id"]].append(fid)

    orphan_rules = 0
    for row in rules:
        uid = _text(row.get("Unique ID"))
        note = {
            "message_id": _text(row.get("Message ID")),
            "severity": _text(row.get("Severity")),
            "text": _text(row.get("Message Text")),
            "logic": _text(row.get("Rule Logic")),
            "unique_id": uid,
            "data_point": _text(row.get("Primary Data Element")),
            "property_affected": _text(row.get("Property Affected")),
            "section": _text(row.get("Report Section")),
            "subsection": _text(row.get("Report Subsection")),
            "label": _text(row.get("Report Label / Value")),
            "xpath": _text(row.get("xPath")),
            "source": "H-1 UAD Compliance Rules v1.5",
        }
        targets = fid_by_uid.get(uid, [])
        if not targets:
            orphan_rules += 1
            continue
        for fid in targets:
            fields[fid]["compliance"].append(note)

    # ---- the comparable grids, as their own ordered structure ------------
    # A grid row is not a field ID; it is a row of the grid that draws on one
    # or more fields.  Keeping it as its own list preserves the row order the
    # spec fixes, which the report has to reproduce exactly.
    def _flag(row: dict, *names: str) -> bool:
        for key, value in row.items():
            flat = " ".join(str(key).split()).lower()
            if any(n in flat for n in names):
                return bool(str(value or "").strip())
        return False

    grid_rows = []
    for order, row in enumerate(supp.get("f1_sales_rows", []), start=1):
        label = _text(row.get("Report Label"))
        if not label:
            continue
        always = _text(row.get("Row Always Displays"))
        grid_rows.append({
            "order": order,
            "label": label,
            "heading": always.lower() == "heading",
            "always": bool(always) and always.lower() != "heading",
            "if_applicable": _flag(row, "if applicable"),
            "if_relevant": _flag(row, "if relevant"),
            "adjustable": _flag(row, "adjustable"),
            "source": "F-1 Supplement - Summary of Rows in Comparable Grids",
        })

    for entry in fields.values():
        entry["roles"] = sorted(entry["roles"])

    _inherit_requires(fields)
    _context_requires(fields)

    return {
        "discriminators": discriminators(delivery),
        "sources": {
            "delivery": "Appendix A-1 URAR Delivery Specification v1.4",
            "enumerations": "Appendix A-1 UAD Enumerations",
            "display": "Appendix B-1 URAR Implementation Guide v1.4",
            "compliance": "Appendix H-1 UAD Compliance Rules v1.5",
            "grids": "Appendix F-1 / B-1 Comparable Grid supplements",
        },
        "unlocated_delivery_rows": unlocated,
        "orphan_compliance_rules": orphan_rules,
        "sales_grid_rows": grid_rows,
        "fields": fields,
    }


def _below_property(xpath: str) -> str:
    return xpath.split("/PROPERTIES/PROPERTY/", 1)[1] if "/PROPERTIES/PROPERTY/" in xpath else ""


def _contradicts(own: str, borrowed: dict[str, str], subject_row: bool) -> bool:
    """A row's own stated condition rules out the one it would borrow.

    Either it names the same data point with another value (14.004
    AmenityCount: 'AmenityCategoryType = "OutdoorAccessories"', not the
    borrowed "Miscellaneous"), or it is the subject's own row with a condition
    that does not mention the borrowed point at all (2.023 InspectionDate:
    "IF (PropertyExteriorInspectionMethodType = Physical OR ...)" -- the PDR
    row's PropertyDataReportIndicator = "true" hid every D-1 inspection date).
    A comparable's row ("IF @ValuationUseType = SalesComparable ...") still
    borrows the subject's discriminator, which is what this is for."""
    for name, value in borrowed.items():
        named = re.findall(re.escape(name) + r'\s*=\s*"([^"]*)"', own)
        if named and value not in named:
            return True
        if subject_row and not named and name not in own:
            return True
    return False


def _context_requires(fields: dict[str, dict]) -> int:
    """Data points A-1 files under one "Additional Context" in one container
    are one block's: "Subject Property: Appraiser Property Inspection" holds
    Exterior (2.021) and Interior (2.022), both stated for PartyRoleType =
    "Appraiser", and Inspection Date (2.023), stated for neither.  Without the
    shared discriminator the date was read from whichever INSPECTION came
    first -- the property data collector's (Condo1) or one without a date
    (SF1).  A point with no condition of its own takes its context siblings'
    when they all agree; recorded as ``requires_from``."""
    groups: dict[tuple[str, str], list[tuple[str, dict]]] = defaultdict(list)
    for entry in fields.values():
        for dp in entry["data_points"]:
            # only the party's role names *which* block this is; any other
            # condition ("... = Other" for an Other-description) is the
            # point's own and does not pass to its neighbours
            if (dp.get("requires") and set(dp["requires"]) == {"PartyRoleType"}
                    and dp.get("context") and dp.get("container")):
                groups[(dp["context"], dp["container"])].append((dp.get("unique_id", ""), dp["requires"]))
    n = 0
    for entry in fields.values():
        for dp in entry["data_points"]:
            if (dp.get("requires") or not dp.get("context") or not dp.get("container")
                    or dp.get("mismo") == "PartyRoleType"):
                continue
            found = groups.get((dp["context"], dp["container"]), [])
            if len({json.dumps(r, sort_keys=True) for _u, r in found}) != 1:
                continue
            dp["requires"] = dict(found[0][1])
            dp["requires_from"] = found[0][0]
            n += 1
    return n


def _inherit_requires(fields: dict[str, dict]) -> int:
    """A comparable's row often lacks the discriminator A-1 states for the
    subject's row of the very same element in the very same container: A-1
    says `IF ImprovementComponentType = "Flooring"` for the subject's overall
    flooring (0700.0122) and nothing for the comparable's (1800.0336), yet both
    live in INTERIOR_COMPONENT, told apart only by that type.  Without it a
    write lands in whichever INTERIOR_COMPONENT exists (the walls-and-ceiling
    one) and TOTAL, reading the Flooring one, finds nothing (CATALOG E-046).
    So a data point without a stated condition takes the condition of the
    same data point at the same path below PROPERTY, when all such rows agree.
    Recorded as ``requires_from`` so it is visible as derived."""
    known: dict[tuple[str, str], list[tuple[str, dict]]] = {}
    for entry in fields.values():
        for dp in entry["data_points"]:
            tail = _below_property(dp.get("xpath", ""))
            if dp.get("requires") and tail:
                known.setdefault((dp.get("mismo", ""), tail), []).append((dp.get("unique_id", ""), dp["requires"]))
    n = 0
    for entry in fields.values():
        for dp in entry["data_points"]:
            tail = _below_property(dp.get("xpath", ""))
            if dp.get("requires") or not tail:
                continue
            own = " ".join(str(dp.get("conditionality_details") or "").split())
            found = known.get((dp.get("mismo", ""), tail), [])
            conds = {json.dumps(r, sort_keys=True) for _u, r in found}
            if len(conds) == 1 and own and _contradicts(own, found[0][1], "Subject Property" in entry.get("roles", [])):
                continue
            if len(conds) == 1:
                dp["requires"] = dict(found[0][1])
                dp["requires_from"] = found[0][0]
                n += 1
    return n


def main() -> None:
    index = build()
    out = SPEC / "field_index.json"
    out.write_text(json.dumps(index, indent=1), encoding="utf-8")
    fields = index["fields"]
    with_dp = sum(1 for f in fields.values() if f["data_points"])
    with_rule = sum(1 for f in fields.values() if f["display_rules"])
    with_enum = sum(1 for f in fields.values()
                    if any("enumerations" in dp for dp in f["data_points"]))
    with_comp = sum(1 for f in fields.values() if f["compliance"])
    linked = sum(len(f["compliance"]) for f in fields.values())
    grid = index["sales_grid_rows"]
    print(f"-> {out} ({out.stat().st_size / 1024:.0f} KB)")
    print(f"   Report Field IDs .................. {len(fields)}")
    print(f"   with an A-1 delivery data point ... {with_dp}")
    print(f"   with enumerated values ............ {with_enum}")
    print(f"   with a B-1 display rule ........... {with_rule}")
    print(f"   with an H-1 compliance rule ....... {with_comp}"
          f"  ({linked} links, {index['orphan_compliance_rules']} rules unattached)")
    print(f"   sales-grid rows ................... {len(grid)}"
          f"  ({sum(1 for g in grid if g['heading'])} headings,"
          f" {sum(1 for g in grid if g['always'])} always,"
          f" {sum(1 for g in grid if g['adjustable'])} adjustable)")
    sections = defaultdict(int)
    for f in fields.values():
        sections[f["field_id"].split(".")[0]] += 1
    print(f"   sections represented .............. {len(sections)} of 29")


if __name__ == "__main__":
    main()
