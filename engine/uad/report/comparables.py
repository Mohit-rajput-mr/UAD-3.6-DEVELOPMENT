"""The comparable grids, built from the B-1 supplement rather than by hand.

Appendix B-1's "Comparable Grids" workbook is the grid, stated row by row: the
row's label, whether it always displays or only when applicable, the Report
Field ID the subject's value comes from, the field ID each comparable's value
comes from, the field ID of the adjustment beside it, and the MISMO data point
behind all three.  So the grid is read out of that file at build time; nothing
about its 167 rows is typed in here.

The geometry is the measured one: the grid ignores the body's two columns and
runs the full 45-pica measure, with a 106 pt row label, a 108.5 pt subject
column, and three comparable columns of 108.5 pt each split into a 66 pt
description and a 42.5 pt adjustment.  Row labels sit 4 pt in from the left;
every value is set flush right, 4 pt in from its own column's right edge.

A row with nothing in it anywhere is dropped unless the workbook marks it
"always", and a cell with no value prints an em dash, which is what the samples
show.
"""
from __future__ import annotations

import json
from copy import deepcopy
import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from lxml import etree

from .. import bind, edit
from . import dashes, page, typography

XLINK = "http://www.w3.org/1999/xlink"

SPEC = Path(__file__).resolve().parents[2] / "spec"
#: How many comparables each grid holds, (fewest, most).  The GSE appendices
#: we hold state no count; these are WinTOTAL's measured grid limits
#: (knowledge/total/FINDINGS.md: sales 3-24, rental 1-24, GRM 3-24), which the
#: owner asked the editor to keep.  All twelve D-1 samples sit inside them
#: (engine/tests/test_comparable_limits.py).  "Not used" has no limit.
LIMITS = {"sales": (3, 24), "rental": (1, 24), "grm": (3, 24)}


def limit_problem(kind: str, after: int) -> str:
    """Why a grid may not hold ``after`` comparables, or ''.  A grid with
    none is one the report does not use; the sales grid always is."""
    if kind not in LIMITS:
        return ""
    low, high = LIMITS[kind]
    if after > high:
        return f"The {kind} grid holds at most {high} comparables."
    if after < low and (after > 0 or kind == "sales"):
        return (f"The {kind} grid needs at least {low} comparable{'s' if low > 1 else ''}; "
                f"replace this one instead of removing it.")
    return ""

SHEETS = {
    "sales": ("b1_sales_grid", "SalesComparable", "Sales Comparison Approach"),
    "rental": ("b1_rental_grid", "RentalComparable", "Rental Information"),
    "grm": ("b1_grm_grid", "GrossRentMultiplierComparable", "Income Approach"),
    # A-1 gives this its own six field IDs (22.17.01-06) but B-1's Comparable
    # Grids workbook has no sheet for it -- it is a short list of rejected
    # comparables, not an adjustment grid, so `rows()` returns it directly
    # below rather than reading a workbook that does not cover it.
    "not_used": (None, "PropertyAnalyzedNotUsed",
                "Additional Properties Analyzed Not Used"),
}

# A-1's own field IDs for the "Additional Properties Analyzed Not Used" list
# (Sales Comparison Approach): confirmed printing in the official Condo1,
# Coop1, SF1 and SF5 samples ("# / Property Address / Sale Date / Status /
# Reason Not Used / Comment").  Every SF1 template case already carries five
# of these PROPERTY elements, fully populated, invisible until this list
# reads and edits them the same way the sales/rental/GRM grids do.
NOT_USED_FIELDS = (
    ("#", "22.17.01"), ("Property Address", "22.17.02"),
    ("Sale Date", "22.17.03"), ("Status", "22.17.04"),
    ("Reason Not Used", "22.17.05"), ("Comment", "22.17.06"),
)
EM_DASH = "—"
TICK = "√"          # the workbook marks a column with a check mark

# The shapes a Report Field ID actually takes across the field index: 1.001,
# 24.010, 22.01.17, 1.033.1, 24.026.1.  A pattern that only allowed two-digit
# groups matched the sales grid and silently dropped the whole GRM grid, whose
# identifiers are 24.008 rather than 24.00.08.
FID = re.compile(r"^\d{1,2}\.\d{2,3}(?:\.\d{1,2})?$")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _ticked(value: Any) -> bool:
    text = _clean(value)
    return bool(text) and text not in ("N/A", "-")


@dataclass
class GridRow:
    order: int
    label: str
    heading: bool = False
    always: bool = False
    if_applicable: bool = False
    if_relevant: bool = False
    subject_fid: str = ""
    comp_fid: str = ""
    adjust_fid: str = ""
    data_point: str = ""
    rules: str = ""
    adjust_type: str = ""
    # An added row ("[Additional Row]") is one the appraiser names.  Once
    # named it behaves as an ordinary row whose label is that name, so the
    # expansion happens in one place and every reader sees the same rows.
    item_name: str = ""
    container: str = ""
    container_kind: str = ""       # which grid this row belongs to
    new_item: bool = False
    named: Any = None              # how the row is stored, when it is a named one
    # B-1's "Display Em-Dash for Subject / Comp when ..." sentences for this row
    # ("" where the table has none for it)
    dash_subject: str = ""
    dash_comp: str = ""

    @property
    def adjustable(self) -> bool:
        return bool(self.adjust_fid)

    def to_json(self) -> dict[str, Any]:
        return self.__dict__.copy()


@lru_cache(maxsize=8)
def rows(kind: str = "sales") -> list[GridRow]:
    """Every row of one grid, in the order the workbook lists them."""
    sheet, _role, _section = SHEETS[kind]
    if kind == "not_used":
        return [GridRow(order=i, label=label, comp_fid=fid, always=True)
                for i, (label, fid) in enumerate(NOT_USED_FIELDS, start=1)]
    data = json.loads((SPEC / "supplements.json").read_text(encoding="utf-8"))
    raw = data.get(sheet, [])
    if not raw:
        return []

    # The sheet carries two headers: the merged title above a group of columns,
    # which survives as the dict key, and the column's own name in the first
    # data row.  Both are needed -- the comparable's field ID and the
    # adjustment's field ID are *both* headed "FID", and are told apart only by
    # the group they sit under.
    header = {key: _clean(value) for key, value in raw[0].items()}

    def column(*, key_has: str = "", named: str = "") -> str:
        for key, name in header.items():
            group = " ".join(str(key).split()).casefold()
            label = name.casefold()
            if key_has and key_has.casefold() not in group:
                continue
            if named and named.casefold() not in label:
                continue
            if key_has or named:
                return key
        return ""

    def pick(want: str, prefer: tuple[str, ...] = ()) -> str:
        """The column whose name contains ``want``, preferring one that also
        mentions this grid.  Each sheet names both the field ID in the source
        section and the field ID used in the grid, and only the second belongs
        to the grid -- taking the first fills every row from the wrong place.
        """
        hits = [key for key, name in header.items() if want in name.casefold()]
        for token in prefer:
            for key in hits:
                if token in header[key].casefold():
                    return key
        return hits[0] if hits else ""

    col_label = next(iter(header))
    col_always = column(named="always")
    col_applicable = column(named="if applicable")
    col_relevant = column(named="if relevant")
    # Sales heads the subject's grid column " Subject FID in Sales Comp";
    # rental and GRM say "... in Rental Grid" / "... in GRM Comp Grid".
    col_subject = pick("subject fid", ("in sales comp", "grid"))
    # Sales heads the comparable's column simply "FID" under a group naming the
    # role; rental and GRM spell out "Comparable FID in ... Grid" and put it in
    # a column of its own, outside that group.
    col_comp = (pick("comparable fid", ("grid",))
                or column(key_has="comparables", named="fid"))
    col_adjust = column(key_has="adjustments", named="fid")
    # This column is titled in the merged header above it; its own first row is
    # blank, so it is found by the group key, not by the column name.
    col_point = (column(key_has="mismo data point")
                 or column(named="mismo data point"))
    # the workbook's first column is "Row Display Rules" (the label); the rules
    # themselves sit under "Display Rules / If SalesComparisonApproachIndicator..."
    col_rules = next((k for k in header
                      if " ".join(str(k).split()).casefold().startswith("display rules")), "")
    # The column beside the adjustment's field ID names the
    # ComparableAdjustmentType that identifies which adjustment the row means.
    # Without it every adjustable row reads the first adjustment on the
    # comparable and the whole column repeats one figure.
    col_adjust_type = column(named="comparableadjustmenttype")
    if not col_adjust_type and col_adjust:
        keys = list(header)
        idx = keys.index(col_adjust)
        col_adjust_type = keys[idx + 1] if idx + 1 < len(keys) else ""

    out: list[GridRow] = []
    for i, entry in enumerate(raw[1:], start=1):
        label = _clean(entry.get(col_label))
        if not label:
            continue
        subject = _clean(entry.get(col_subject))
        comp = _clean(entry.get(col_comp))
        adjust = _clean(entry.get(col_adjust))
        point = _clean(entry.get(col_point))
        heading = not (FID.match(subject) or FID.match(comp)) and not point
        out.append(GridRow(
            order=i, label=label, heading=heading,
            always=_ticked(entry.get(col_always)),
            if_applicable=_ticked(entry.get(col_applicable)),
            if_relevant=_ticked(entry.get(col_relevant)),
            subject_fid=subject if FID.match(subject) else "",
            comp_fid=comp if FID.match(comp) else "",
            adjust_fid=adjust if FID.match(adjust) else "",
            adjust_type=_clean(entry.get(col_adjust_type)),
            data_point=point,
            rules=_clean(entry.get(col_rules))[:400],
        ))
    _fill_subject_fids(out)
    _attach_dash_sentences(kind, out)
    return out


def _fill_subject_fids(out: list[GridRow]) -> None:
    """A row whose own text says it has a subject value, but whose subject
    column reads N/A.

    "Contract Price" and "Contract Date" say "Subject: Display if
    SalesContractReviewedIndicator = true", and the Contract Price note names
    the pair ("displays in 22.01.04/22.01.22"), yet the workbook's subject FID
    column is N/A for both -- so the subject's price and date, which the D-1
    samples print, were never read.  A-1 files the subject's value under the
    same label in the same group (22.01.04 beside the comparable's 22.01.22);
    it is taken only when that is the one field no row already uses.
    """
    used = {x for r in out for x in (r.subject_fid, r.comp_fid, r.adjust_fid) if x}
    index = bind._index()
    squash = lambda t: re.sub(r"[^a-z0-9]", "", t.casefold())
    for row in out:
        if row.heading or row.subject_fid or not row.comp_fid:
            continue
        if not re.search(r"\bSubject:\s*Display", row.rules):
            continue
        group = row.comp_fid.rsplit(".", 1)[0]
        found = [fid for fid, entry in index.items()
                 if fid.rsplit(".", 1)[0] == group and fid not in used
                 and any(squash(loc.get("label", "")) == squash(row.label)
                         for loc in entry.get("locations") or [])]
        if len(found) == 1:
            row.subject_fid = found[0]
            used.add(found[0])


