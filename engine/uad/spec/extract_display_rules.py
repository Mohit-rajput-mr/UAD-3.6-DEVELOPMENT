"""Lift Appendix B-1's display-rule tables out of the PDF as data.

B-1 states, for every Report Field ID, the report label, the MISMO data point
behind it, and the condition under which it appears on the page.  That is the
conditionality engine for 29 sections and roughly 1,400 fields, and it exists
only as tables inside a 401-page PDF.  Hand-transcribing it is the mistake this
project has already made once, so we read the tables instead.

The tables are not uniformly shaped: the header spans two or three rows, merged
cells push the columns around from page to page, and a row's text can continue
onto the next page under a repeated header.  So columns are identified by what
their header says rather than by position, and a row with no field ID is
treated as a continuation of the one above it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

FID = re.compile(r"^\d{1,2}\.\d{2,3}(?:\.\d{1,2})?$")
UID = re.compile(r"^\d{4}\.\d{4}$")

# A chapter heading is a two-digit number and a name.  Several carry a suffix
# naming the instance -- "10 Unit Interior - [Outbuilding Type] - [Unit
# Identifier]" -- so the match stops at the first dash or bracket.
CHAPTER = re.compile(r"^(\d{2})\s+([A-Za-z][A-Za-z ,/&']*)")

# The 29 sections and their names, from Appendix F-1 "URAR Section
# Organization" (p11-12).  A heading line is only accepted as a chapter break
# when its number and name agree with this list, which keeps stray text such as
# a lone "29 Certifications" from opening a section of its own.
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

ROLES = (
    ("field_id",   ("report field id", "reportfield id", "report field")),
    ("label",      ("report label",)),
    ("uid",        ("unique id",)),
    ("mismo",      ("mismo data point", "mismo attribute")),
    ("rule",       ("display rules", "conditionality")),
    ("source_fid", ("source field id",)),
    ("origin",     ("original section",)),
)


def _role(header: str) -> str | None:
    h = " ".join(header.lower().split())
    for name, keys in ROLES:
        if any(k in h for k in keys):
            return name
    return None


@dataclass
class Rule:
    field_id: str
    label: str = ""
    uid: str = ""
    mismo: str = ""
    rule: str = ""
    section: str = ""
    table: str = ""
    page: int = 0
    source_fid: str = ""
    origin: str = ""

    def merge(self, other: "Rule") -> None:
        """Absorb a continuation row, which carries only trailing prose."""
        for name in ("label", "uid", "mismo", "rule"):
            extra = getattr(other, name)
            if not extra:
                continue
            have = getattr(self, name)
            setattr(self, name, f"{have} {extra}".strip() if have else extra)


def _clean(cell) -> str:
    return " ".join(str(cell or "").split())


def _split_ids(cell: str) -> list[str]:
    """A cell may carry several field IDs: '1.033 | 1.040 | 1.048'."""
    return [p for p in re.split(r"[|,/]|\s+", cell) if FID.match(p)]


def extract(pdf: Path) -> list[Rule]:
    doc = pymupdf.open(pdf)
    rules: list[Rule] = []
    section = ""
    try:
        for pno in range(doc.page_count):
            page = doc[pno]

            # The chapter heading names the section the tables on this page
            # belong to, and carries forward until the next heading.
            for line in page.get_text().splitlines():
                m = CHAPTER.match(line.strip())
                if not m:
                    continue
                number = int(m.group(1))
                name = SECTIONS.get(number)
                if name and m.group(2).strip().lower().startswith(name.split()[0].lower()):
                    section = f"{number} {name}"

            for table in page.find_tables().tables:
                grid = table.extract()
                if not grid:
                    continue
                width = max(len(r) for r in grid)
                caption = _clean(grid[0][0])

                # The header spans several rows and its pieces are not
                # adjacent -- "Report" can sit two rows above its own
                # "Field ID".  Take the header to run down to the last row near
                # the top that still names a column.
                header_at, named = None, {}
                for ri in range(min(8, len(grid))):
                    roles = {ci: _role(_clean(grid[ri][ci]))
                             for ci in range(len(grid[ri]))}
                    roles = {ci: r for ci, r in roles.items() if r}
                    if roles:
                        header_at = ri
                        named.update(roles)
                # Most tables state a Display Rules column.  The Summary and
                # Reconciliation chapters instead say where each redisplayed
                # value comes from, which is just as much a rule about what
                # appears on the page, so those columns qualify too.
                if header_at is None or not (
                        {"rule", "origin", "source_fid"} & set(named.values())):
                    continue

                body = grid[header_at + 1:]
                if not body:
                    continue

                # Merged cells routinely shift a header label one column away
                # from the data it labels, so the two columns that can be
                # recognised by their content -- field ID and unique ID -- are
                # found by looking at the data instead of the header.
                def _best(pattern) -> int | None:
                    counts = [sum(1 for row in body
                                  if ci < len(row) and pattern(_clean(row[ci])))
                              for ci in range(width)]
                    top = max(counts) if counts else 0
                    return counts.index(top) if top else None

                fid_col = _best(lambda s: bool(_split_ids(s)))
                if fid_col is None:
                    continue
                uid_col = _best(lambda s: bool(UID.match(s)))

                columns = {ci: r for ci, r in named.items()
                           if r not in ("field_id", "uid")
                           and ci != fid_col and ci != uid_col}
                columns[fid_col] = "field_id"
                if uid_col is not None:
                    columns[uid_col] = "uid"
                if not ({"rule", "origin", "source_fid"} & set(columns.values())):
                    continue

                current: Rule | None = None
                for row in body:
                    cells = {role: _clean(row[ci])
                             for ci, role in columns.items() if ci < len(row)}
                    ids = _split_ids(cells.get("field_id", ""))
                    if not ids:
                        # An irregular table (the Supervisory Appraiser
                        # Certifications heading, B-1 p396) can set one row's
                        # ID a column away from the rest.  A lone ID in a
                        # column no header names is that row's own.
                        stray = [fid for ci, cell in enumerate(row)
                                 if ci not in columns for fid in _split_ids(_clean(cell))]
                        if len(stray) == 1:
                            ids = stray
                    carried = {
                        "label": cells.get("label", ""),
                        "uid": cells.get("uid", "") if UID.match(cells.get("uid", "")) else "",
                        "mismo": cells.get("mismo", ""),
                        "rule": cells.get("rule", ""),
                        "source_fid": cells.get("source_fid", ""),
                        "origin": cells.get("origin", ""),
                    }
                    if ids:
                        for fid in ids:
                            current = Rule(field_id=fid, section=section,
                                           table=caption, page=pno + 1, **carried)
                            rules.append(current)
                    elif current is None or not any(carried.values()):
                        continue
                    elif carried["uid"]:
                        # A row with its own Unique ID but no field ID is a
                        # further data point feeding the same field, not a
                        # wrapped line -- keep it as its own statement.
                        rules.append(Rule(field_id=current.field_id, section=section,
                                          table=caption, page=pno + 1, **carried))
                    else:
                        current.merge(Rule(field_id="", **carried))
    finally:
        doc.close()
    return rules


def consolidate(rules: list[Rule]) -> dict[str, dict]:
    """One entry per field ID, keeping every statement B-1 makes about it.

    A field ID legitimately appears in several tables -- once where it is
    captured and again where it is redisplayed -- so the statements are kept as
    a list rather than collapsed into the last one seen.
    """
    out: dict[str, dict] = {}
    for r in rules:
        e = out.setdefault(r.field_id, {"field_id": r.field_id, "labels": [],
                                        "uids": [], "mismo": [], "statements": []})
        for key, value in (("labels", r.label), ("uids", r.uid), ("mismo", r.mismo)):
            if value and value not in e[key]:
                e[key].append(value)
        if r.rule:
            e["statements"].append({"section": r.section, "table": r.table,
                                    "page": r.page, "rule": r.rule})
    return out


def main() -> None:
    # UAD36_SPECS, else the folder's own specs/official (see paths.py)
    root = Path(__import__("os").environ.get("UAD36_SPECS")
                or Path(__file__).resolve().parents[3] / "specs" / "official")
    pdf = next(root.rglob("*B-1 URAR Implementation Guide v1.4.pdf"))
    rules = extract(pdf)
    merged = consolidate(rules)
    out = Path("engine/spec/display_rules.json")
    out.write_text(json.dumps(
        {"source": pdf.name, "rows": len(rules), "fields": len(merged),
         "by_field_id": merged}, indent=1), encoding="utf-8")
    print(f"{pdf.name}")
    print(f"   table rows extracted ..... {len(rules)}")
    print(f"   distinct Report Field IDs  {len(merged)}")
    print(f"   -> {out} ({out.stat().st_size / 1024:.0f} KB)")
    sections = sorted({r.section for r in rules if r.section},
                      key=lambda s: int(s.split()[0]))
    print(f"   sections seen ............ {len(sections)}")
    for s in sections:
        n = sum(1 for r in rules if r.section == s)
        print(f"      {s:<44} {n:>4} rows")


if __name__ == "__main__":
    main()
