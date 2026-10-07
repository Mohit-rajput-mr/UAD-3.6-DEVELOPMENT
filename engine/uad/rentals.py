"""Which rental comparable is compared with which subject unit.

UAD 3.6 compares rents unit to unit: a rental comparable is one rented unit,
and B-1 23.03.24 draws its column "for each rental comparable being compared
to the subject unit".  A-1 keeps that pairing as data -- the comparable holds
one RENTAL_INFORMATION per subject unit it is compared with, tied to the
unit's own RENTAL_INFORMATION by RENTAL_INFORMATION_IsComparableFor_
RENTAL_INFORMATION (D-1 2-4: Unit 1 with #1, #2, #3; Unit 2 with #1, #4, #5,
#1 carrying a different Adjusted Rent in each).  The report draws one rental
analysis per subject unit from it (comparables.rental_pairs).

Nothing in the printed form says which comparable goes with which unit, so
the editor offers it as a small matrix (owner, 2026-10-07: "how do I put each
unit ... which rental has how many units ... dynamic").
"""
from __future__ import annotations

from lxml import etree

from . import bind, edit

M = f"{{{bind.MISMO}}}"
X = "{http://www.w3.org/1999/xlink}"
ARC = "urn:fdc:mismo.org:2009:residential/RENTAL_INFORMATION_IsComparableFor_RENTAL_INFORMATION"


def subject_units(root: etree._Element) -> list[etree._Element]:
    """The subject's living units, in report order."""
    subj = bind.subject(root)
    return list(subj.iter(f"{M}PROPERTY_UNIT")) if subj is not None else []


def unit_name(unit: etree._Element, n: int) -> str:
    ident = (unit.findtext(f".//{M}UnitIdentifier") or "").strip()
    return ident or f"Unit {n}"


def _existing_unit_ri(root: etree._Element, unit: etree._Element) -> etree._Element | None:
    """The unit's own RENTAL_INFORMATION, one rule everywhere: the one a
    comparable is already tied to, else the first labelled, else the first."""
    found = unit.findall(f"{M}RENTAL_INFORMATIONS/{M}RENTAL_INFORMATION")
    targets = {r.get(f"{X}to") for r in _links(root)}
    # (an lxml element with no children is falsy: no "a or b" between them)
    for want in (lambda ri: ri.get(f"{X}label") in targets, lambda ri: bool(ri.get(f"{X}label")),
                 lambda ri: True):
        for ri in found:
            if want(ri):
                return ri
    return None


def _unit_ri(root: etree._Element, unit: etree._Element, stem: str) -> etree._Element:
    """The unit's own RENTAL_INFORMATION (made, labelled, when missing)."""
    ri = _existing_unit_ri(root, unit)
    if ri is None:
        holder, _ = edit.ensure_path(unit, ["RENTAL_INFORMATIONS"])
        ri = edit.insert_ordered(holder, "RENTAL_INFORMATION")
    if not ri.get(f"{X}label"):
        ri.set(f"{X}label", edit._free_label(root, stem))
    return ri


def _comp_unit(prop: etree._Element) -> etree._Element:
    found = prop.find(f"{M}IMPROVEMENTS/{M}IMPROVEMENT/{M}PROPERTY_UNITS/{M}PROPERTY_UNIT")
    if found is not None:
        return found
    unit_holder, _ = edit.ensure_path(prop, ["IMPROVEMENTS", "IMPROVEMENT", "PROPERTY_UNITS"])
    return edit.insert_ordered(unit_holder, "PROPERTY_UNIT")


def _links(root: etree._Element) -> list[etree._Element]:
    return [r for r in root.iter(f"{M}RELATIONSHIP") if r.get(f"{X}arcrole", "") == ARC]


def matrix(root: etree._Element) -> dict:
    """{"units": [names], "comparables": [{"number", "address", "paired": [bool per unit]}]}"""
    from .report import comparables
    units = subject_units(root)
    unit_labels = [(ri.get(f"{X}label") if (ri := _existing_unit_ri(root, u)) is not None else None)
                   for u in units]
    by_label = {e.get(f"{X}label"): e for e in root.iter(f"{M}RENTAL_INFORMATION") if e.get(f"{X}label")}
    pairs = {(r.get(f"{X}from"), r.get(f"{X}to")) for r in _links(root)}
    comps = []
    for n, prop in enumerate(comparables.properties(root, "RentalComparable"), start=1):
        own = {ri.get(f"{X}label") for ri in prop.iter(f"{M}RENTAL_INFORMATION") if ri.get(f"{X}label")}
        paired = [bool(lab) and any((o, lab) in pairs for o in own) for lab in unit_labels]
        street = (prop.findtext(f".//{M}ADDRESS/{M}AddressLineText") or "").strip()
        unit_no = (prop.findtext(f".//{M}ADDRESS/{M}AddressUnitIdentifier") or "").strip()
        comps.append({"number": comparables._number_of(prop) or n,
                      "address": " ".join(x for x in (street, f"Unit {unit_no}" if unit_no else "") if x),
                      "paired": paired})
    _ = by_label
    return {"units": [unit_name(u, i + 1) for i, u in enumerate(units)], "comparables": comps}


def set_pair(root: etree._Element, comp_index: int, unit_index: int, on: bool) -> None:
    """Compare rental comparable #comp_index (1-based, report order) with
    subject unit unit_index (1-based) -- or stop comparing them."""
    from .report import comparables
    props = comparables.properties(root, "RentalComparable")
    units = subject_units(root)
    if not (1 <= comp_index <= len(props)) or not (1 <= unit_index <= len(units)):
        raise ValueError("no such rental comparable or subject unit")
    prop, unit = props[comp_index - 1], units[unit_index - 1]
    target = _unit_ri(root, unit, f"RENTAL_INFORMATION_SUBJECT_UNIT{unit_index}")
    to = target.get(f"{X}label")
    own = {ri.get(f"{X}label"): ri for ri in prop.iter(f"{M}RENTAL_INFORMATION") if ri.get(f"{X}label")}
    existing = [r for r in _links(root) if r.get(f"{X}to") == to and r.get(f"{X}from") in own]
    if on:
        if existing:
            return
        cunit = _comp_unit(prop)
        holder, _ = edit.ensure_path(cunit, ["RENTAL_INFORMATIONS"])
        ri = edit.insert_ordered(holder, "RENTAL_INFORMATION")
        ri.set(f"{X}label", edit._free_label(root, f"RENTAL_INFORMATION_RENTCOMP{comp_index}_SUBJECTUNIT{unit_index}"))
        from . import sources
        rel = edit.insert_ordered(sources._relationships(root), "RELATIONSHIP")
        rel.set(f"{X}arcrole", ARC)
        rel.set(f"{X}from", ri.get(f"{X}label"))
        rel.set(f"{X}to", to)
        return
    for rel in existing:
        ri = own.get(rel.get(f"{X}from"))
        rel.getparent().remove(rel)
        if ri is not None:
            holder = ri.getparent()
            holder.remove(ri)
            if not len(holder):
                holder.getparent().remove(holder)


def pair_new_comparable(root: etree._Element) -> None:
    """A rental comparable just added is compared with every subject unit;
    the appraiser unticks the ones it does not fit."""
    from .report import comparables
    props = comparables.properties(root, "RentalComparable")
    if not props or len(subject_units(root)) < 2:
        return
    n = len(props)
    for u in range(1, len(subject_units(root)) + 1):
        set_pair(root, n, u, True)