@lru_cache(maxsize=1)
def _dash_table() -> dict[str, list[tuple[str, str, str]]]:
    """B-1's em-dash table (``b1_em_dashes``), cut into its three grids:
    kind -> [(row label, Subject sentence, Comp sentence)] in the table's order."""
    data = json.loads((SPEC / "supplements.json").read_text(encoding="utf-8")).get("b1_em_dashes", [])
    if not data:
        return {}
    keys = list(data[0])
    label_key = next(k for k in keys if "label" in k.casefold())
    subject_key = next(k for k in keys if "subject" in k.casefold())
    comp_key = next(k for k in keys if "comp" in k.casefold())
    starts = {"sales": "Sales Comparison Approach", "grm": "Income Approach (GRM Comps)",
              "rental": "Rental Information (Rental Comps)"}
    at = {kind: next((i for i, r in enumerate(data) if _clean(r.get(label_key)) == head), None)
          for kind, head in starts.items()}
    bounds = sorted((i, kind) for kind, i in at.items() if i is not None)
    out: dict[str, list[tuple[str, str, str]]] = {}
    for n, (i, kind) in enumerate(bounds):
        end = bounds[n + 1][0] if n + 1 < len(bounds) else len(data)
        out[kind] = [(_clean(r.get(label_key)), _clean(r.get(subject_key)), _clean(r.get(comp_key)))
                     for r in data[i:end]]
    return out


def not_used_dash(root: etree._Element, prop: etree._Element, label: str) -> bool:
    """Does an empty cell of the "Additional Properties Analyzed Not Used" list
    print an em-dash?  Its own rows in B-1's table decide, the same way the
    grid's do (Sale Date: ListingStatusType <> "SettledSale")."""
    table = _dash_table().get("sales") or []
    squash = lambda t: re.sub(r"[^a-z0-9]", "", t.casefold())
    start = next((i for i, row in enumerate(table)
                  if squash(row[0]).startswith("additionalpropertiesanalyzednotused")), None)
    if start is None:
        return False
    for name, _subject, comp in table[start + 1:start + 8]:
        if squash(name) == squash(label):
            return dashes.decide(comp, dashes.Cell(root, prop, False, [True], 0))
    return False


def _attach_dash_sentences(kind: str, out: list[GridRow]) -> None:
    """Give each row its two sentences.  The workbook and the em-dash table list
    a grid's rows in the same order, so a row takes the next sentence pair whose
    label it shares; labels repeat (Roof, [Additional Row]) and only the order
    tells them apart."""
    table = _dash_table().get(kind) or []
    squash = lambda t: re.sub(r"[^a-z0-9]", "", t.casefold())
    at = 0
    for row in out:
        for j in range(at, min(at + 12, len(table))):
            if squash(table[j][0]) == squash(row.label):
                row.dash_subject, row.dash_comp = table[j][1], table[j][2]
                at = j + 1
                break


# --------------------------------------------------------------------------
# Reading a case
# --------------------------------------------------------------------------
# The samples carry PropertyOrdinalNumber in COMPARABLE_DETAIL.  Reading it
# with a descendant search but writing it as a child of PROPERTY_DETAIL creates
# a second element the reader never reaches, so a reorder renumbers nothing and
# the grid keeps its old order.  One accessor, so both ends agree.
ORDINAL_PATH = ("COMPARABLE", "COMPARABLE_DETAIL")


def ordinal_node(prop: etree._Element, *, create: bool = False):
    """The PropertyOrdinalNumber this property is ordered by."""
    node = prop.find(f".//{{{bind.MISMO}}}PropertyOrdinalNumber")
    if node is not None or not create:
        return node
    from .. import edit

    parent, _created = edit.ensure_path(prop, list(ORDINAL_PATH))
    return edit.insert_ordered(parent, "PropertyOrdinalNumber")


# The document already identifies a comparable durably: PROPERTY carries an
# xlink:label that RELATIONSHIP elements point at, and reordering never
# rewrites it.  That label is the identity; the number is only where the
# property currently sits.
LABEL_STEM = {
    "SalesComparable": "PROPERTY_SALESCOMP",
    "RentalComparable": "PROPERTY_RENTALCOMP",
    "GrossRentMultiplierComparable": "PROPERTY_GRMCOMP",
}


def label_of(prop: etree._Element) -> str:
    return prop.get(f"{{{XLINK}}}label") or ""


def ensure_label(root: etree._Element, prop: etree._Element, role: str) -> str:
    """The property's durable identifier, minted if it has none yet."""
    label = label_of(prop)
    if label:
        return label
    taken = {label_of(p) for p in root.iter(f"{{{bind.MISMO}}}PROPERTY")}
    stem = LABEL_STEM.get(role, "PROPERTY_COMP")
    n = 1
    while f"{stem}{n}" in taken:
        n += 1
    label = f"{stem}{n}"
    prop.set(f"{{{XLINK}}}label", label)
    return label


def labels(root: etree._Element, role: str) -> list[str]:
    """Each comparable's identifier, in the order the report numbers them."""
    return [label_of(p) for p in properties(root, role)]


def properties(root: etree._Element, role: str) -> list[etree._Element]:
    """The comparables of one kind, in the order the report numbers them."""
    found = [p for p in root.iter(f"{{{bind.MISMO}}}PROPERTY")
             if p.get("ValuationUseType") == role]

    def ordinal(prop: etree._Element) -> int:
        node = ordinal_node(prop)
        try:
            return int((node.text or "0").strip()) if node is not None else 0
        except ValueError:
            return 0

    return sorted(found, key=ordinal)


def add_property(tree, role: str) -> int:
    """Add another comparable of this kind, numbered after the last one.

    A comparable is a PROPERTY carrying the role as its @ValuationUseType and a
    PropertyOrdinalNumber that the grid orders by, so a new one is created with
    both -- an unnumbered property would sort to the front of the grid.
    """
    from .. import edit

    root = tree.getroot() if hasattr(tree, "getroot") else tree
    existing = properties(root, role)
    holder = None
    for prop in root.iter(f"{{{bind.MISMO}}}PROPERTY"):
        holder = prop.getparent()
        break
    if holder is None:
        raise ValueError("this case has no PROPERTIES container to add to")

    # after the last PROPERTY, before anything the XSD lists later
    node = edit.insert_ordered(holder, "PROPERTY")
    node.set("ValuationUseType", role)
    number = len(existing) + 1
    ordinal_node(node, create=True).text = str(number)
    ensure_label(root, node, role)
    return number


def binding_of(field_id: str):
    """The binding for a grid field.

    The page model only knows the fields the older label-driven renderer laid
    out; the grids ask for plenty it never had a row for (an additional line
    item, a not-used property), and a cell whose binding came back empty read
    and wrote nothing at all -- silently.  A-1's own index answers for those.
    """
    pf = _by_field_id().get(field_id)
    if pf is not None:
        return pf.binding
    return bind.binding_for(field_id)


@lru_cache(maxsize=1)
def _by_field_id() -> dict[str, Any]:
    out = {}
    for fields in bind.page_model().values():
        for pf in fields:
            out.setdefault(pf.field_id, pf)
    return out


# Three rows of the outbuilding block share one Report Field ID and one data
# point (RoomType); which room each means is spelled by its own label, exactly
# as the utilities rows are ("Gas" is a UtilityType).  So the label is matched
# against the data point's own A-1 enumeration and used to pick the instance.
#: B-1 names the instance a description row reads ('Display when
#: (ImprovementComponentType = "WallsAndCeiling")', 'RoomType = "Kitchen"'):
#: Overall Flooring and Walls and Ceiling read the same data point and are
#: told apart only by this (D-1 SF3 printed the flooring text twice)
_RULE_MARK = re.compile(r'\b(ImprovementComponentType|RoomType)(?:\s*\([^)]*\))?\s*=\s*["\u201c]([A-Za-z]+)["\u201d]')


def _row_marks(row: "GridRow | None", binding) -> dict[str, str]:
    if row is not None and row.rules:
        found = dict(_RULE_MARK.findall(row.rules))
        if found:
            return found
    if row is None or not row.data_point or not row.data_point.endswith("Type"):
        return {}
    wanted = [w for w in re.split(r"[^A-Za-z]+", row.label.casefold()) if w]
    if not wanted:
        return {}
    for dp in binding.data_points:
        if dp.get("mismo") != row.data_point:
            continue
        for option in dp.get("enumerations") or []:
            value = option.get("value") or ""
            words = [w.casefold() for w in re.findall(r"[A-Z][a-z]*|[a-z]+", value)]
            if len(wanted) != len(words):
                continue
            if all(any(w.startswith(want.rstrip("s")) for w in words) for want in wanted)                     and all(any(w.rstrip("s").startswith(x) or x.startswith(w.rstrip("s"))
                                for x in [want.rstrip("s") for want in wanted]) for w in words):
                return {row.data_point: value}
    return {}


def _read(root: etree._Element, binding, scope: etree._Element | None,
          marks: dict[str, str] | None = None):
    """The elements a grid cell reads: the first instance of its block, or --
    where B-1 stacks them ("a separate line for each street", each vehicle
    storage, each view) -- every instance."""
    if scope is not None:
        binding = _held_conditions(binding, scope)
    composite = bind.composite_for([dp.get("mismo", "") for dp in binding.data_points])
    if not (composite and composite.stack):
        yield from bind._walk(root, binding, scope, 1, marks)
        return
    # an instance holding nothing (the insertion point a blank case keeps) is
    # passed over, not taken for the end: the garage behind an empty
    # CAR_STORAGE printed nowhere in the grid
    xpath = next((dp.get("xpath", "") for dp in binding.data_points
                  if bind.repeating_container(dp.get("xpath", ""))), "")
    for ordinal in range(1, 25):
        nodes = list(bind._walk(root, binding, scope, ordinal, marks))
        if not nodes and (not xpath or bind.scope_for(root, xpath, scope, ordinal) is None):
            return
        yield from nodes


def _held_conditions(binding, scope: etree._Element):
    """The binding with any A-1 condition dropped whose data point this
    property does not hold at all.  GRM Sale Date (24.018) carries the
    subject's 'IF PriorSalesOrTransfersIndicator = "true"'; a GRM comparable
    has no such indicator, so the condition hid its own sale date (D-1 2-4
    prints 02/24/2019)."""
    changed = False
    points = []
    for dp in binding.data_points:
        req = dp.get("requires") or {}
        keep = {k: v for k, v in req.items()
                if k.startswith(("@", "__")) or next(scope.iter(f"{{{bind.MISMO}}}{k}"), None) is not None}
        if keep != req:
            dp = dict(dp, requires=keep)
            changed = True
        points.append(dp)
    if not changed:
        return binding
    return bind.Binding(binding.field_id, binding.section, binding.subsection, binding.label, points)


def value_for(root: etree._Element, field_id: str,
              scope: etree._Element | None, row: "GridRow | None" = None,
              binding=None) -> str:
    """One grid cell: the value of a field read within one property.

    Areas carry their unit and whole dollars drop their cents, exactly as they
    do elsewhere in the report -- the grid is not a different language.
    """
    if row is not None and row.container and scope is not None:
        # a row the appraiser named keeps its value beside that name, not
        # where the field's own path would otherwise look
        named = row.named
        if named is not None:
            text, _adjust = named_value(scope, named, row.item_name)
            return text
        return ""
    binding = binding or binding_of(field_id)
    if binding is None:
        return ""
    groups = []
    marks = _row_marks(row, binding)
    for name, node in _read(root, binding, scope, marks):
        text = (node.text or "").strip()
        if not text or name in marks:
            continue                 # the row's label already says which type
        text = bind.with_unit(text, node)
        key = bind.instance_of(node)
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        if (name, text) not in groups[-1][1]:
            groups[-1][1].append((name, text))
    if len({k for k, _g in groups}) < len(groups):
        # one block's values arrived apart (a data source's identifier, then
        # every source's type): gather each block's, in document order
        merged: dict[str, list] = {}
        for key, group in groups:
            merged.setdefault(key, []).extend(x for x in group if x not in merged.get(key, []))
        tree = root.getroottree()
        rank = {tree.getpath(e): n for n, e in enumerate(root.iter())}
        groups = sorted(merged.items(), key=lambda kv: rank.get(kv[0], 0))
    shown = bind.display_value([g for _k, g in groups], binding)
    if shown == "$0.00":
        return "$0"                  # D-1 2-4: an unrented unit's Rent Per Finished Area
    return bind.trim_cents(shown, binding.label)


