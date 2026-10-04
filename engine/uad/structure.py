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
