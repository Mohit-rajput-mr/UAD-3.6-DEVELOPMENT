"""How many dwellings a property is made of, and keeping the document saying so.

H-1 settles this, in rule UAD1016:

    The 'Dwellings Containing Units' does not equal the number of structures
    identified as a dwelling.
    If DwellingCount does not equal the number of instances of
    IMPROVEMENT_DETAIL with ImprovementType = "Dwelling"

So the count is not a label on the side of the document -- it *is* the number
of Dwelling improvements, and the two can never disagree.  Both published
2-to-4-unit samples are consistent with that reading and show the two real
shapes: one has two buildings of one unit each ("Building 1", "Building 2"),
the other one building holding four units.

A case that starts from a template starts with the template's shape.  A
converted two-family -- one building, two units -- built from the two-building
sample therefore inherited a second dwelling it does not have, and H-1 then
asked for that phantom's year built, its structure identifier and its gross
building area, in every report built that way.  Writing the count now moves
the units together and removes what is left over, so answering the question
the report asks is what fixes the document.
"""
from __future__ import annotations

from lxml import etree

from . import bind, xsd_order
from .edit import QN, insert_ordered

DWELLING = "Dwelling"


def dwellings(prop: etree._Element) -> list[etree._Element]:
    """The IMPROVEMENTs of this property that are dwellings, in document order.

    An IMPROVEMENT with no type at all is counted as a dwelling: that is what
    a half-written block is, and leaving it out would let the count agree with
    H-1 while the document still carried a structure nobody can identify.
    """
    out = []
    for imp in prop.iter(f"{QN}IMPROVEMENT"):
        kind = imp.findtext(f"{QN}IMPROVEMENT_DETAIL/{QN}ImprovementType")
        if kind is None or (kind or "").strip() in ("", DWELLING):
            out.append(imp)
    return out


def units(imp: etree._Element) -> list[etree._Element]:
    return list(imp.iter(f"{QN}PROPERTY_UNIT"))


def _structural() -> frozenset[str]:
    """The values that say what a block *is* rather than answering anything.

    The same set a blank case keeps: the determinants that decide the form and
    the type values that identify a block.  A dwelling holding nothing but
    "Dwelling", "SiteBuilt" and the names of its own component rows is the
    empty shape the template arrived in, not something somebody filled in.
    """
    from . import templates                      # circular at module level

    return templates.structure_elements()


def _empty(node: etree._Element) -> bool:
    """Nothing but structure left: no answer anywhere underneath."""
    structural = _structural()
    return not any((child.text or "").strip()
                   for child in node.iter()
                   if isinstance(child.tag, str) and not len(child)
                   and etree.QName(child).localname not in structural)


def set_count(prop: etree._Element, count: int) -> list[str]:
    """Make the property hold exactly ``count`` dwellings, and say what moved.

    Merging keeps every unit: the units of the dwellings being removed are
    moved into the one that stays, in order, which is the shape the four-unit
    sample publishes.  A dwelling that still holds a value of its own after
    its units have moved is *not* removed -- that would throw away an answer --
    and the caller is told, so the report can say the counts disagree rather
    than quietly losing data.
    """
    said: list[str] = []
    have = dwellings(prop)
    if count < 1 or not have:
        return said

    while len(have) < count:
        imps = prop.find(f"{QN}IMPROVEMENTS")
        if imps is None:
            imps = insert_ordered(prop, "IMPROVEMENTS")
        new = insert_ordered(imps, "IMPROVEMENT")
        detail = new.find(f"{QN}IMPROVEMENT_DETAIL")
        if detail is None:
            detail = insert_ordered(new, "IMPROVEMENT_DETAIL")
        kind = detail.find(f"{QN}ImprovementType")
        if kind is None:
            kind = insert_ordered(detail, "ImprovementType")
        kind.text = DWELLING
        said.append("added a dwelling")
        have = dwellings(prop)

    keep, extra = have[:count], have[count:]
    for imp in extra:
        into = keep[-1]
        holder = into.find(f"{QN}PROPERTY_UNITS")
        for unit in units(imp):
            if _empty(unit):
                continue
            if holder is None:
                holder = insert_ordered(into, "PROPERTY_UNITS")
            unit.getparent().remove(unit)
            holder.append(unit)
            said.append("moved a living unit into the dwelling that stays")
        if _empty(imp):
            parent = imp.getparent()
            parent.remove(imp)
            # MISMO forbids an empty IMPROVEMENTS, and a document that does not
            # validate is a worse document than one with a spare block in it.
            if parent is not None and len(parent) == 0 and parent.getparent() is not None:
                parent.getparent().remove(parent)
            said.append("removed a dwelling that held nothing")
        else:
            said.append("kept a dwelling that still holds values of its own")
    return said