# "None", "No" and "false" answer the question without reporting anything, and
# the samples leave such a row out of the grid rather than print a column of
# negatives (B-1 states each row's rule this way: display when <> "None").
SILENT = {"", "none", "no", "false", "not applicable"}
# ...except where the workbook says the row displays "if Exists": a delivered
# "No" exists (D-1 2-4 prints Furnished / Rent Control / Rent Concessions "No"
# for every rental comparable)
_EXISTS = re.compile(r"display\s+if\s+exists", re.I)


def _told(value: str) -> bool:
    return value.strip().casefold() not in SILENT


def raw_for(root: etree._Element, field_id: str,
            scope: etree._Element | None) -> list[str]:
    """The values behind a grid cell, unformatted."""
    binding = binding_of(field_id)
    if binding is None:
        return []
    return [(node.text or "").strip()
            for _name, node in bind._walk(root, binding, scope, 1)
            if (node.text or "").strip()]


def adjustment_for(root: etree._Element, row: GridRow,
                   prop: etree._Element) -> str:
    """The adjustment on this comparable for this row, and no other.

    A comparable carries many COMPARABLE_ADJUSTMENT elements; the workbook
    names the ComparableAdjustmentType that belongs to each row, and only the
    adjustment carrying that type is the one this row shows.
    """
    if row.container:
        if row.named is None:
            return ""
        _text, amount = named_value(prop, row.named, row.item_name)
        return amount
    if not row.adjust_fid:
        return ""
    want = row.adjust_type
    if not want:
        return value_for(root, row.adjust_fid, prop)
    for node in prop.iter(f"{{{bind.MISMO}}}COMPARABLE_ADJUSTMENT"):
        kind = node.find(f"{{{bind.MISMO}}}ComparableAdjustmentType")
        if kind is None or (kind.text or "").strip() != want:
            continue
        amount = node.find(f"{{{bind.MISMO}}}ComparableAdjustmentAmount")
        if amount is None or not (amount.text or "").strip():
            return ""
        binding = binding_of(row.adjust_fid)
        if binding is None:
            return (amount.text or "").strip()
        return bind.display_value(
            [[("ComparableAdjustmentAmount", (amount.text or "").strip())]],
            binding)
    return ""


def adjustment_value(prop: etree._Element, adjust_type: str) -> str:
    """The raw amount of one named adjustment on this comparable."""
    for node in prop.iter(f"{{{bind.MISMO}}}COMPARABLE_ADJUSTMENT"):
        kind = node.find(f"{{{bind.MISMO}}}ComparableAdjustmentType")
        if kind is not None and (kind.text or "").strip() == adjust_type:
            amount = node.find(f"{{{bind.MISMO}}}ComparableAdjustmentAmount")
            return (amount.text or "").strip() if amount is not None else ""
    return ""


def write_adjustment(prop: etree._Element, adjust_type: str, value: str):
    """Set one named adjustment on one comparable.

    A comparable carries many COMPARABLE_ADJUSTMENT blocks and they are told
    apart only by their ComparableAdjustmentType, so the block carrying this
    row's type is the one written -- creating it if the appraiser is making
    this adjustment for the first time.
    """
    from .. import edit

    text = value.strip()
    target = None
    for node in prop.iter(f"{{{bind.MISMO}}}COMPARABLE_ADJUSTMENT"):
        kind = node.find(f"{{{bind.MISMO}}}ComparableAdjustmentType")
        if kind is not None and (kind.text or "").strip() == adjust_type:
            target = node
            break

    if target is None:
        if not text:
            return edit.Written("", "ComparableAdjustmentAmount", "", "", "", [])
        comparable, _ = edit.ensure_path(prop, ["COMPARABLE"])
        holder, _ = edit.ensure_path(comparable, ["COMPARABLE_ADJUSTMENTS"])
        target = edit.insert_ordered(holder, "COMPARABLE_ADJUSTMENT")
        kind = edit.insert_ordered(target, "ComparableAdjustmentType")
        kind.text = adjust_type

    amount = target.find(f"{{{bind.MISMO}}}ComparableAdjustmentAmount")
    old = (amount.text or "").strip() if amount is not None else ""
    if not text:
        if amount is not None:
            target.remove(amount)
    else:
        if amount is None:
            amount = edit.insert_ordered(target, "ComparableAdjustmentAmount")
        amount.text = text
    return edit.Written("", "ComparableAdjustmentAmount", "", old, text, [])


def write_nth_adjustment(prop: etree._Element, adjust_type: str, k: int, value: str):
    """Set the k-th (0-based) adjustment of a type on one comparable: one per
    unit, ADU, dwelling or outbuilding the row repeats over, in the order the
    grid draws them (``build``'s ``instance``). Blocks before it are created
    empty when missing, so the positions stay as the grid reads them."""
    from .. import edit
    if k <= 0:
        found = [n for n in prop.iter(f"{{{bind.MISMO}}}COMPARABLE_ADJUSTMENT")
                 if (n.findtext(f"{{{bind.MISMO}}}ComparableAdjustmentType") or "").strip() == adjust_type]
        if not found:
            return write_adjustment(prop, adjust_type, value)
    text = value.strip()
    found = [n for n in prop.iter(f"{{{bind.MISMO}}}COMPARABLE_ADJUSTMENT")
             if (n.findtext(f"{{{bind.MISMO}}}ComparableAdjustmentType") or "").strip() == adjust_type]
    if len(found) <= k and not text:
        return edit.Written("", "ComparableAdjustmentAmount", "", "", "", [])
    while len(found) <= k:
        comparable, _ = edit.ensure_path(prop, ["COMPARABLE"])
        holder, _ = edit.ensure_path(comparable, ["COMPARABLE_ADJUSTMENTS"])
        node = edit.insert_ordered(holder, "COMPARABLE_ADJUSTMENT")
        if found:                        # keep the type's blocks together, in order
            found[-1].addnext(node)
        kind = edit.insert_ordered(node, "ComparableAdjustmentType")
        kind.text = adjust_type
        found.append(node)
    target = found[k]
    amount = target.find(f"{{{bind.MISMO}}}ComparableAdjustmentAmount")
    old = (amount.text or "").strip() if amount is not None else ""
    if not text:
        if amount is not None:
            target.remove(amount)
    else:
        if amount is None:
            amount = edit.insert_ordered(target, "ComparableAdjustmentAmount")
        amount.text = text
    return edit.Written("", "ComparableAdjustmentAmount", "", old, text, [])


def nth_adjustment_value(prop: etree._Element, adjust_type: str, k: int) -> str:
    found = [n for n in prop.iter(f"{{{bind.MISMO}}}COMPARABLE_ADJUSTMENT")
             if (n.findtext(f"{{{bind.MISMO}}}ComparableAdjustmentType") or "").strip() == adjust_type]
    if k >= len(found):
        return ""
    return (found[k].findtext(f"{{{bind.MISMO}}}ComparableAdjustmentAmount") or "").strip()


@dataclass
class Cell:
    text: str = ""
    adjustment: str = ""
    dash: bool = False             # empty, and B-1 says this cell prints an em-dash
    scope: str = ""                # the block the value was read in, when not the property


@dataclass
class BuiltRow:
    label: str
    heading: bool
    subject: str
    cells: list[Cell] = field(default_factory=list)
    subject_dash: bool = False
    adjustable: bool = False
    subject_fid: str = ""
    comp_fid: str = ""
    adjust_type: str = ""
    adjust_fid: str = ""
    # An additional comparison line item is a row the appraiser names: B-1
    # gives each group one "[Additional Row]" template and A-1 an Identifier
    # (what the row is called) beside a Description (what each property has).
    line_item: str = ""            # the container it is kept in
    item_name: str = ""            # the identifier, which is the row's label
    new_item: bool = False         # where the group's "+" adds another
    line_type: str = ""            # the ComparableAdjustmentType it is kept under
    subject_scope: str = ""        # the subject block read (a rental unit), when not the property
    # A row drawn once per unit, ADU, dwelling or outbuilding: which one
    # ("unit 1", "adu 1", ...), and which of the comparable's adjustments of
    # this type it shows -- they are positional, in the order the grid draws
    # the rows (D-1 2-4: unit 1 then unit 2; SF3: the dwelling then its ADU).
    group: str = ""
    instance: int = -1

    @property
    def empty(self) -> bool:
        return not self.subject and not any(c.text or c.adjustment
                                            for c in self.cells)


@dataclass
class Grid:
    kind: str
    title: str
    comparables: list[str]
    rows: list[BuiltRow] = field(default_factory=list)
    subject_label: str = "Subject Property"
    numbers: list[int] = field(default_factory=list)   # each column's comparable number

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "title": self.title,
                "comparables": self.comparables,
                "rows": [{"label": r.label, "heading": r.heading,
                          "subject": r.subject,
                          "cells": [c.__dict__ for c in r.cells]}
                         for r in self.rows]}


ADDITIONAL_ROW = "[Additional Row]"
# B-1 writes a row the appraiser names in brackets: "[Additional Row]" is one
# they invent outright, "[Other Exterior Feature]" one the standard list does
# not cover.  Both work the same way -- a name and, beside it, what each
# property has -- and both are expanded here into ordinary named rows.
NAMED_ROWS = ("AdditionalComparisonLineItemIdentifier",
              "ImprovementComponentTypeOtherDescription")

# Where the sales sheet keeps a row it cannot adjust.  A-1 enumerates exactly
# three additional-item types; which one applies follows from the grid.
ADDITIONAL_TYPE = {"sales": "SalesComparableAdditionalNonAdjustableComparisonItem",
                   "grm": "GrossRentMultiplierAdditionalNonAdjustableComparisonItem"}


@dataclass(frozen=True)
class Named:
    """How a row the appraiser names is stored."""
    container: str
    marks: tuple            # (element name, value) pairs that identify it
    name_dp: str            # the data point holding the name
    value_dp: str           # the data point holding what each property has
    value_fid: str
    subject_fid: str = ""   # the identifier the subject's cell writes
    comp_fid: str = ""      # the identifier a comparable's cell writes
    inner: tuple = ()       # the path from the repeat down to those values
    # kept inside an IMPROVEMENT (a dwelling, a living unit, an outbuilding),
    # so drawn with each one; otherwise it is the property's, and drawn once
    per_block: bool = False

    @property
    def kept_as(self) -> str:
        """The ComparableAdjustmentType the rows are kept under ("" if none)."""
        return dict(self.marks).get("ComparableAdjustmentType", "")


def _next_field_in(container: str, fid: str) -> tuple[str, str]:
    """A-1 numbers a named row's value straight after its name.

    "[Other Exterior Feature]" is 22.08.07, what the property has is 22.08.08;
    "[Additional Row]" is 22.05.18 and its description 22.05.19.  So the value
    is the next Report Field ID in the same container, which is read here
    rather than written out.
    """
    head, _, tail = fid.rpartition(".")
    try:
        nxt = f"{head}.{int(tail) + 1:0{len(tail)}d}"
    except ValueError:
        return "", ""
    binding = binding_of(nxt)
    for dp in (binding.data_points if binding else []):
        if bind.repeating_container(dp.get("xpath", "")) == container and dp.get("mismo"):
            return nxt, dp["mismo"]
    return "", ""


@lru_cache(maxsize=1)
def _roles() -> dict[str, tuple[str, ...]]:
    data = json.loads((SPEC / "field_index.json").read_text(encoding="utf-8"))["fields"]
    return {fid: tuple(entry.get("roles") or []) for fid, entry in data.items()}


