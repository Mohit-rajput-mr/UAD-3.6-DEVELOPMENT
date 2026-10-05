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
    steps = autofill.plan(target, source)
    done = autofill.apply(target, steps, source)
    return Reshaped(template=template, property_type=templates.get(template).property_type,
                    tree=target, carried=done["written"], failed=done["failed"])


def needed(before: dict[str, str], after: dict[str, str]) -> bool:
    """Did an answer change the shape of the report?"""
    return shape_key(before) != shape_key(after)