def counted(prop: etree._Element) -> int:
    return len(dwellings(prop))


# =====================================================================
# The structure engine: dwellings, units, ADUs and outbuildings as a tree,
# with every count derived from it (owner's brief, T-1035).
#
# From Appendix F-1 (03 Subject Property, 08 Dwelling Exterior, 10 Unit
# Interior, 12 Outbuilding), B-1 pp29-31 and the D-1 samples
# (knowledge/blueprint/STUDY.md section 4):
#
#   PROPERTY (SubjectProperty)
#     IMPROVEMENT  ImprovementType = Dwelling   STRUCTURE_DETAIL/StructureIdentifier
#       PROPERTY_UNITS/PROPERTY_UNIT   PROPERTY_UNIT_DETAIL/UnitIdentifier,
#                                      AccessoryDwellingUnitIndicator
#     IMPROVEMENT  ImprovementType = Outbuilding  OutbuildingType
#       PROPERTY_UNITS/PROPERTY_UNIT   (an ADU in the outbuilding)
#
# * 3.005 LivingUnitExcludingADUCount = units that are not ADUs; 3.006
#   AccessoryDwellingUnitTotalCount = ADUs anywhere; 3.007 DwellingCount =
#   dwellings (H-1 UAD1016).  They are recounted after every operation -- a
#   count is a reading of the tree, never a separate answer.
# * Unit Identifier is required when there is more than one living unit and
#   cannot repeat (F-1 10.002); Structure Identifier when 3.005 > 1 (8.000).
# * Each sales comparable of a multi-unit subject has one PROPERTY_UNIT per
#   subject unit, linked PROPERTY_UNIT_IsComparableFor_PROPERTY_UNIT (both
#   2-4 unit samples); a single-unit report's comparables have one, unlinked.
# * A unit's rental information is compared by rental comparables
#   (RENTAL_INFORMATION_IsComparableFor_RENTAL_INFORMATION) and its defects
#   point at it (DEFECT_ContainsDefectOf_PROPERTY_UNIT): removing the unit
#   removes what only it explains, and says so first (``loss``).
# =====================================================================
import copy as _copy                                    # noqa: E402

XL = "{http://www.w3.org/1999/xlink}"
OUTBUILDING = "Outbuilding"
ARC = "urn:fdc:mismo.org:2009:residential/"


def _subject(root: etree._Element) -> etree._Element:
    prop = bind.subject(root)
    if prop is None:
        raise ValueError("the document has no subject property")
    return prop


def _kind(imp: etree._Element) -> str:
    return (imp.findtext(f"{QN}IMPROVEMENT_DETAIL/{QN}ImprovementType") or "").strip()


def outbuildings(prop: etree._Element) -> list[etree._Element]:
    return [imp for imp in prop.iter(f"{QN}IMPROVEMENT") if _kind(imp) == OUTBUILDING]


def is_adu(unit: etree._Element) -> bool:
    return (unit.findtext(f"{QN}PROPERTY_UNIT_DETAIL/{QN}AccessoryDwellingUnitIndicator") or "").strip() == "true"