def _value_field_for(role: str, value_fid: str, value_dp: str, container: str) -> str:
    """The Report Field ID this role writes the row's value with.

    A-1 gives the subject and each kind of comparable their own identifier for
    the same data point -- the subject's description of an added row is
    22.05.19, a sales comparable's is 22.05.53 -- and a cell that offered the
    subject's identifier to a comparable wrote the value into the subject.
    """
    if role in _roles().get(value_fid, ()):
        return value_fid
    head = value_fid.rsplit(".", 1)[0]
    mine = binding_of(value_fid)
    want_label = (mine.label if mine else "").strip()
    want_sub = (mine.subsection if mine else "").strip()
    fallback = ""
    for fid, roles in _roles().items():
        if role not in roles or not fid.startswith(head + "."):
            continue
        binding = binding_of(fid)
        if binding is None:
            continue
        if not any(dp.get("mismo") == value_dp and
                   bind.repeating_container(dp.get("xpath", "")) == container
                   for dp in binding.data_points):
            continue
        # several of a group's fields share one data point ("Windows" and
        # "Other (Describe)" are both a quality summary), so the label A-1
        # gives the row decides which of them this row writes
        if binding.label.strip() == want_label and binding.subsection.strip() == want_sub:
            return fid
        fallback = fallback or fid
    return fallback or value_fid


@lru_cache(maxsize=256)
def named_row(kind: str, fid: str, data_point: str, adjust_type: str) -> "Named | None":
    """What a bracketed row of the workbook means, or None if it is not one."""
    if data_point not in NAMED_ROWS:
        return None
    binding = binding_of(fid)
    if binding is None:
        return None
    dp = next((d for d in binding.data_points if d.get("mismo") == data_point), None)
    if dp is None:
        return None
    container = bind.repeating_container(dp.get("xpath", ""))
    if not container:
        return None
    marks = {k: v for k, v in (dp.get("requires") or {}).items()
             if not k.startswith(("@", "__"))}
    if container == "COMPARABLE_ADJUSTMENT":
        marks["ComparableAdjustmentType"] = adjust_type or ADDITIONAL_TYPE.get(kind, "")
    value_fid, value_dp = _next_field_in(container, fid)
    if not value_dp:
        return None
    segs = bind._tail(dp.get("xpath", ""))
    inner = tuple(segs[segs.index(container) + 1:]) if container in segs else ()
    comp_role = {"sales": "Sales Comparable", "rental": "Rental Comparable",
                 "grm": "Gross Rent Multiplier Comparable"}.get(kind, "")
    return Named(container, tuple(sorted(marks.items())), data_point, value_dp,
                 value_fid,
                 _value_field_for("Subject Property", value_fid, value_dp, container),
                 _value_field_for(comp_role, value_fid, value_dp, container),
                 inner, "IMPROVEMENT" in segs[:segs.index(container)] if container in segs else False)


def line_item_place(kind: str, row: "GridRow") -> tuple[str, str]:
    """(the container this grid keeps added rows in, the type that marks one)."""
    named = named_row(kind, row.subject_fid or row.comp_fid, row.data_point,
                      row.adjust_type)
    if named is None:
        return "", ""
    return named.container, named.kept_as


def _inside(node, name: str) -> str:
    """A value anywhere inside this instance.

    The block that repeats and the block the values sit in are not always the
    same element -- an interior component repeats at INTERIOR_COMPONENT and
    keeps its values in INTERIOR_COMPONENT_DETAIL -- so the search goes down,
    not just one level.
    """
    hit = node.find(f"{{{bind.MISMO}}}{name}")
    if hit is None:
        hit = node.find(f".//{{{bind.MISMO}}}{name}")
    return (hit.text or "").strip() if hit is not None else ""


def _is_item(node, named: "Named", name: str = "") -> bool:
    for key, want in named.marks:
        if _inside(node, key) != want:
            return False
    got = _inside(node, named.name_dp)
    return got == name if name else bool(got)


def named_values(root: etree._Element, named: "Named", props: list) -> list[str]:
    """Every name given to this group's rows, in document order."""
    names: list[str] = []
    for prop in props:
        for node in prop.iter(f"{{{bind.MISMO}}}{named.container}"):
            if not _is_item(node, named):
                continue
            name = _inside(node, named.name_dp)
            if name and name not in names:
                names.append(name)
    return names


def named_node(prop: etree._Element, named: "Named", name: str, *, create: bool = False):
    """The element this property keeps that named row in."""
    for node in prop.iter(f"{{{bind.MISMO}}}{named.container}"):
        if _is_item(node, named, name):
            return node
    if not create:
        return None
    holder = _container_parent(prop, named)
    if holder is None:
        return None
    # a list made just now came with the row its schema requires: that one
    # is this row, not a nameless second one beside it (T-509)
    node = edit.add_instance(holder, named.container)
    inner, _made = edit.ensure_path(node, list(named.inner))
    for key, want in named.marks:
        edit.insert_ordered(inner, key).text = want
    edit.insert_ordered(inner, named.name_dp).text = name
    return node


def named_nodes(prop: etree._Element, named: "Named", name: str) -> list:
    """Every element this property keeps that named row in: a rental row is
    kept once per subject unit the comparable is compared with."""
    return [node for node in prop.iter(f"{{{bind.MISMO}}}{named.container}")
            if _is_item(node, named, name)]


def drop_named(prop: etree._Element, node: etree._Element) -> None:
    """Take a named row out of one property, with the containers made to hold
    it (COMPARABLE, COMPARABLE_ADJUSTMENTS) once they hold nothing else."""
    edit.remove_block(node)              # schema-aware: edit.removal_plan (T-509)


def _container_parent(prop: etree._Element, named: "Named"):
    """The element a named row hangs from, made if the case has none yet.
    ``prop`` is the property, or a block inside it on the way down (the
    RENTAL_INFORMATION of a rental grid drawn per subject unit)."""
    binding = binding_of(named.value_fid)
    here = etree.QName(prop).localname
    for dp in (binding.data_points if binding else []):
        segs = bind._tail(dp.get("xpath", ""))
        if named.container not in segs or here not in segs[:segs.index(named.container)]:
            continue
        upto = segs[segs.index(here) + 1:segs.index(named.container)]
        holder, _ = edit.ensure_path(prop, upto)
        return holder
    return None


def named_value(prop: etree._Element, named: "Named", name: str) -> tuple[str, str]:
    """What this property says on that row, and its adjustment."""
    node = named_node(prop, named, name)
    if node is None:
        return "", ""
    text = _inside(node, named.value_dp)
    binding = binding_of(named.value_fid)
    if text and binding is not None:
        text = bind.display_value([[(named.value_dp, text)]], binding) or text
    amount = _inside(node, "ComparableAdjustmentAmount")
    if amount:
        amount = bind.format_value(amount, "Amount", "+9.0")
    return text, amount


def write_named(prop: etree._Element, named: "Named", name: str, value: str, *,
                adjustment: bool = False) -> "edit.Written":
    """Write what this property has on a row the appraiser named, or its
    adjustment, into that row's own element.

    Every row of a group shares one Report Field ID (22.07.44 is each added
    row's description) and one ComparableAdjustmentType, so neither says which
    row is meant -- the name does.  Written by field or by type, the second
    row's adjustment landed on the first.  The element is made for a property
    that has none yet.
    """
    point = "ComparableAdjustmentAmount" if adjustment else named.value_dp
    text = value.strip()
    node = named_node(prop, named, name, create=bool(text))
    if node is None:
        if text:
            raise ValueError(f"this property cannot keep the row {name!r}")
        return edit.Written("", point, "", "", "", [])
    holder = node if adjustment else edit.ensure_path(node, list(named.inner))[0]
    target = holder.find(f"{{{bind.MISMO}}}{point}")
    old = (target.text or "").strip() if target is not None else ""
    if not text:
        if target is not None:
            holder.remove(target)
    else:
        if target is None:
            target = edit.insert_ordered(holder, point)
        target.text = text
    return edit.Written("", point, "", old, text, [])


def specs(root: etree._Element, kind: str = "sales", *,
          every_row: bool = False) -> list[GridRow]:
    """The rows of a grid, with every added row expanded into its own.

    The workbook gives each group one "[Additional Row]" template; a case may
    have named several, and they are all kept under one adjustment type, so
    the template is expanded here -- once, at the last place the workbook
    offers it -- and every part of the program reads the same list.

    ``every_row`` (the editor) adds, after each group's rows, the place its
    "+" is drawn (``new_item``).  It is never a row of its own: an empty
    named row there read as one more row the appraiser had not asked for,
    and a new one appeared under every row they named (DR §7).
    """
    _sheet, role, _title = SHEETS[kind]
    props = properties(root, role)
    subject = bind.subject(root)
    spec = rows(kind)
    everywhere = ([subject] if subject is not None else []) + props
    # the Outbuilding group is drawn once per outbuilding, so with none it is
    # not drawn at all; the type's template before it (Vehicle Storage) is
    # then the last place it is offered, or its rows could neither be added
    # nor printed
    no_outbuildings = not any(_outbuildings(p) for p in everywhere)
    last: dict[tuple[str, str], int] = {}
    group = ""
    for row in spec:
        if row.heading:
            group = row.label.strip()
        elif row.label == ADDITIONAL_ROW and not (no_outbuildings and group.startswith("Outbuilding (")):
            last[line_item_place(kind, row)] = row.order
    out: list[GridRow] = []
    for row in spec:
        named = named_row(kind, row.subject_fid or row.comp_fid, row.data_point,
                          row.adjust_type)
        if named is None:
            out.append(row)
            continue
        if row.label == ADDITIONAL_ROW and row.order != last.get((named.container, named.kept_as)):
            # every additional row of a grid is kept under one type, so the
            # workbook's several templates for it expand in one place
            continue
        for name in named_values(root, named, everywhere):
            out.append(replace(row, label=name, item_name=name,
                               container=named.container, container_kind=kind,
                               subject_fid=named.subject_fid,
                               comp_fid=named.comp_fid, named=named))
        if every_row:
            out.append(replace(row, item_name="", container=named.container,
                               container_kind=kind, new_item=True,
                               subject_fid=named.subject_fid,
                               comp_fid=named.comp_fid, named=named))
    return out


X = "{http://www.w3.org/1999/xlink}"


def rental_pairs(root: etree._Element) -> list[tuple[etree._Element, list[tuple[etree._Element, etree._Element]]]]:
    """Each subject unit's rental comparables, as A-1 ties them: a
    comparable keeps one RENTAL_INFORMATION per subject unit it is compared
    with, linked by RENTAL_INFORMATION_IsComparableFor_RENTAL_INFORMATION to
    that unit's own.  D-1 2-4 compares Unit 1 with #1-#3 and Unit 2 with #1,
    #4, #5 -- with a different Adjusted Rent for #1 in each.  Returns
    [(subject RENTAL_INFORMATION, [(comparable PROPERTY, its RENTAL_INFORMATION)])]
    in the subject's unit order; empty when nothing is linked."""
    links = [(r.get(f"{X}from"), r.get(f"{X}to")) for r in root.iter(f"{{{bind.MISMO}}}RELATIONSHIP")
             if r.get(f"{X}arcrole", "").endswith("RENTAL_INFORMATION_IsComparableFor_RENTAL_INFORMATION")]
    if not links:
        return []
    by = {e.get(f"{X}label"): e for e in root.iter(f"{{{bind.MISMO}}}RENTAL_INFORMATION") if e.get(f"{X}label")}
    subject = bind.subject(root)
    if subject is None:
        return []
    out = []
    for ri in subject.iter(f"{{{bind.MISMO}}}RENTAL_INFORMATION"):
        label = ri.get(f"{X}label")
        comps = []
        for frm, to in links:
            if to != label or frm not in by:
                continue
            cri = by[frm]
            prop = next((a for a in cri.iterancestors(f"{{{bind.MISMO}}}PROPERTY")), None)
            if prop is not None:
                comps.append((prop, cri))
        if comps:
            order = {id(p): n for n, p in enumerate(properties(root, "RentalComparable"))}
            comps.sort(key=lambda pc: _number_of(pc[0]) or order.get(id(pc[0]), 99))
            out.append((ri, comps))
    return out


