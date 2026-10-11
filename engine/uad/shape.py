"""One report that takes the shape of the property.

UAD 3.6 has no form numbers: "data -- not a form number -- will drive the
property type" (Appendix B-1, Overview).  So there is one "New report", and the
appraiser's own answers decide what it holds.  The answers that decide it are
the six determining data points ``templates.DETERMINANT_FIELDS`` names --
valuation method, construction method, attachment, project legal structure,
site owned in common, units excluding ADUs, ADUs -- and ``templates.classify``
turns them into a property type exactly as it classifies the GSE samples.

When an answer changes that shape, the report is rebuilt on the official
structure that fits it best -- one of the twelve Appendix D-1 cases, which are
the only shapes the GSEs publish and which validate against the subschema --
and everything already entered is carried across by address, the same way an
imported file is filled in (``app/autofill.py``).  Nothing is chosen from a
list by the appraiser and nothing typed is lost silently: what could not be
placed is returned so the editor can say so.

This is the bridge to the structure engine (T-1035): a 3-unit property starts
from the 4-unit structure and the unit count is then made exact by
``structure``; an ADU in a detached outbuilding needs the ADU-location answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from . import templates


def determinants(root: etree._Element) -> dict[str, str]:
    """The six determining answers of this document (empty when unanswered)."""
    return {k: templates._text(root, xp) for k, (_fid, xp) in templates.determinants().items()}


def property_type(root: etree._Element) -> str:
    return templates.classify(determinants(root))


#: what each determining answer is worth when choosing the closest official shape
_WEIGHTS = {"units_excluding_adus": 6, "adu_count": 4, "attachment_type": 2,
            "construction_method": 2, "site_owned_in_common": 1, "valuation_method": 1,
            "project_legal_structure": 1}


def best_template(det: dict[str, str], prefer: str = "") -> str:
    """The D-1 structure closest to these answers, within their property type."""
    kind = templates.classify(det)
    pool = templates.by_property_type().get(kind) or []
    if not pool:
        return prefer

    def score(t) -> tuple:
        s = 0
        for name, w in _WEIGHTS.items():
            want = (det.get(name) or "").strip()
            have = (t.determinants.get(name) or "").strip()
            if want and want == have:
                s += w
        try:
            gap = abs(int(det.get("units_excluding_adus") or 1) - int(t.units))
        except ValueError:
            gap = 0
        # a tie goes to the preferred shape, then to the simpler one (an ADU in
        # the house before one in a detached outbuilding)
        return (s, -gap, t.key == prefer, -t.elements)

    return max(pool, key=score).key


def shape_key(det: dict[str, str]) -> tuple:
    """What, in the answers, decides the structure (the rest is just a value)."""
    try:
        units = int(det.get("units_excluding_adus") or 1)
    except ValueError:
        units = 1
    try:
        adus = int(det.get("adu_count") or 0)
    except ValueError:
        adus = 0
    return (templates.classify(det), min(max(units, 1), 4) if units >= 2 else 1, adus > 0)


@dataclass
class Reshaped:
    template: str
    property_type: str
    tree: etree._ElementTree
    carried: int = 0
    failed: list[dict] = field(default_factory=list)


def reshape(current: etree._ElementTree, template: str) -> Reshaped:
    """The same report on the structure of ``template``: a blank of it, with
    every value the current document holds written into it by address."""
    from app import autofill                    # app layer: plan / apply
    from . import delivery

    source = current.getroot()
    target = templates.load(template, blank=True)
    delivery.stamp_software(target.getroot())
    from . import setup
    developed = setup.approaches(target.getroot())     # the structure's own, before the carry
    # A structure that keeps its property data report in a SERVICE of its own
    # before the valuation's (D-1 Condo1) would take the carried valuation
    # into that first SERVICE -- two VALUATIONs.  It stands aside during the
    # carry and goes back where it was.
    from . import bind as _bind
    M_ = f"{{{_bind.MISMO}}}"
    aside = []
    for svc in list(target.getroot().iter(f"{M_}SERVICE")):
        if svc.find(f"{M_}VALUATION") is None:
            holder = svc.getparent()
            aside.append((holder, list(holder).index(svc), svc))
            holder.remove(svc)
    # the old report's own property data report SERVICE is carried whole,
    # never by position into the new valuation
    from copy import deepcopy
    source = deepcopy(source.getroottree()).getroot()
    carried_insp = []
    for svc in list(source.iter(f"{M_}SERVICE")):
        if svc.find(f"{M_}VALUATION") is None and svc.find(f"{M_}INSPECTION_SERVICE") is not None:
            carried_insp.append(svc)
            svc.getparent().remove(svc)
    steps = autofill.plan(target, source)
    # parties by their roles; the rest by place, as before -- carrying the
    # comparables by what they are changes which rental columns the new
    # structure keeps, and its unit pairings do not survive yet (T-1250)
    done = autofill.apply(target, steps, source, keyed=("PARTY",))
    for holder, index, svc in reversed(aside):
        holder.insert(index, svc)
    for svc in carried_insp:
        valuation = next((v for v in target.getroot().iter(f"{M_}SERVICE")
                          if v.find(f"{M_}VALUATION") is not None), None)
        if valuation is None:
            break
        holder = valuation.getparent()
        own = next((o for o in holder.findall(f"{M_}SERVICE") if o.find(f"{M_}VALUATION") is None), None)
        if own is not None and "".join(own.itertext()).strip():
            continue                     # the new structure's own report stays
        if own is not None:
            holder.replace(own, svc)
        else:
            holder.insert(list(holder).index(valuation), svc)
    from . import structure
    setup.keep_approaches(source, target.getroot(), developed)   # a carried "false" never switches one off
    _own_inspection_service(target.getroot())
    structure.tidy(target.getroot())      # links, identifiers and counts follow the new tree
    return Reshaped(template=template, property_type=templates.get(template).property_type,
                    tree=target, carried=done["written"], failed=done["failed"])


def _own_inspection_service(root: etree._Element) -> None:
    """A property data report carried from one structure into another lands
    beside the VALUATION in its SERVICE -- which the subschema refuses (a
    SERVICE holds one or the other).  It goes where D-1 Condo1 keeps it: a
    SERVICE of its own, before the valuation's.  When the new structure has
    one already, the carried report takes its place if that one is empty."""
    from . import bind, edit
    M_ = f"{{{bind.MISMO}}}"
    for svc in list(root.iter(f"{M_}SERVICE")):
        insp = svc.find(f"{M_}INSPECTION_SERVICE")
        if insp is None or svc.find(f"{M_}VALUATION") is None:
            continue
        holder = svc.getparent()
        # the new structure's own inspection SERVICE (blanking may have left
        # it without its INSPECTION_SERVICE): any SERVICE that is not a valuation
        own = next((o for o in holder.findall(f"{M_}SERVICE")
                    if o is not svc and o.find(f"{M_}VALUATION") is None), None)
        if own is not None:
            there = own.find(f"{M_}INSPECTION_SERVICE")
            if there is None:
                own.insert(0, insp)
            elif "".join(there.itertext()).strip():
                svc.remove(insp)            # the new structure's own report stays
            else:
                own.replace(there, insp)
            continue
        own = etree.Element(f"{M_}SERVICE")
        holder.insert(list(holder).index(svc), own)
        own.append(insp)
        detail, _ = edit.ensure_path(own, ["SERVICE_DETAIL"])
        if detail.find(f"{M_}ServiceType") is None:
            edit.insert_ordered(detail, "ServiceType").text = "Inspection"


def needed(before: dict[str, str], after: dict[str, str]) -> bool:
    """Did an answer change the shape of the report?"""
    return shape_key(before) != shape_key(after)