def unit_identifier(unit: etree._Element) -> str:
    return (unit.findtext(f"{QN}PROPERTY_UNIT_DETAIL/{QN}UnitIdentifier") or "").strip()


def structure_identifier(imp: etree._Element) -> str:
    return (imp.findtext(f"{QN}STRUCTURE/{QN}STRUCTURE_DETAIL/{QN}StructureIdentifier") or "").strip()


def outbuilding_type(imp: etree._Element) -> str:
    detail = imp.find(f"{QN}IMPROVEMENT_DETAIL")
    if detail is None:
        return ""
    kind = (detail.findtext(f"{QN}OutbuildingType") or "").strip()
    other = (detail.findtext(f"{QN}OutbuildingTypeOtherDescription") or "").strip()
    return other if kind == "Other" and other else kind


def all_units(prop: etree._Element) -> list[etree._Element]:
    return list(prop.iter(f"{QN}PROPERTY_UNIT"))


def _set(parent: etree._Element, path: list[str], value: str) -> etree._Element:
    from .edit import ensure_path
    holder, _ = ensure_path(parent, path[:-1])
    leaf = holder.find(f"{QN}{path[-1]}")
    if leaf is None:
        leaf = insert_ordered(holder, path[-1])
    leaf.text = value
    return leaf


def _label(root: etree._Element, stem: str) -> str:
    from .edit import _free_label
    return _free_label(root, stem)


def recount(root: etree._Element) -> dict[str, int]:
    """Write 3.005 / 3.006 / 3.007 from the tree and return them."""
    prop = _subject(root)
    units = all_units(prop)
    counts = {"LivingUnitExcludingADUCount": sum(1 for u in units if not is_adu(u)) or 1,
              "AccessoryDwellingUnitTotalCount": sum(1 for u in units if is_adu(u)),
              "DwellingCount": len(dwellings(prop)) or 1}
    for name, n in counts.items():
        _set(prop, ["PROPERTY_DETAIL", name], str(n))
    return counts


def tree(root: etree._Element) -> dict:
    """The structure as the editor shows it: dwellings with their units, then
    outbuildings (with an ADU if they hold one), and the derived counts."""
    prop = _subject(root)
    path = root.getroottree().getpath

    def unit_json(u):
        return {"key": path(u), "label": u.get(f"{XL}label", ""), "identifier": unit_identifier(u),
                "adu": is_adu(u)}
    out = {"dwellings": [], "outbuildings": []}
    for imp in dwellings(prop):
        out["dwellings"].append({"key": path(imp), "identifier": structure_identifier(imp),
                                 "units": [unit_json(u) for u in units(imp)]})
    for imp in outbuildings(prop):
        out["outbuildings"].append({"key": path(imp), "type": outbuilding_type(imp),
                                    "units": [unit_json(u) for u in units(imp)]})
    every = all_units(prop)
    out["counts"] = {"units_excluding_adus": sum(1 for u in every if not is_adu(u)),
                     "adus": sum(1 for u in every if is_adu(u)),
                     "dwellings": len(dwellings(prop)),
                     "outbuildings": len(outbuildings(prop))}
    return out


# ------------------------------------------------------------- relationships
def _relationships(root: etree._Element) -> etree._Element:
    rels = next(root.iter(f"{QN}RELATIONSHIPS"), None)
    if rels is None:
        holder = next(e for e in root.iter() if isinstance(e.tag, str)
                      and xsd_order.load().position(etree.QName(e).localname, "RELATIONSHIPS") is not None)
        rels = insert_ordered(holder, "RELATIONSHIPS")
    return rels