def _number_of(prop: etree._Element) -> int:
    n = ordinal_node(prop)
    text = (n.text or "").strip() if n is not None else ""
    return int(text) if text.isdigit() else 0


def _scopes(block: etree._Element) -> list[etree._Element]:
    """The pairing's RENTAL_INFORMATION, the unit holding it, the property:
    a comparison ("Similar", Adjusted Rent) is the pairing's, bedrooms the
    unit's, the site and neighborhood the property's."""
    out = [block]
    unit = next(block.iterancestors(f"{{{bind.MISMO}}}PROPERTY_UNIT"), None)
    if unit is not None:
        out.append(unit)
    prop = next(block.iterancestors(f"{{{bind.MISMO}}}PROPERTY"), None)
    if prop is not None:
        out.append(prop)
    return out


def _field_scope(fid: str, scopes: list) -> "etree._Element | None":
    """The block a field is read in: the innermost of the pairing, its unit
    and its property that the field's own path runs through.  A unit's
    answer is never looked for in the whole property -- that finds another
    unit's (D-1 2-4: Unit 2 is not rented, and prints em-dashes, not Unit 1's
    "No")."""
    binding = binding_of(fid)
    paths = [dp.get("xpath", "") for dp in (binding.data_points if binding else [])]
    for sc in scopes[:-1]:
        name = etree.QName(sc).localname
        if any(f"/{name}/" in f"/{p}" for p in paths):
            return sc
    return scopes[-1] if scopes else None


def _dp_scope(dp: dict, scopes: list):
    path = "/" + dp.get("xpath", "")
    for sc in scopes[:-1]:
        if f"/{etree.QName(sc).localname}/" in path:
            return sc
    return scopes[-1]


def _layered(root, fid: str, scopes: list, row) -> tuple[str, etree._Element | None]:
    binding = binding_of(fid)
    if binding is not None and len(scopes) > 1 and not (row is not None and row.container):
        levels: dict[int, tuple] = {}
        for dp in binding.data_points:
            sc = _dp_scope(dp, scopes)
            levels.setdefault(scopes.index(sc), (sc, []))[1].append(dp)
        if len(levels) > 1:
            # one field over two levels -- "Structure ID | Unit ID" is the
            # building's identifier and the unit's: each read where it is, the
            # outer first, as D-1 2-4 prints "Building 1 | Unit 1"
            parts = []
            for _n, (sc, dps) in sorted(levels.items(), key=lambda kv: -kv[0]):
                one = bind.Binding(binding.field_id, binding.section, binding.subsection, binding.label, dps)
                text = value_for(root, fid, sc, row, binding=one)
                if text:
                    parts.append(text)
            return " | ".join(parts), (scopes[0] if parts else None)
    sc = _field_scope(fid, scopes)
    if sc is None:
        return "", None
    text = value_for(root, fid, sc, row)
    return text, (sc if text else None)


def _layered_raw(root, fid: str, scopes: list) -> list[str]:
    sc = _field_scope(fid, scopes)
    return raw_for(root, fid, sc) if sc is not None else []


_OTHER_THAN = re.compile(r"other than ([A-Za-z ]+?)\)", re.I)


def _other_than(rules: str) -> set[str]:
    m = _OTHER_THAN.search(rules or "")
    if not m:
        return set()
    return {w.strip().casefold() for w in re.split(r"\band\b|,", m.group(1)) if w.strip()}


def _without(text: str, drop: set[str]) -> str:
    return " | ".join(p for p in (text or "").split(" | ") if p.strip().casefold() not in drop) if text else text


def _has_adu(root: etree._Element, props: list) -> bool:
    for prop in props:
        if prop is None:
            continue
        for n in prop.iter(f"{{{bind.MISMO}}}AccessoryDwellingUnitIndicator"):
            if (n.text or "").strip() == "true":
                return True
    return False


def _outbuildings(prop) -> list[etree._Element]:
    """A property's outbuildings in the order D-1 MH1 prints them -- by their
    name (Barn before Rec Room/Garage), the k-th of every property side by
    side: A-1 ties no outbuilding to another, and the sample pairs them by
    position (#1's Barn with the subject's Barn, its Workshop with the Rec
    Room/Garage)."""
    if prop is None:
        return []
    out = []
    for imp in prop.iter(f"{{{bind.MISMO}}}IMPROVEMENT"):
        if (imp.findtext(f".//{{{bind.MISMO}}}ImprovementType") or "").strip() != "Outbuilding":
            continue
        if any((u.findtext(f".//{{{bind.MISMO}}}AccessoryDwellingUnitIndicator") or "").strip() == "true"
               for u in imp.iter(f"{{{bind.MISMO}}}PROPERTY_UNIT")):
            continue        # "ADU ... not included" (the group's own heading; D-1 SF3)
        kind = (imp.findtext(f".//{{{bind.MISMO}}}OutbuildingType") or "").strip()
        other = (imp.findtext(f".//{{{bind.MISMO}}}OutbuildingTypeOtherDescription") or "").strip()
        out.append(((other if kind == "Other" and other else bind._humanise(kind)).casefold(), imp))
    return [imp for _name, imp in sorted(out, key=lambda t: t[0])]


def _units(prop, adu: bool) -> list[etree._Element]:
    """A property's living units (adu False) or ADUs (adu True), in document order."""
    if prop is None:
        return []
    out = []
    for u in prop.iter(f"{{{bind.MISMO}}}PROPERTY_UNIT"):
        flag = (u.findtext(f".//{{{bind.MISMO}}}AccessoryDwellingUnitIndicator") or "").strip() == "true"
        if flag == adu:
            out.append(u)
    return out


def _dwellings(prop) -> list[etree._Element]:
    if prop is None:
        return []
    return [imp for imp in prop.iter(f"{{{bind.MISMO}}}IMPROVEMENT")
            if (imp.findtext(f".//{{{bind.MISMO}}}ImprovementType") or "").strip() == "Dwelling"]


def _unit_scopes(unit, prop) -> list:
    imp = next(unit.iterancestors(f"{{{bind.MISMO}}}IMPROVEMENT"), None)
    return [x for x in (unit, imp, prop) if x is not None]


def _ob_scopes(prop, k) -> list:
    """The block a repeated group's row is read in, for one property.  ``k``
    is (kind, position): an outbuilding, a living unit, an ADU or a dwelling."""
    kind, n = k if isinstance(k, tuple) else ("ob", k)
    if kind == "ob":
        obs = _outbuildings(prop)
        return [obs[n]] if n < len(obs) else []
    if kind in ("unit", "adu"):
        units = _units(prop, kind == "adu")
        return _unit_scopes(units[n], prop) if n < len(units) else []
    if kind == "dwelling":
        ds = _dwellings(prop)
        return [ds[n], prop] if n < len(ds) else []
    return []


#: the grid groups B-1 repeats, what each repeats over, and the rows that
#: belong only to some of its copies
_REPEATS = (("Unit(s)", "unit"), ("Exterior Quality and Condition", "dwelling"),
            ("Interior Quality and Condition", "unit"), ("ADU Interior Quality and Condition", "adu"))


def _expand_outbuildings(spec: list, props: list) -> list:
    """The spec with each repeating group drawn once per position, as D-1
    prints them: 2-4 "Building 1 | Unit 1" then "Building 2 | Unit 2" in
    Unit(s) and Interior Quality and Condition, "Building 1" / "Building 2"
    in Exterior; SF3 its ADU's own Unit(s) lines under "Location of ADU";
    MH1 each outbuilding.  Rows read inside that unit, dwelling or
    outbuilding only."""
    out: list = []
    i = 0
    while i < len(spec):
        row = spec[i]
        if not row.heading:
            out.append((row, None))
            i += 1
            continue
        end = next((j for j in range(i + 1, len(spec)) if spec[j].heading), len(spec))
        group = spec[i + 1:end]
        label = row.label.strip()
        kind = next((k for name, k in _REPEATS if label == name), None)
        if label.startswith("Outbuilding ("):
            kind = "ob"
        out.append((row, None))
        # A row the appraiser named and keeps against the whole property (an
        # additional comparison item, A-1 COMPARABLE_ADJUSTMENT) is no unit's
        # or outbuilding's: drawn with each copy, one name showed under every
        # unit of a 2-4 report.  It is drawn once, after the group's copies.
        once = [r for r in group if r.named is not None and not r.named.per_block]
        if kind is not None:
            group = [r for r in group if not any(r is o for o in once)]
        if kind is None:
            out += [(r, None) for r in group]
        elif kind == "ob":
            n = max((len(_outbuildings(p)) for p in props), default=0)
            for k in range(n):
                out += [(r, ("ob", k)) for r in group]
            out += [(r, None) for r in once]
        elif kind == "unit":
            n = max((len(_units(p, False)) for p in props), default=0)
            body = [r for r in group if r.label.strip() != "Location of ADU"]
            for k in range(max(n, 1)):
                out += [(r, ("unit", k)) for r in body]
            out += [(r, None) for r in once]
            if label == "Unit(s)":
                # each ADU's own lines, under its location (D-1 SF3)
                m = max((len(_units(p, True)) for p in props), default=0)
                adu_body = [r for r in group if r.label.strip() != "Structure ID | Unit ID"]
                for k in range(m):
                    out += [(r, ("adu", k)) for r in adu_body]
        elif kind == "adu":
            m = max((len(_units(p, True)) for p in props), default=0)
            for k in range(m):
                out += [(r, ("adu", k)) for r in group]
            out += [(r, None) for r in once]
        else:
            n = max((len(_dwellings(p)) for p in props), default=0)
            for k in range(max(n, 1)):
                out += [(r, (kind, k)) for r in group]
            out += [(r, None) for r in once]
        i = end
    return out


def _nth_adjustment(root, row, prop, k) -> str:
    """The k-th adjustment of the row's type: one per outbuilding, unit or
    dwelling it repeats over."""
    k = k[1] if isinstance(k, tuple) else k
    if not row.adjust_type:
        return adjustment_for(root, row, prop)
    found = [n for n in prop.iter(f"{{{bind.MISMO}}}COMPARABLE_ADJUSTMENT")
             if (n.findtext(f"{{{bind.MISMO}}}ComparableAdjustmentType") or "").strip() == row.adjust_type]
    if k >= len(found):
        return ""
    amount = (found[k].findtext(f"{{{bind.MISMO}}}ComparableAdjustmentAmount") or "").strip()
    binding = binding_of(row.adjust_fid)
    if not amount:
        return ""
    return bind.display_value([[("ComparableAdjustmentAmount", amount)]], binding) if binding else amount


_ROW_WHEN = re.compile(r"Display (?:row )?when (.+?)(?:\.\s|\.$|$| Repeat| Subject| Display| When)")
_ROW_NAMES = re.compile(r"\b([A-Z][A-Za-z]+(?:Type|Indicator|Count|Code))\b")