def _link(root: etree._Element, arc: str, source: etree._Element, target: etree._Element) -> None:
    rels = _relationships(root)
    for r in rels.findall(f"{QN}RELATIONSHIP"):
        if (r.get(f"{XL}from") == source.get(f"{XL}label") and r.get(f"{XL}to") == target.get(f"{XL}label")
                and r.get(f"{XL}arcrole", "").endswith(arc)):
            return
    r = insert_ordered(rels, "RELATIONSHIP")
    r.set(f"{XL}arcrole", ARC + arc)
    r.set(f"{XL}from", source.get(f"{XL}label"))
    r.set(f"{XL}to", target.get(f"{XL}label"))


def _labelled(root: etree._Element, el: etree._Element, stem: str) -> etree._Element:
    if not el.get(f"{XL}label"):
        el.set(f"{XL}label", _label(root, stem))
    return el


def _linked_to(root: etree._Element, labels: set[str], arc: str) -> list[str]:
    """The ``from`` labels of relationships of this arc pointing at ``labels``."""
    return [r.get(f"{XL}from") for r in root.iter(f"{QN}RELATIONSHIP")
            if r.get(f"{XL}arcrole", "").endswith(arc) and r.get(f"{XL}to") in labels]


def _by_label(root: etree._Element, label: str):
    return next((e for e in root.iter() if isinstance(e.tag, str) and e.get(f"{XL}label") == label), None)


# ------------------------------------------------------------- comparables
def _comparables(root: etree._Element) -> list[etree._Element]:
    return [p for p in root.iter(f"{QN}PROPERTY") if p.get("ValuationUseType") == "SalesComparable"]


def _comp_unit_for(root: etree._Element, comp: etree._Element, subject_unit: etree._Element):
    label = subject_unit.get(f"{XL}label")
    mine = {u.get(f"{XL}label") for u in comp.iter(f"{QN}PROPERTY_UNIT")}
    for src in _linked_to(root, {label}, "PROPERTY_UNIT_IsComparableFor_PROPERTY_UNIT"):
        if src in mine:
            return _by_label(root, src)
    return None


def _new_unit(holder_imp: etree._Element) -> etree._Element:
    holder = holder_imp.find(f"{QN}PROPERTY_UNITS")
    if holder is None:
        # a new PROPERTY_UNITS arrives holding the PROPERTY_UNIT it requires
        holder = insert_ordered(holder_imp, "PROPERTY_UNITS")
        unit = holder.find(f"{QN}PROPERTY_UNIT")
        if unit is None:
            unit = insert_ordered(holder, "PROPERTY_UNIT")
    else:
        unit = insert_ordered(holder, "PROPERTY_UNIT")
    for part in ("PROPERTY_UNIT_AREA", "PROPERTY_UNIT_DETAIL"):   # the XSD's required pair
        if unit.find(f"{QN}{part}") is None:
            insert_ordered(unit, part)
    return unit


def _match_comparables(root: etree._Element) -> list[str]:
    """Give every sales comparable one unit per subject unit, linked to it,
    when the subject has more than one; never touch a single-unit report."""
    said = []
    prop = _subject(root)
    subject_units = [u for u in all_units(prop) if not is_adu(u) or True]
    if len(subject_units) < 2:
        return said
    for su in subject_units:
        _labelled(root, su, "PROPERTY_UNIT_SUBJECT")
    for n, comp in enumerate(_comparables(root), start=1):
        unlinked = [u for u in comp.iter(f"{QN}PROPERTY_UNIT")
                    if not _linked_to_any(root, u)]
        for su in subject_units:
            if _comp_unit_for(root, comp, su) is not None:
                continue
            cu = unlinked.pop(0) if unlinked else None
            if cu is None:
                imps = [i for i in comp.iter(f"{QN}IMPROVEMENT")]
                if not imps:
                    continue
                cu = _new_unit(imps[-1])
                said.append(f"comparable {n}: added a unit row")
            _labelled(root, cu, f"PROPERTY_UNIT_COMP{n}")
            _link(root, "PROPERTY_UNIT_IsComparableFor_PROPERTY_UNIT", cu, su)
    return said


def _linked_to_any(root: etree._Element, unit: etree._Element) -> bool:
    label = unit.get(f"{XL}label")
    return bool(label) and any(r.get(f"{XL}from") == label for r in root.iter(f"{QN}RELATIONSHIP")
                               if r.get(f"{XL}arcrole", "").endswith("PROPERTY_UNIT_IsComparableFor_PROPERTY_UNIT"))


# ------------------------------------------------------------- operations
def _next_identifier(prop: etree._Element, stem: str) -> str:
    taken = {unit_identifier(u) for u in all_units(prop)} | {structure_identifier(i) for i in dwellings(prop)}
    n = 1
    while f"{stem} {n}" in taken:
        n += 1
    return f"{stem} {n}"


def _ensure_identifiers(root: etree._Element) -> None:
    """F-1 10.002 / 8.000: identifiers are required once there is more than
    one unit / dwelling, and a unit identifier cannot repeat."""
    prop = _subject(root)
    units_ = all_units(prop)
    if len(units_) > 1:
        seen = set()
        for u in units_:
            ident = unit_identifier(u)
            if not ident or ident in seen:
                ident = "ADU" if is_adu(u) and "ADU" not in seen else _next_identifier(prop, "Unit")
                _set(u, ["PROPERTY_UNIT_DETAIL", "UnitIdentifier"], ident)
            seen.add(ident)
    ds = dwellings(prop)
    if len(ds) > 1 or sum(1 for u in units_ if not is_adu(u)) > 1:
        for imp in ds:
            if not structure_identifier(imp):
                _set(imp, ["STRUCTURE", "STRUCTURE_DETAIL", "StructureIdentifier"],
                     _next_identifier(prop, "Building"))


def prune_dangling(root: etree._Element) -> int:
    """Drop relationships whose ``from`` or ``to`` names no element.

    A relationship to nothing is a broken document: an element re-labelled
    (values carried onto a new structure) or removed leaves its links behind,
    and a comparable unit linked to a unit that is not there is linked to
    none -- so it is then matched again, to a unit that exists."""
    labels = {e.get(f"{XL}label") for e in root.iter() if isinstance(e.tag, str) and e.get(f"{XL}label")}
    gone = 0
    for rels in root.iter(f"{QN}RELATIONSHIPS"):
        for r in list(rels.findall(f"{QN}RELATIONSHIP")):
            if r.get(f"{XL}from") not in labels or r.get(f"{XL}to") not in labels:
                rels.remove(r)
                gone += 1
    return gone


def tidy(root: etree._Element) -> list[str]:
    """Identifiers, comparable unit rows and counts made consistent with the tree."""
    return _finish(root, [])


def _finish(root: etree._Element, said: list[str]) -> list[str]:
    prune_dangling(root)
    _ensure_identifiers(root)
    said += _match_comparables(root)
    recount(root)
    return said


def add_unit(root: etree._Element, dwelling: int = 0, identifier: str = "",
             adu: bool = False) -> list[str]:
    """A living unit (or an ADU) in a dwelling (index, default the last)."""
    prop = _subject(root)
    ds = dwellings(prop)
    if not ds:
        add_dwelling(root)
        ds = dwellings(prop)
    imp = ds[dwelling if 0 <= dwelling < len(ds) else -1]
    unit = _new_unit(imp)
    _labelled(root, unit, "PROPERTY_UNIT_SUBJECT")
    _set(unit, ["PROPERTY_UNIT_DETAIL", "AccessoryDwellingUnitIndicator"], "true" if adu else "false")
    if identifier:
        _set(unit, ["PROPERTY_UNIT_DETAIL", "UnitIdentifier"], identifier)
    return _finish(root, ["added an ADU" if adu else "added a living unit"])