def _rule_hides(row, root, subject) -> bool:
    """B-1's "Display when ..." for a grid row, where it decides alone: no
    "relevant to the analysis" (the appraiser's call) and every data point it
    names delivered in the document (AmenityCategoryType never is).  Checked
    against all twelve D-1 samples: it hides Structure ID | Unit ID with one
    unit (10/12), Dwelling Style / Structure Design by attachment, and the
    Exterior Quality and Condition rows where the homeowner does not maintain
    the exterior (Condo1, Coop1) -- each absent from the official PDF."""
    text = row.rules or ""
    if text.lstrip().startswith("Comps:") or "Subject:" in text or "\u2026" in text:
        return False           # a comparable's condition, or one split by side
    m = _ROW_WHEN.search(text)
    if not m or "elevant" in m.group(1).lower() or subject is None:
        return False           # "relevant to the analysis" (B-1 once spells it "elevant")
    names = _ROW_NAMES.findall(m.group(1))
    if not names or any(next(root.iter(f"{{{bind.MISMO}}}{n}"), None) is None for n in names):
        return False
    from . import rules as _rules
    d = _rules.evaluate("Display when " + m.group(1), root, subject)
    return d.known and not d.shown


def build(tree, kind: str = "sales", *, per_block: int = 3, every_row: bool = False) -> list[Grid]:
    """The grid for a case, in blocks of three comparables as the form prints.

    More than three comparables do not widen the page -- the samples repeat the
    grid, three at a time, which is why the measured geometry has exactly three
    comparable columns.  A rental grid whose comparables are tied to subject
    units (rental_pairs) is drawn once per unit, as D-1 2-4 does.
    """
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    _sheet, role, title = SHEETS[kind]
    comps = properties(root, role)
    if not comps:
        return []
    subject = bind.subject(root)
    spec = specs(root, kind, every_row=every_row)
    tree_ = root.getroottree()

    plans: list[tuple[str, list[etree._Element], list[tuple[etree._Element, list]]]] = []
    pairs = rental_pairs(root) if kind == "rental" else []
    if pairs:
        for k, (sri, comp_pairs) in enumerate(pairs, start=1):
            unit = next(sri.iterancestors(f"{{{bind.MISMO}}}PROPERTY_UNIT"), None)
            uid = (unit.findtext(f".//{{{bind.MISMO}}}UnitIdentifier") or "").strip() if unit is not None else ""
            uid = uid or f"Unit {k}"         # a unit not yet named is still told apart
            columns = [(p, _scopes(cri)) for p, cri in comp_pairs]
            for start in range(0, len(columns), per_block):
                plans.append((f"Subject {uid}".strip(), _scopes(sri), columns[start:start + per_block]))
    else:
        columns = [(p, [p]) for p in comps]
        for start in range(0, len(columns), per_block):
            plans.append(("Subject Property", [subject] if subject is not None else [], columns[start:start + per_block]))

    grids: list[Grid] = []
    for subject_label, subject_scopes, block in plans:
        position: dict[str, int] = {}     # adjustments of a type, in drawing order
        numbers = [_number_of(p) or comps.index(p) + 1 for p, _sc in block]
        grid = Grid(kind=kind, title=title, comparables=[f"Comparable #{n}" for n in numbers],
                    subject_label=subject_label, numbers=numbers)
        all_cols_base = [c for _l, _s, b in plans for c in b]
        ruled_labels: set[str] = set()
        for row, ob in _expand_outbuildings(spec, [subject] + comps):
            if row.heading:
                grid.rows.append(BuiltRow(row.label, True, "", []))
                continue
            if ob is None:
                row_subject_scopes, row_block, all_cols = subject_scopes, block, all_cols_base
            else:
                # the ob-th outbuilding of each property, read inside it only:
                # the dwelling's cooling is not an outbuilding's (T-123)
                row_subject_scopes = _ob_scopes(subject, ob)
                row_block = [(p, _ob_scopes(p, ob)) for p, _sc in block]
                all_cols = [(p, _ob_scopes(p, ob)) for p, _sc in all_cols_base]
            subject_text, sscope = (_layered(root, row.subject_fid, row_subject_scopes, row)
                                    if row.subject_fid and row_subject_scopes else ("", None))
            instance = -1
            if ob is not None and row.adjust_type:
                instance = position.get(row.adjust_type, 0)
                position[row.adjust_type] = instance + 1
            cells = []
            for prop, scopes in row_block:
                text, used = _layered(root, row.comp_fid, scopes, row) if (row.comp_fid and scopes) else ("", None)
                adj = adjustment_for(root, row, prop) if ob is None else _nth_adjustment(
                    root, row, prop, instance if instance >= 0 else ob)
                cells.append(Cell(text=text, adjustment=adj,
                                  scope=tree_.getpath(scopes[0]) if (pairs and scopes) else ""))
            built = BuiltRow(row.label, False, subject_text, cells,
                             adjustable=bool(row.adjustable),
                             subject_fid=row.subject_fid, comp_fid=row.comp_fid,
                             adjust_type=row.adjust_type, adjust_fid=row.adjust_fid,
                             line_item=row.container, item_name=row.item_name,
                             new_item=row.new_item,
                             line_type=row.named.kept_as if row.named is not None else "",
                             subject_scope=tree_.getpath(subject_scopes[0]) if (pairs and subject_scopes) else "",
                             group=f"{ob[0]} {ob[1] + 1}" if isinstance(ob, tuple) else "",
                             instance=instance)
            # an empty cell prints an em-dash only where B-1's sentence for the
            # row says so (dashes.py); every other empty cell stays blank
            empty = [not subject_text] + [not c.text for c in cells]
            if not subject_text:
                built.subject_dash = dashes.decide(
                    row.dash_subject, dashes.Cell(root, subject, True, empty, 0))
            for n, ((prop, _sc), cell) in enumerate(zip(block, cells), start=1):
                if not cell.text:
                    cell.dash = dashes.decide(
                        row.dash_comp, dashes.Cell(root, prop, False, empty, n))
            # The supplement marks each row always / if applicable / if
            # relevant.  "None" is an answer, not a fact about the property,
            # so a row every property answers "None" is not printed -- which is
            # how the samples drop Hazard Zone, Functional Issues and the rest.
            subject_raw = (_layered_raw(root, row.subject_fid, row_subject_scopes)
                           if row.subject_fid and row_subject_scopes else [])
            # whether a row prints is judged across every comparable, not only
            # the block of three it is drawn in: D-1 MH2's fourth comparable is
            # pending, and its contract price puts the Contract Price row (with
            # dashes for the other three) in the first block too
            comp_raw: list[str] = []
            if row.comp_fid:
                for _prop, scopes in all_cols:
                    if scopes:
                        comp_raw += _layered_raw(root, row.comp_fid, scopes)
            if ob is not None and not every_row and not subject_text and not any(
                    c.text or c.adjustment for c in cells):
                continue                  # nothing in this outbuilding position
            adjusted = any(c.adjustment for c in cells) or any(
                adjustment_for(root, row, prop) for prop in comps)
            # (in the editor every row stays, so it can be answered)
            if row.new_item:
                # where the group's "+" is drawn: it holds nothing (a row with
                # no name reads as the group's first, and showed its values)
                built.subject, built.subject_dash = "", False
                built.cells = [Cell() for _ in cells]
                grid.rows.append(built)
                continue
            if row.container:
                # A row the appraiser named is judged by what it actually
                # holds, not by reading its field anywhere in the property:
                # the same data point serves every row of the group, so the
                # general rule saw "Standard Grade" on some other component
                # and printed an empty row for a feature nobody described.
                if not every_row and built.empty:
                    continue
                grid.rows.append(built)
                continue
            exists = row.if_relevant and _EXISTS.search(row.rules or "") and bool(comp_raw)
            shown_row = ((row.always and not row.named) or adjusted or exists
                         or any(map(_told, comp_raw))
                         or ((row.if_applicable or row.named) and any(map(_told, subject_raw))))
            all_zero = (row.if_applicable and not row.always and not adjusted
                        and bool(comp_raw + subject_raw)
                        and all(v.strip() == "0" for v in comp_raw + subject_raw))
            ruled_out = _rule_hides(row, root, subject) or row.label.strip() in ruled_labels
            if ruled_out and row.label.strip() == "Structure ID | Unit ID":
                # B-1 states the condition on the Unit(s) row (22.07.01); the
                # Interior Quality and Condition row (22.09.02) repeats it
                ruled_labels.add(row.label.strip())
            if not every_row and (not shown_row or all_zero or ruled_out):
                # a named row prints for the name it carries, not because its
                # template always prints: a Wet Bar with no value in any column
                # is not a comparison line (D-1 SF3 p19-20).  A count every
                # property answers 0 is not applicable either (D-1 2-4 GRM:
                # no "Accessory Dwelling Units 0 0 0 0")
                continue
            grid.rows.append(built)
        # B-1 (Site Characteristics): "other than Drainage and Topography" --
        # those have rows of their own (D-1 SF1 prints "Topography  Rolling"
        # and no "Site Characteristics  Topography")
        others = {row_.label.strip(): _other_than(row_.rules) for row_ in spec if _other_than(row_.rules)}
        kept_rows = []
        for r in grid.rows:
            drop = others.get(r.label.strip())
            if drop and not r.heading:
                r.subject = _without(r.subject, drop)
                for c in r.cells:
                    c.text = _without(c.text, drop)
                if not every_row and not r.subject and not any(c.text or c.adjustment for c in r.cells):
                    continue
            kept_rows.append(r)
        grid.rows = kept_rows
        if not every_row and not _has_adu(root, [subject] + comps):
            # B-1: "Repeat Interior Quality and Condition for all PROPERTY_UNITS
            # where AccessoryDwellingUnitIndicator = true" -- with none, the
            # ADU group does not print (it repeated the dwelling's, D-1 SF1)
            out_rows, skipping = [], False
            for r in grid.rows:
                if r.heading:
                    skipping = r.label.strip().startswith("ADU Interior")
                    if skipping:
                        continue
                if not skipping and r.label.strip() != "Location of ADU":
                    out_rows.append(r)
            grid.rows = out_rows
        # A heading with nothing under it is not printed.
        pruned: list[BuiltRow] = []
        for i, r in enumerate(grid.rows):
            if r.heading and (i + 1 >= len(grid.rows) or grid.rows[i + 1].heading):
                continue
            pruned.append(r)
        grid.rows = pruned
        grids.append(grid)
    return grids


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------
# Measured off the D-1 grid pages: the label column, the subject column, and
# each comparable as a description cell plus its adjustment cell.  Appendix E
# calls these cell Types 2-5 (p61-62).
GRID_GEOM = {"label": 106.0, "subject": 108.5, "desc": 66.0, "adj": 42.5}

# Appendix E p61-62: rows that never apply, so the sample greys the cell out.
SUBJECT_GREY = {
    "Data Source", "Proximity to Subject", "Sale Price", "Transfer Terms",
    "Financing Type", "Sale Date", "Sale to List Price Ratio",
    "Same Builder as Subject", "Net Adjustment Total", "Adjusted Price Per Unit",
    "Adjusted Price Per Bedroom", "Price Per Gross Building Finished Area",
    "Price Per Finished Area Above Grade", "Adjusted Price", "Comparable Weight",
}
COMP_GREY = {"Days on Market", "Annual Ground Rent", "Rights Not Included",
             "Same Builder as Subject"}