def add_dwelling(root: etree._Element, identifier: str = "") -> list[str]:
    """A dwelling (a building that holds living units), with one unit."""
    prop = _subject(root)
    imps = prop.find(f"{QN}IMPROVEMENTS")
    if imps is None:
        imps = insert_ordered(prop, "IMPROVEMENTS")
    imp = insert_ordered(imps, "IMPROVEMENT")
    _labelled(root, imp, "IMPROVEMENT_DWELLING")
    _set(imp, ["IMPROVEMENT_DETAIL", "ImprovementType"], DWELLING)
    if identifier:
        _set(imp, ["STRUCTURE", "STRUCTURE_DETAIL", "StructureIdentifier"], identifier)
    unit = _new_unit(imp)
    _labelled(root, unit, "PROPERTY_UNIT_SUBJECT")
    _set(unit, ["PROPERTY_UNIT_DETAIL", "AccessoryDwellingUnitIndicator"], "false")
    return _finish(root, ["added a dwelling with one unit"])


def add_outbuilding(root: etree._Element, kind: str = "Other", other: str = "",
                    adu: bool = False) -> list[str]:
    """An outbuilding (OutbuildingType, A-1 12.001); ``adu`` puts an ADU in it
    (a standalone ADU, or "ADUGarage" -- Other + ADUGarage, B-1 p217)."""
    prop = _subject(root)
    imps = prop.find(f"{QN}IMPROVEMENTS")
    if imps is None:
        imps = insert_ordered(prop, "IMPROVEMENTS")
    imp = insert_ordered(imps, "IMPROVEMENT")
    _labelled(root, imp, "IMPROVEMENT_OUTBUILDING")
    _set(imp, ["IMPROVEMENT_DETAIL", "ImprovementType"], OUTBUILDING)
    _set(imp, ["IMPROVEMENT_DETAIL", "OutbuildingType"], kind)
    if kind == "Other" and other:
        _set(imp, ["IMPROVEMENT_DETAIL", "OutbuildingTypeOtherDescription"], other)
    said = [f"added an outbuilding ({other or kind})"]
    if adu:
        unit = _new_unit(imp)
        _labelled(root, unit, "PROPERTY_UNIT_SUBJECT")
        _set(unit, ["PROPERTY_UNIT_DETAIL", "AccessoryDwellingUnitIndicator"], "true")
        said.append("with an ADU in it")
    return _finish(root, said)


def _gone_with(root: etree._Element, node: etree._Element) -> list[etree._Element]:
    """Everything that exists only because of ``node``: the comparables' unit
    rows for it, rental comparables' rows compared with it, defects of it."""
    labels = {e.get(f"{XL}label") for e in node.iter() if isinstance(e.tag, str) and e.get(f"{XL}label")}
    out = []
    for arc in ("PROPERTY_UNIT_IsComparableFor_PROPERTY_UNIT",
                "RENTAL_INFORMATION_IsComparableFor_RENTAL_INFORMATION",
                "DEFECT_ContainsDefectOf_PROPERTY_UNIT", "DEFECT_ContainsDefectOf_IMPROVEMENT"):
        for src in _linked_to(root, labels, arc):
            el = _by_label(root, src)
            if el is not None and all(el is not o for o in out):
                out.append(el)
    return out


def loss(root: etree._Element, node: etree._Element) -> list[str]:
    """What removing ``node`` would throw away: every answered value in it and
    in what goes with it, as "Label: value" lines (structural values aside)."""
    # identifiers name the part; on their own they are not an answer to keep
    structural = _structural() | {"UnitIdentifier", "StructureIdentifier"}
    lines = []
    for el in [node] + _gone_with(root, node):
        for leaf in el.iter():
            if (isinstance(leaf.tag, str) and not len(leaf) and (leaf.text or "").strip()
                    and etree.QName(leaf).localname not in structural):
                lines.append(f"{bind._humanise(etree.QName(leaf).localname)}: {leaf.text.strip()}")
    return lines