def html(grid: Grid, photos: dict[int, str] | None = None,
         first: bool = True, *, edit: bool = False, start: int = 1) -> str:
    """One grid block, at the geometry the samples measure.

    Appendix E p62 and the D-1 samples with more than three comparables (SF2,
    Condo1, Condo2, MH2, SF5): each block of up to three comparables repeats
    the label and Subject Property columns, is only as wide as its columns,
    and carries its own photos in the Property Address row.  On a page the
    block continues onto, the column heads and the Property Address row repeat
    without photos -- that row is ``tr.tca`` in the head, shown only on a
    continued slice (``table.grid.cont``).

    ``edit`` marks each value cell with what writes it back (``data-gc`` the
    column, 0 = subject; ``data-gf`` the field; ``data-ga`` the adjustment).
    """
    photos = photos or {}
    n = len(grid.comparables)
    # These bracketed labels are B-1's own row templates -- "[Additional Row]",
    # "[Other Exterior Feature]" -- and every one of them carries a real,
    # writable Report Field ID (22.08.07, 22.13.02, ...).  Hiding them
    # unconditionally meant an appraiser could never describe an exterior
    # feature the standard categories do not cover, or add the extra
    # amenity/utility/GRM row A-1 provides for exactly that: skipping them was
    # right for the printed report, which drops an empty optional row anyway,
    # but wrong for the editor, which must not hide a line nobody can fill in.
    # "Comparable #" (PropertyOrdinalNumber) stays hidden even in edit mode: the
    # column head already shows it, and it is set by the dedicated reorder
    # route (comparables.reorder), which renumbers every comparable together --
    # a free-text cell here could desynchronise the numbering it depends on.
    skip = {"Comparable #"} if edit else {
        "Comparable #", "[Additional Row]",
        "[Other Exterior Feature]", "[Other Interior Feature]"}
    g = GRID_GEOM
    width = g["label"] + g["subject"] + n * (g["desc"] + g["adj"])
    cols = [f"<col style='width:{g['label']:.2f}pt'>",
            f"<col style='width:{g['subject']:.2f}pt'>"]
    for _ in range(n):
        cols.append(f"<col style='width:{g['desc']:.2f}pt'>")
        cols.append(f"<col style='width:{g['adj']:.2f}pt'>")

    head = [f"<tr class='tch'><th></th><th><span>{_esc(grid.subject_label)}</span></th>"]

    def number_of(i: int) -> int:
        # a rental grid drawn per subject unit compares #1, #4, #5 (D-1 2-4)
        return grid.numbers[i - 1] if len(grid.numbers) >= i else start + i - 1
    for i, name in enumerate(grid.comparables, start=1):
        attrs = f" data-compmenu='{number_of(i)}'" if edit else ""
        head.append(f"<th colspan='2'{attrs}><span>{_esc(name)}</span></th>")
    head.append("</tr>")

    def gattr(col: int, fid: str = "", adjust: str = "", scope: str = "", instance: int = -1) -> str:
        if not edit or not (fid or adjust):
            return ""
        from . import form as _form
        # the input the cell takes, drawn as the editor draws it elsewhere
        k = "amount" if adjust else _form.input_kind(fid)
        # one typed value -- an adjustment, a price, an area, a count -- is
        # typed where it prints; a cell of several parts or a list opens its
        # editor (owner 2026-10-08: "no dropdown for a field we know")
        point = "adjustment" if adjust else typed_in_place(fid)
        inline = f" data-gin='{_esc(point)}'" if point else ""
        return (f" data-gc='{col}' data-k='{k}'{inline}" + (f" data-gf='{_esc(fid)}'" if fid else "")
                + (f" data-ga='{_esc(adjust)}'" if adjust else "")
                + (f" data-gai='{instance}'" if adjust and instance >= 0 else "")
                + (f" data-gs='{_esc(scope)}'" if scope else ""))

    body = []
    repeat = ""
    for row in grid.rows:
        if row.heading:
            kind = "sca-h2" if row.label.strip().startswith(("Exterior Quality",
                                                             "Interior Quality",
                                                             "ADU Interior",
                                                             "Indicated Value")) else "sca-sub"
            body.append(f"<tr class='{kind}'><td colspan='{2 + 2 * n}'>"
                        f"<span>{_esc(row.label)}</span></td></tr>")
            continue
        if row.label.strip() in skip:
            continue
        address = row.label.strip() == "Property Address"
        if edit and row.line_item:
            # a row the appraiser adds and names: the name is the row's label.
            # The "+" at the foot of the group adds one; nothing is added by
            # itself (DR §7)
            if row.new_item:
                body.append(_line_add(kind_of(grid), row, 2 + 2 * n))
                continue
            cells = [_line_name(kind_of(grid), row)]
        else:
            cells = [f"<td class='lbl'><span>{_esc(row.label)}</span></td>"]
        subject_grey = row.label.strip() in SUBJECT_GREY
        align = " left" if address else ""
        sub_text = row.subject or (EM_DASH if row.subject_dash else "")
        sub = (_photo_cell(photos.get(0), row.subject, 0, edit) if (address and first)
               else _esc(sub_text))
        cells.append(f"<td class='v sub{align}{' grey' if subject_grey else ''}'"
                     f"{gattr(0, row.subject_fid, scope=row.subject_scope)}><span>{sub}</span></td>")
        plain = [cells[0], f"<td class='v sub left'><span>{_esc(sub_text)}</span></td>"]
        for i, cell in enumerate(row.cells, start=1):
            number = number_of(i)
            shown = cell.text or (EM_DASH if cell.dash else "")
            text = (_photo_cell(photos.get(number), cell.text, number, edit) if (address and first)
                    else _esc(shown))
            grey = " grey" if row.label.strip() in COMP_GREY else ""
            if not row.adjustable:
                # nothing can be adjusted on this row, so the value has the
                # width of the whole comparable column (Appendix E, Type 2)
                cells.append(f"<td class='v comp{align}{grey}' colspan='2'"
                             f"{gattr(number, row.comp_fid, scope=cell.scope)}><span>{text}</span></td>")
                plain.append(f"<td class='v comp left' colspan='2'><span>{_esc(shown)}</span></td>")
                continue
            cells.append(f"<td class='v comp{align}{grey}'{gattr(number, row.comp_fid, scope=cell.scope)}>"
                         f"<span>{text}</span></td>")
            adj = _esc(cell.adjustment)
            gaf = f" data-gaf='{_esc(row.adjust_fid)}'" if (edit and row.adjust_fid) else ""
            cells.append(f"<td class='v adj{'' if adj else ' grey'}'"
                         f"{gattr(number, adjust=row.adjust_type, instance=row.instance)}{gaf}><span>{adj}</span></td>")
        if address and not repeat:
            repeat = "<tr class='tca'>" + "".join(plain) + "</tr>"
        body.append("<tr>" + "".join(cells) + "</tr>")

    kind_attr = f" data-gk='{_esc(grid.kind)}'" if edit else ""
    return (f"<table class='grid'{kind_attr} style='width:{width:.2f}pt'><colgroup>" + "".join(cols) + "</colgroup>"
            "<thead>" + "".join(head) + repeat + "</thead>"
            "<tbody>" + "".join(body) + "</tbody></table>")


def html_pair(grids: list["Grid"], *, edit: bool = False) -> str:
    """Two subject units' rental analyses side by side (C-1 p33: "Subject
    [Unit Identifier] | # # #" twice to a line; D-1 2-4 "Subject Unit 1 #1 #2
    #3 | Subject Unit 2 #1 #4 #5").  One label column; a row prints when
    either unit's grid prints it."""
    labels: list[tuple[str, bool]] = []
    for g in grids:
        for r in g.rows:
            key = (r.label, r.heading)
            if key not in labels:
                labels.append(key)
    by = [{(r.label, r.heading): r for r in g.rows} for g in grids]
    width, label_w = 540.0, 100.0
    per = (width - label_w) / (4 * len(grids))
    cols = f"<col style='width:{label_w:.2f}pt'>" + "".join(
        f"<col style='width:{per:.2f}pt'>" for _ in range(4 * len(grids)))

    def attrs(col: int, fid: str, scope: str) -> str:
        if not edit or not fid:
            return ""
        return f" data-gc='{col}' data-gf='{_esc(fid)}'" + (f" data-gs='{_esc(scope)}'" if scope else "")

    top = ["<tr class='tch'><th></th>"]
    sub = ["<tr class='tch2'><th></th>"]
    for g in grids:
        top.append("<th><span>Subject</span></th><th colspan='3'><span>Comparables</span></th>")
        sub.append(f"<th><span>{_esc(g.subject_label.replace('Subject ', ''))}</span></th>"
                   + "".join(f"<th><span>#{n}</span></th>" for n in g.numbers))
        sub.append("".join("<th></th>" for _ in range(3 - len(g.numbers))))
    head = "".join(top) + "</tr>" + "".join(sub) + "</tr>"
    body = []
    n_cols = 1 + 4 * len(grids)
    for label, heading in labels:
        if heading:
            body.append(f"<tr class='sca-sub'><td colspan='{n_cols}'><span>{_esc(label)}</span></td></tr>")
            continue
        lead = next((rows[(label, False)] for rows in by if (label, False) in rows), None)
        if edit and lead is not None and lead.line_item:
            # a row the appraiser adds and names, as in a grid of its own
            if lead.new_item:
                body.append(_line_add(kind_of(grids[0]), lead, n_cols))
                continue
            cells = [_line_name(kind_of(grids[0]), lead)]
        else:
            cells = [f"<td class='lbl'><span>{_esc(label)}</span></td>"]
        for g, rows in zip(grids, by):
            r = rows.get((label, False))
            if r is None:
                cells.append("<td></td>" * 4)
                continue
            sub_text = r.subject or (EM_DASH if r.subject_dash else "")
            cells.append(f"<td class='v sub'{attrs(0, r.subject_fid, r.subject_scope)}><span>{_esc(sub_text)}</span></td>")
            for i, c in enumerate(r.cells):
                shown = c.text or (EM_DASH if c.dash else "")
                number = g.numbers[i] if i < len(g.numbers) else i + 1
                cells.append(f"<td class='v comp'{attrs(number, r.comp_fid, c.scope)}><span>{_esc(shown)}</span></td>")
            cells.append("<td></td>" * (3 - len(r.cells)))
        body.append("<tr>" + "".join(cells) + "</tr>")
    kind_attr = " data-gk='rental'" if edit else ""
    return (f"<table class='grid rentpair'{kind_attr} style='width:{width:.2f}pt'><colgroup>{cols}</colgroup>"
            f"<thead>{head}</thead><tbody>{''.join(body)}</tbody></table>")


def kind_of(grid: "Grid") -> str:
    return grid.kind


def _photo_cell(src: str | None, text: str, number: int = 0, edit: bool = False) -> str:
    """A property's photo under its address, in the Property Address row.

    The empty box says whose photo belongs there, as the D-1 samples do
    ("This is where the Comparable 4 photo would display.").  In the editor
    the box itself takes the photograph; 0 is the subject, whose thumbnail is
    its front photo.
    """
    whose = "Subject Property" if number == 0 else f"Comparable {number}"
    picture = (f"<img class='cp' src='{src}'>" if src else
               f"<span class='cp empty'><i>This is where the {whose} photo would display.</i></span>")
    if edit:
        attrs = (" data-section='8' data-category='subject' data-name='Dwelling Exterior'"
                 " data-caption='Front of the dwelling'" if number == 0 else
                 f" data-section='22' data-category='comparable' data-comparable='{number}'"
                 f" data-name='Sales Comparison Approach' data-caption='Comparable #{number}'")
        picture = (f"<span class='cpwrap'>{picture}<span class='photodrop exdrop'{attrs}>"
                   f"</span></span>")
    return f"<span class='ca'>{_esc(text)}</span>{picture}"      # an address never prints a dash


def _esc(text: str) -> str:
    """A cell's text as HTML, keeping the line breaks it carries: the street on
    one line and the town on the next, a line for each vehicle storage."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("\n", "<br>"))


def _attr(text: str) -> str:
    """Text inside a single-quoted attribute: a name may be "Owner's Suite"."""
    return _esc(text).replace("'", "&#39;")


def _line_attrs(kind: str, row: "BuiltRow") -> str:
    """Where a group's added rows are kept: the grid, the container, the type."""
    return (f" data-li='{_esc(kind)}' data-lic='{_esc(row.line_item)}'"
            f" data-lit='{_esc(row.line_type)}'")