def _remove(root: etree._Element, node: etree._Element) -> None:
    doomed = [node] + _gone_with(root, node)
    labels = {e.get(f"{XL}label") for d in doomed for e in d.iter()
              if isinstance(e.tag, str) and e.get(f"{XL}label")}
    for el in doomed:
        parent = el.getparent()
        if parent is None:
            continue
        parent.remove(el)
        # an emptied plural wrapper goes too (MISMO forbids an empty one)
        while parent is not None and len(parent) == 0 and parent.getparent() is not None \
                and xsd_order.required(etree.QName(parent).localname):
            up = parent.getparent()
            up.remove(parent)
            parent = up
    rels = next(root.iter(f"{QN}RELATIONSHIPS"), None)
    if rels is not None:
        for r in list(rels.findall(f"{QN}RELATIONSHIP")):
            if r.get(f"{XL}from") in labels or r.get(f"{XL}to") in labels:
                rels.remove(r)


def find(root: etree._Element, key: str) -> etree._Element | None:
    hit = root.getroottree().xpath(key) if key.startswith("/") else []
    return hit[0] if hit else _by_label(root, key)


def remove(root: etree._Element, key: str) -> list[str]:
    """Remove a unit, an ADU, a dwelling (with its units) or an outbuilding.
    The subject keeps at least one dwelling with one living unit."""
    prop = _subject(root)
    node = find(root, key)
    if node is None:
        raise KeyError(key)
    name = etree.QName(node).localname
    if name == "PROPERTY_UNIT":
        living = [u for u in all_units(prop) if not is_adu(u)]
        if not is_adu(node) and len(living) <= 1:
            raise ValueError("The property keeps at least one living unit.")
        imp = next(node.iterancestors(f"{QN}IMPROVEMENT"))
        if _kind(imp) == OUTBUILDING:
            # the outbuilding stays; it no longer holds an ADU
            _remove(root, node)
            return _finish(root, ["removed the ADU from the outbuilding"])
        _remove(root, node)
        return _finish(root, ["removed an ADU" if is_adu(node) else "removed a living unit"])
    if name == "IMPROVEMENT":
        if _kind(node) != OUTBUILDING and len(dwellings(prop)) <= 1:
            raise ValueError("The property keeps at least one dwelling.")
        for u in units(node):
            _remove(root, u)
        _remove(root, node)
        return _finish(root, ["removed an outbuilding" if _kind(node) == OUTBUILDING else "removed a dwelling"])
    raise ValueError(f"{name} is not a dwelling, unit or outbuilding")


def set_units(root: etree._Element, count: int, lost: list | None = None) -> list[str]:
    """3.005 typed as a number: the same operations, until the tree has that
    many living units (added to the last dwelling, removed from the end --
    empty ones first)."""
    prop = _subject(root)
    count = max(1, min(int(count), 4))
    said: list[str] = []
    while sum(1 for u in all_units(prop) if not is_adu(u)) < count:
        said += add_unit(root)
    while True:
        living = [u for u in all_units(prop) if not is_adu(u)]
        if len(living) <= count:
            break
        empties = [u for u in living if not loss(root, u)]
        doomed = (empties or living)[-1]
        if lost is not None:
            lost += loss(root, doomed)
        said += remove(root, root.getroottree().getpath(doomed))
    return _finish(root, said)


def set_adus(root: etree._Element, count: int, lost: list | None = None) -> list[str]:
    """3.006 typed as a number: ADUs added in the primary dwelling (the
    location is then the appraiser's to change), removed from the end."""
    prop = _subject(root)
    count = max(0, int(count))
    said: list[str] = []
    while sum(1 for u in all_units(prop) if is_adu(u)) < count:
        said += add_unit(root, dwelling=0, adu=True)
    while True:
        adus = [u for u in all_units(prop) if is_adu(u)]
        if len(adus) <= count:
            break
        if lost is not None:
            lost += loss(root, adus[-1])
        said += remove(root, root.getroottree().getpath(adus[-1]))
    return _finish(root, said)