def _line_name(kind: str, row: "BuiltRow") -> str:
    """The label cell of a row the appraiser added, in the editor: its name in
    a text box, and the x that removes it (shown on hover)."""
    return (f"<td class='lbl liname'><input class='liin' type='text'{_line_attrs(kind, row)}"
            f" data-liwas='{_attr(row.item_name)}' value='{_attr(row.item_name)}'"
            f" placeholder='Name this row' aria-label='Row name' spellcheck='false'>"
            f"<span class='lidrop' role='button' tabindex='0' title='Remove this row'>&#215;</span></td>")


def _line_add(kind: str, row: "BuiltRow", span: int) -> str:
    """The "+" that adds one more row to a group, under its rows.  B-1's own
    label for the template ("[Other Exterior Feature]") says what it adds."""
    return (f"<tr class='liadd'><td colspan='{span}'><span class='liaddbtn' role='button'"
            f" tabindex='0'{_line_attrs(kind, row)}"
            f" title='Add a row you name; it is kept for the subject and every comparable'>"
            f"+ {_esc(row.label.strip().strip('[]'))}</span></td></tr>")


def main() -> None:
    import sys

    from .. import templates

    key = sys.argv[1] if len(sys.argv) > 1 else "sf1_appraisal_v1_4"
    tpl = templates.get(key)
    tree = etree.parse(str(tpl.path))
    for kind in SHEETS:
        spec = rows(kind)
        grids = build(tree, kind)
        heading = sum(1 for r in spec if r.heading)
        print(f"{kind:<8} {len(spec):>4} rows in the workbook "
              f"({heading} headings, {sum(1 for r in spec if r.always)} always, "
              f"{sum(1 for r in spec if r.adjustable)} adjustable)")
        for i, grid in enumerate(grids, start=1):
            drawn = [r for r in grid.rows if not r.heading]
            print(f"         block {i}: {len(grid.comparables)} comparables, "
                  f"{len(grid.rows)} rows drawn ({len(drawn)} with values)")
            for r in grid.rows[:5]:
                mark = "  --" if r.heading else ""
                print(f"            {r.label[:34]:<36}{mark} "
                      f"subj={r.subject[:16]!r} "
                      f"c1={(r.cells[0].text[:16] if r.cells else '')!r}")


if __name__ == "__main__":
    main()


def remove_property(tree, role: str, number: int) -> int:
    """Delete one comparable and close the numbering up behind it."""
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    found = properties(root, role)
    if not 1 <= number <= len(found):
        raise IndexError(f"no comparable #{number}")
    node = found[number - 1]
    label = node.get(f"{{{XLINK}}}label") if hasattr(node, "get") else None
    parent = node.getparent()
    if parent is not None:
        parent.remove(node)
    if label:
        _drop_relationships(root, label)
    renumber(tree, role, [p for p in found if p is not node])
    return len(found) - 1


def renumber(tree, role: str, order: list[etree._Element] | None = None) -> list[int]:
    """Write PropertyOrdinalNumber 1..n in the order given (or as found)."""
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    items = order if order is not None else properties(root, role)
    out = []
    for n, prop in enumerate(items, start=1):
        ordinal_node(prop, create=True).text = str(n)
        out.append(n)
    return out


def reorder(tree, role: str, order: list[int]) -> dict[int, int]:
    """Put the comparables in this order, given as their current numbers.

    The number is what the whole report refers to a comparable by -- the grid,
    the transfer history, the map, and the photograph -- so moving one
    renumbers every other.  The mapping of old number to new is returned
    because everything else keyed by the number has to move with it.
    """
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    found = properties(root, role)
    picked = [found[i - 1] for i in order if 1 <= i <= len(found)]
    rest = [p for p in found if not any(p is q for q in picked)]
    final = picked + rest

    # Identity, not equality: an lxml proxy is recreated per access, so the
    # element cannot be used as a dictionary key or compared with ==.
    def was(prop: etree._Element) -> int:
        return next(i for i, q in enumerate(found, start=1) if q is prop)

    mapping = {was(prop): new for new, prop in enumerate(final, start=1)}
    renumber(tree, role, final)
    return mapping


def copy_property(tree, role: str, number: int) -> int:
    """Add a copy of comparable #number as the last one of its kind.

    Everything the comparable holds is copied: its own elements and every
    relationship that points into it -- its data sources, and for a rental or
    a 2-4 unit sale the subject unit it is compared with.  Each identifier
    inside the copy is minted afresh (an ``xlink:label`` names one element in
    the whole document), and the copied relationships point at the new ones.
    Photographs are not copied: they are of the original property.
    """
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    found = properties(root, role)
    if not 1 <= number <= len(found):
        raise IndexError(f"no comparable #{number}")
    src = found[number - 1]
    dup = deepcopy(src)
    taken = {e.get(f"{{{XLINK}}}label") for e in root.iter() if isinstance(e.tag, str)}
    renamed: dict[str, str] = {}
    for node in dup.iter():
        old = node.get(f"{{{XLINK}}}label") if isinstance(node.tag, str) else None
        if not old:
            continue
        n = 2
        while f"{old}_COPY{n}" in taken:
            n += 1
        new = f"{old}_COPY{n}"
        taken.add(new)
        renamed[old] = new
        node.set(f"{{{XLINK}}}label", new)
    last = found[-1]
    last.addnext(dup)
    ordinal_node(dup, create=True).text = str(len(found) + 1)
    for rel in list(root.iter(f"{{{bind.MISMO}}}RELATIONSHIP")):
        a, b = rel.get(f"{{{XLINK}}}from"), rel.get(f"{{{XLINK}}}to")
        if a in renamed or b in renamed:
            twin = deepcopy(rel)
            twin.set(f"{{{XLINK}}}from", renamed.get(a, a))
            twin.set(f"{{{XLINK}}}to", renamed.get(b, b))
            rel.addnext(twin)
    return len(found) + 1


def _drop_relationships(root: etree._Element, label: str) -> None:
    for rel in list(root.iter(f"{{{bind.MISMO}}}RELATIONSHIP")):
        if label in (rel.get(f"{{{XLINK}}}from"), rel.get(f"{{{XLINK}}}to")):
            if rel.getparent() is not None:
                edit.remove_block(rel)   # MISMO: RELATIONSHIPS holds at least one


def points_for(field_id: str) -> list[dict]:
    """The data points a grid cell is actually made of.

    An address is six of them, and a cell that writes one string into the
    first would silently drop the city and the state, so the editor is given
    the parts and composes the cell the way the report does.
    """
    binding = binding_of(field_id)
    if binding is None:
        return []
    # A value with a unit -- "1,850" with @AreaUnitOfMeasureType -- is still
    # typed: its enumeration lists the unit, which the write fills in
    # (entry.normalize: square feet unless the appraiser types another).  It
    # was dropped as an attribute, leaving the cell nothing but a one-item
    # "Sq. Ft." list and no way to enter the area (owner 2026-10-08).
    from .. import entry
    unique = {d["mismo"]: d for d in binding.data_points
              if d.get("mismo") and (not d.get("attribute") or entry.unit_attribute(d))}
    return [{"data_point": d["mismo"],
             "format": d.get("format_type", ""),
             "definition": d.get("definition", ""),
             "options": [] if entry.unit_attribute(d) else
                        [{"value": o["value"], "label": o.get("display") or o["value"]}
                         for o in d.get("enumerations", []) if o.get("value")]}
            for d in unique.values()]


def parts_for(root: etree._Element, field_id: str,
              scope: etree._Element | None) -> dict[str, str]:
    """Each data point's own value within one property."""
    binding = binding_of(field_id)
    if binding is None or scope is None:
        return {}
    out: dict[str, str] = {}
    for name, node in bind._walk(root, binding, scope, 1):
        text = (node.text or "").strip()
        if text and name not in out:
            out[name] = text
    return out


@lru_cache(maxsize=None)
def stacks(field_id: str) -> bool:
    """Does this cell print one line for each instance of its block (a
    ``Composite`` with ``stack``)?"""
    binding = binding_of(field_id)
    composite = bind.composite_for([dp.get("mismo", "") for dp in binding.data_points]) if binding else None
    return bool(composite and composite.stack)


def lines_for(root: etree._Element, field_id: str,
              scope: etree._Element | None) -> list[dict] | None:
    """A stacked cell's lines -- B-1 "a separate line for each" vehicle storage,
    view, street, heating system -- each with its own values and the path
    (``line``) a write into that line names.  None where the cell is one
    value.  Edited through ``parts_for`` alone, every line but the first was
    out of reach and a garage typed there replaced the driveway."""
    binding = binding_of(field_id)
    if binding is None or scope is None or not stacks(field_id):
        return None
    tree = root.getroottree()
    lines: dict[str, tuple] = {}
    for name, node in _read(root, binding, scope):
        text = (node.text or "").strip()
        if not text:
            continue
        key = bind.instance_of(node)
        if key not in lines:
            hit = tree.xpath(key)
            if not hit:
                continue
            lines[key] = (hit[0], {"line": bind.stable_path(hit[0]), "parts": {}})
        lines[key][1]["parts"].setdefault(name, text)
    # each line asks for what A-1 asks of its own block (a garage's area, not
    # a driveway's surface) -- the same conditions the section's row follows
    # and an "Other" description goes with its list
    from . import form as _form
    names = {dp.get("mismo") for dp in binding.data_points}
    for el, ln in lines.values():
        ok = [dp["mismo"] for dp in binding.data_points if dp.get("mismo")
              and not dp["mismo"].endswith("OtherDescription") and _form._instance_ok(dp, el)]
        ln["points"] = list(dict.fromkeys(ok + [f"{n}OtherDescription" for n in ok
                                                if f"{n}OtherDescription" in names]))
    # in the order they print (an "Other" description is read ahead of its line)
    rank = {el: n for n, el in enumerate(scope.iter())}
    return [ln for el, ln in sorted(lines.values(), key=lambda p: rank.get(p[0], 0))]


@lru_cache(maxsize=None)
def typed_in_place(field_id: str) -> str:
    """The data point a grid cell is typed into where it prints, or ''.

    One data point, no list to choose from and not a Yes/No: an amount, a
    number, a date, words.  Everything else keeps the cell editor."""
    pts = points_for(field_id)
    if len(pts) != 1 or pts[0]["options"] or pts[0]["format"].casefold() == "boolean":
        return ""
    return pts[0]["data_point"]


def options_for(field_id: str) -> list[dict]:
    """The enumerated values a grid cell accepts, for the editor's dropdown."""
    binding = binding_of(field_id)
    if binding is None:
        return []
    from .. import entry
    points = [d for d in binding.data_points if d.get("mismo")]
    if points and all(entry.unit_attribute(d) for d in points):
        return []                       # the units of a typed measure, not choices
    return [{"value": o["value"], "label": o.get("display") or o["value"]}
            for o in binding.enumerations if o.get("value")]


def adjustment_type_of(field_id: str, kind: str = "sales") -> str:
    """The ComparableAdjustmentType an adjustment cell's Report Field ID writes,
    read from the B-1 grid ('' when the grid does not name exactly one).

    Written without it, an adjustment fell through to the generic writer and
    was filed under whichever COMPARABLE_ADJUSTMENT came first
    (owner's section test B13)."""
    if kind not in SHEETS or not SHEETS[kind][0]:
        return ""
    types = {r.adjust_type for r in rows(kind) if r.adjust_fid == field_id and r.adjust_type}
    return next(iter(types)) if len(types) == 1 else ""
