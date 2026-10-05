"""Starting templates, taken from the GSEs' own Appendix D-1 sample cases.

An appraiser opening a new file should not face an empty form.  They should
land on a report already shaped for the property in front of them -- the right
sections showing, the right grids, the right number of units -- and then edit.

Rather than hand-author those shapes, this module uses the twelve official
sample cases as the templates.  That has a property nothing hand-written can
match: every template is a real case that already round-trips losslessly and
validates against the GSE subschema, so a file is never invalid because of the
template it started from.

A template is offered in two forms:

``sample``   the GSE case complete with its data, for learning the form and for
             regression testing against the published PDF.
``blank``    the same case with every appraiser-supplied value cleared but the
             structure kept, which is what "new report" actually wants.

Property type is read out of the case itself, from the six data points the
specification says determine it, never from the file name.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from lxml import etree

from .paths import SPEC_ROOT
SPEC = Path(__file__).resolve().parents[1] / "spec"
NS = {"m": "http://www.mismo.org/residential/2009/schemas"}
XLINK = "http://www.w3.org/1999/xlink"

VR = ("DOCUMENT_SETS/DOCUMENT_SET/DOCUMENTS/DOCUMENT/DEAL_SETS/DEAL_SET/DEALS/"
      "DEAL/SERVICES/SERVICE/VALUATION/VALUATION_RESPONSE")
SUBJECT = (f"{VR}/VALUATION_ANALYSES/VALUATION_ANALYSIS/PROPERTIES/"
           "PROPERTY[@ValuationUseType='SubjectProperty']")

# The data points the specification names as determining property type, each
# identified by its Report Field ID and MISMO data point name.  The xPath is
# NOT written here -- it is read from the A-1 delivery specification through
# ``engine/spec/field_index.json`` at import, so the paths can never drift from
# the spec or be mistyped from a truncated screenful.
DETERMINANT_FIELDS = {
    "valuation_method": ("1.010", "PropertyValuationMethodType"),
    "construction_method": ("1.012", "ConstructionMethodType"),
    "attachment_type": ("1.013", "AttachmentType"),
    "project_legal_structure": ("1.016", "ProjectLegalStructureType"),
    "site_owned_in_common": ("1.020", "LandOwnedInCommonIndicator"),
    "units_excluding_adus": ("1.021", "LivingUnitExcludingADUCount"),
    "adu_count": ("3.006", "AccessoryDwellingUnitTotalCount"),
}

_MESSAGE_PREFIX = "MESSAGE/"
_SUBJECT_PREDICATE = "PROPERTY[@ValuationUseType='SubjectProperty']"


@lru_cache(maxsize=1)
def _field_index() -> dict:
    return json.loads((SPEC / "field_index.json").read_text(encoding="utf-8"))["fields"]


def field_path(field_id: str, data_point: str, *, subject_only: bool = True) -> str:
    """The delivery spec's xPath for one data point, relative to MESSAGE.

    A-1 gives the *container* path in its xPath column and names the leaf
    separately, so the two are joined here.
    """
    entry = _field_index().get(field_id)
    if not entry:
        raise KeyError(f"Report Field ID {field_id} is not in the index")
    for dp in entry["data_points"]:
        if dp["mismo"] == data_point:
            path = dp["xpath"]
            if path.startswith(_MESSAGE_PREFIX):
                path = path[len(_MESSAGE_PREFIX):]
            path = path.rstrip("/") + "/" + data_point
            if subject_only:
                path = path.replace("PROPERTIES/PROPERTY/",
                                    f"PROPERTIES/{_SUBJECT_PREDICATE}/", 1)
            return path
    raise KeyError(f"{data_point} is not a data point of {field_id}")


@lru_cache(maxsize=1)
def determinants() -> dict[str, tuple[str, str]]:
    """Each determining data point as (Report Field ID, subject xPath)."""
    return {name: (fid, field_path(fid, dp))
            for name, (fid, dp) in DETERMINANT_FIELDS.items()}

@lru_cache(maxsize=1)
def kept_elements() -> frozenset[str]:
    """Elements a new file inherits, because they decide its shape.

    These are the determining data points -- the same ones that classify a
    sample into a property type -- and nothing else.  Which sections, grids and
    subsections a report has follows from them, so a case that dropped them
    would open as the wrong form.
    """
    return frozenset(dp for _fid, dp in DETERMINANT_FIELDS.values())


@lru_cache(maxsize=1)
def supplied_elements() -> frozenset[str]:
    """Every element the appraiser supplies, read from A-1.

    A new report must inherit none of them.  The set is *derived*: an element
    is appraiser-supplied exactly when Appendix A-1 binds it to a Report Field
    ID, which is the definition A-1 itself uses.  It was previously a list of
    name suffixes written out by hand, and a hand-written list is wrong in the
    way lists are -- ``StateCode`` and ``PostalCode`` end in neither "Name" nor
    "Text" nor "Identifier", so the sample's state and ZIP survived into every
    blank case and printed on the title line of somebody else's report.
    """
    from . import bind
    # every data point A-1 defines -- not only those the old page model laid
    # out, which let the sample's areas, legal description, coordinates and
    # comments survive into every blank case
    names = set()
    identity = set()
    for entry in _field_index().values():
        for dp in entry.get("data_points") or []:
            if isinstance(dp, dict) and dp.get("mismo") and not dp.get("attribute"):
                names.add(dp["mismo"])
            identity.update(k for k in (dp.get("requires") or {}) if not k.startswith(("@", "__")))
    for marks in bind.discriminators().values():
        identity.update(k for k in marks if not k.startswith("__"))
    # a type that says which block this is (which adjustment, which market
    # inventory, which charge) is structure, not an answer -- but a Yes/No or
    # a description never is
    identity = {k for k in identity if k.endswith("Type") and not k.endswith("OtherDescription")}
    return frozenset(names) - kept_elements() - identity


# Type values that say *which* block a block is -- whose party, which
# adjustment, which market inventory, which commentary, which utility row --
# rather than answering a question.  A-1's Additional Context names them.
# The rest of a sample's values are its answers and never reach a new report.
IDENTITY = frozenset({
    "PartyRoleType", "ComparableAdjustmentType", "MarketInventoryType", "ValuationAnalysisCategoryType",
    "AdditionalValuationIdentifierType", "AmenityCategoryType", "AssociationChargeType", "FeeType",
    "ParcelIdentificationType", "ServiceType", "ValuationAdditionalCertificationIncludedByType",
    "UtilityType", "ImprovementType", "ImprovementComponentType",
    "DocumentType", "DocumentFormIssuingEntityNameType", "DocumentFormIssuingEntityVersionIdentifier",
    "ValuationReportContentIdentifier",
    # a comparable's number is the column it occupies, not the sample's answer:
    # without it every blank report was blocked as "not numbered 1..n"
    "PropertyOrdinalNumber",
    # what a unit or an outbuilding *is*: a blank of SF4 that dropped the ADU
    # flag counted its ADU as a second living unit and became a 2-unit report
    # (uad/structure.py counts from these)
    "AccessoryDwellingUnitIndicator", "OutbuildingType",
    # which approaches the report develops decides which sections it has
    # (B-1: Sales Comparison / Income / Cost / Rental Information display on
    # these); a new report starts with its shape's, and the appraiser changes
    # them -- unanswered, the editor hid the sales grid of every new report
    "SalesComparisonApproachIndicator", "CostApproachIndicator", "IncomeApproachIndicator",
    "RentScheduleIndicator",
})


@lru_cache(maxsize=1)
def structure_elements() -> frozenset[str]:
    """What a blank case keeps: the determinants that decide its form, and the
    identity types above.  Every other value -- areas, dates, names, legal
    description, coordinates, comments, file numbers, the sample's software
    vendor -- is the sample's own answer and is removed."""
    return kept_elements() | IDENTITY


@dataclass
class Template:
    """One starting point, derived from an official sample case."""
    key: str
    name: str
    path: Path
    property_type: str
    determinants: dict[str, str]
    scenario: dict[str, str] = field(default_factory=dict)
    elements: int = 0
    comps: int = 0
    units: int = 1
    pdf: Path | None = None
    images: list[Path] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "property_type": self.property_type,
            "determinants": self.determinants,
            "scenario": self.scenario,
            "elements": self.elements,
            "comps": self.comps,
            "units": self.units,
            "images": len(self.images),
            "has_reference_pdf": self.pdf is not None,
            "source": self.path.name,
        }


# "PROPERTY[@ValuationUseType='SubjectProperty']" -> element name, predicate
_SEGMENT = re.compile(r"^([A-Za-z_][\w.-]*)(\[.*\])?$")


def _qualify(path: str) -> str:
    """Add the MISMO namespace prefix to each element name, keeping predicates."""
    parts = []
    for seg in path.split("/"):
        if not seg or seg.startswith("@") or seg.startswith("m:"):
            parts.append(seg)
            continue
        m = _SEGMENT.match(seg)
        parts.append(f"m:{m.group(1)}{m.group(2) or ''}" if m else seg)
    return "/".join(parts)


def _text(root: etree._Element, path: str) -> str:
    """Read one value by its MISMO path, with the namespace applied."""
    found = root.xpath(f"./{_qualify(path)}", namespaces=NS)
    if not found:
        return ""
    node = found[0]
    return (node.text or "").strip() if hasattr(node, "text") else str(node).strip()


def classify(det: dict[str, str]) -> str:
    """The property type the six determining data points imply.

    Order matters: a legal structure decides the type before unit count does,
    because a two-unit condominium is a condominium, not a 2-4 unit property.
    """
    legal = (det.get("project_legal_structure") or "").lower()
    construction = (det.get("construction_method") or "").lower()
    units = det.get("units_excluding_adus") or "1"
    try:
        unit_count = int(units)
    except ValueError:
        unit_count = 1

    if "cooperative" in legal or "coop" in legal:
        return "cooperative"
    if "condominium" in legal or "condo" in legal:
        return "condominium"
    if "manufactured" in construction or "mobile" in construction:
        return "manufactured"
    if unit_count >= 2:
        return "two_to_four_unit"
    if legal:
        return "planned_unit_development"
    return "single_family"


PROPERTY_TYPES = {
    "single_family": "Single family",
    "two_to_four_unit": "2- to 4-unit",
    "condominium": "Condominium",
    "cooperative": "Cooperative",
    "manufactured": "Manufactured home",
    "planned_unit_development": "Planned unit development",
}


def _scenario_rows() -> list[dict[str, str]]:
    path = SPEC / "supplements.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("d1_scenario_matrix", [])


def _match_scenario(name: str, rows: list[dict[str, str]]) -> dict[str, str]:
    """Join a sample file to its row in the D-1 scenario matrix."""
    stem = re.sub(r"[^a-z0-9]", "", name.lower())
    for noise in ("xml", "appraisal", "v14", "v12"):
        stem = stem.replace(noise, "")
    # Among the rows whose name is a prefix of the file stem (or the reverse),
    # take the closest in length.  "2to4unit" must not match the longer
    # "2to4unitscenario2" when the plain "2to4unitscenario" row also fits.
    best, distance = {}, None
    for row in rows:
        label = str(row.get("Sample Scenario Name", "")).lower()
        key = re.sub(r"[^a-z0-9]", "", label)
        # "Condominium 1 (Condo1) Scenario" -> the parenthesised short name
        short = re.findall(r"\(([^)]+)\)", label)
        for k in [key] + [re.sub(r"[^a-z0-9]", "", s) for s in short]:
            if not k:
                continue
            if k.startswith(stem) or stem.startswith(k) or k in stem or stem in k:
                gap = abs(len(k) - len(stem))
                if distance is None or gap < distance:
                    best, distance = row, gap
    return {k: " ".join(str(v).split()) for k, v in best.items()
            if v and str(v).strip()}


@lru_cache(maxsize=1)
def catalogue() -> list[Template]:
    """Every official sample, classified and described."""
    rows = _scenario_rows()
    seen: dict[str, Path] = {}
    for p in sorted(SPEC_ROOT.rglob("*_Appraisal_v1.*.xml")):
        seen.setdefault(p.name, p)

    out: list[Template] = []
    for name, path in seen.items():
        tree = etree.parse(str(path))
        root = tree.getroot()
        det = {k: _text(root, xp) for k, (_fid, xp) in determinants().items()}
        comps = len(root.xpath(
            f".//m:PROPERTY[@ValuationUseType='SalesComparable']", namespaces=NS))
        try:
            units = max(1, int(det.get("units_excluding_adus") or 1))
        except ValueError:
            units = 1
        key = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
        pdf = next((q for q in path.parent.glob("*.pdf")), None)
        images = sorted(q for q in path.parent.rglob("*")
                        if q.suffix.lower() in (".jpg", ".jpeg", ".png"))
        out.append(Template(
            key=key,
            name=path.stem.replace("_", " "),
            path=path,
            property_type=classify(det),
            determinants={k: v for k, v in det.items() if v},
            scenario=_match_scenario(path.name, rows),
            elements=sum(1 for _ in root.iter() if isinstance(_.tag, str)),
            comps=comps,
            units=units,
            pdf=pdf,
            images=images,
        ))
    out.sort(key=lambda t: (t.property_type, t.key))
    return out


def get(key: str) -> Template:
    for t in catalogue():
        if t.key == key:
            return t
    raise KeyError(f"no template {key!r}; have {[t.key for t in catalogue()]}")


def by_property_type() -> dict[str, list[Template]]:
    out: dict[str, list[Template]] = {}
    for t in catalogue():
        out.setdefault(t.property_type, []).append(t)
    return out


def load(key: str, *, blank: bool = False, prune_empty: bool = False
         ) -> etree._ElementTree:
    """The template's case document, optionally cleared of supplied values.

    A blank case is deliberately **not** schema-valid.  MISMO requires values
    in the elements it declares mandatory, so any report that is not finished
    yet fails the XSD by definition -- that is information for the appraiser,
    not a defect.  Schema validity is enforced where it belongs, at export, and
    reported continuously in between; see ``uad.review``.
    """
    tpl = get(key)
    tree = etree.parse(str(tpl.path))
    if blank:
        clear(tree.getroot(), prune_empty=prune_empty)
    return tree


def clear(root: etree._Element, *, prune_empty: bool = False) -> int:
    """Strip appraiser-supplied values, keeping the structure that shapes the form.

    A cleared value is **removed**, never blanked: MISMO types an empty element
    as an invalid value rather than as absent data, so a blanked element would
    read as a wrong answer instead of an unanswered question.

    Containers are kept by default.  They cost nothing, and they give the
    editor a ready insertion point for the value that belongs there, which
    keeps writes local instead of rebuilding a branch each time.
    """
    removed = 0
    # Images belong to the appraiser, not to the template: a new report starts
    # with none, so the GSE sample's photos never appear in someone's report.
    for images in list(root.iter(f"{{{NS['m']}}}IMAGES")):
        parent = images.getparent()
        if parent is not None:
            parent.remove(images)
            removed += 1
    keep = structure_elements()
    for node in list(root.iter()):
        if not isinstance(node.tag, str) or len(node):
            continue
        local = etree.QName(node).localname
        if local in keep or not (node.text or "").strip():
            continue
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)
            removed += 1
    bare = _drop_bare_instances(root)
    if bare < 0:                         # the removal made the schema worse
        root.getroottree().getroot()     # nothing to undo: it is re-read below
        bare = 0
    removed += bare
    removed += _drop_bare_repeats(root)
    if prune_empty:
        removed += prune(root)
    _restore_required_containers(root)
    return removed


_EXPECTED = re.compile(r"Element '\{[^}]*\}(\w+)': This element is not expected\. "
                       r"Expected is \( \{[^}]*\}(\w+) \)")


def _restore_required_containers(root: etree._Element, rounds: int = 8) -> int:
    """Put back a required container that blanking emptied away.

    Removing a template's parties can take their PARTIES wrapper with them,
    and the schema then rejects the next sibling ("RELATIONSHIPS is not
    expected; expected PARTIES").  An empty wrapper is valid and carries no
    value, so it is restored -- only when the schema names exactly one
    expected element, and only when restoring it makes the document better.
    No value is ever invented here."""
    from . import edit, schema          # circular at module level
    restored = 0
    for _ in range(rounds):
        errors = schema.validate(root.getroottree())
        fixed = False
        for err in errors:
            m = _EXPECTED.search(getattr(err, "message", "") or "")
            path = getattr(err, "path", "") or ""
            if not m or not path:
                continue
            found = root.getroottree().xpath(path)
            if not found:
                continue
            parent = found[0].getparent()
            if parent is None or parent.find(f"{{{NS['m']}}}{m.group(2)}") is not None:
                continue
            new = edit.insert_ordered(parent, m.group(2))
            if len(schema.validate(root.getroottree())) < len(errors):
                restored += 1
                fixed = True
                break
            parent.remove(new)
        if not fixed:
            break
    return restored


#: Containers whose only surviving content after blanking is the value that
#: says *which* instance they are, and the element that says it.  A-1 conditions
#: the data points inside each of these on that very value, so an instance left
#: holding nothing else is not an unanswered question -- it is a claim that the
#: thing exists, and every conditional field beneath it then reads as missing.
#: IMPROVEMENT is deliberately NOT in this list.  Dropping a bare dwelling did
#: clear the "year built for each dwelling" findings, and it also emptied
#: IMPROVEMENTS, which MISMO requires to hold at least one IMPROVEMENT -- five
#: schema errors in place of a handful of completeness findings, which is a
#: worse document.  Removing one needs the empty container to go with it; see
#: TASKS.md.
BARE_INSTANCES = (("PARTY", "PartyRoleType"),)


def _drop_bare_instances(root: etree._Element) -> int:
    """Remove instances that blanking left holding nothing but their own type.

    Two cases, one shape.  The GSE samples name a supervisory appraiser and
    describe a second dwelling and an outbuilding; most reports have none of
    them.  Those discriminators are structure, so they survived blanking, and
    H-1 then asked for that supervisor's credentials and that dwelling's year
    built and defect answers -- in every report built from a template.
    """
    from . import schema                # circular at module level

    before = len(schema.validate(root.getroottree()))
    removed = 0
    for tag, discriminator in BARE_INSTANCES:
        removed += _drop_bare(root, tag, discriminator)
    if removed and len(schema.validate(root.getroottree())) > before:
        # Taking the last party out left RELATIONSHIPS pointing at a list that
        # is no longer there, which the XSD rejects outright.  A document that
        # does not validate is worse than one carrying a bare instance, so the
        # whole removal is undone rather than half-applied.
        return -1
    return removed


#: Blocks whose emptiness is a claim rather than an unanswered question.
#: A sample's comparable grid carries an adjustment row for every line it uses;
#: blanking takes the amounts out and keeps the row, because the type that says
#: *which* adjustment it is counts as structure.  What is left is fifteen to
#: seventeen blocks per comparable that name an adjustment and state none, and
#: a form drawn from that document asks the appraiser for an adjustment on
#: every one of those rows.  A defect with no defect in it, and a certification
#: included by a supervisory appraiser the report does not have, read the same
#: way.
#:
#: Only blocks that say something by existing belong here.  PROPERTY, PARTY and
#: IMPROVEMENT deliberately do not: the report is *about* those, the grid is
#: built from them, and a report that starts with no comparable properties has
#: no columns to fill.
BARE_BLOCKS = ("COMPARABLE_ADJUSTMENT", "PROPERTY_DEFECT",
               "VALUATION_REPORT_ADDITIONAL_CERTIFICATION",
               "AMENITY", "SALES_HISTORY")


def _drop_bare_repeats(root: etree._Element) -> int:
    """Remove the blocks in ``BARE_BLOCKS`` that hold nothing but their type.

    A block goes only when its parent wraps it in the plural -- it is one of
    several the document may hold -- and the whole removal is put back if the
    schema likes the result any less.  That guard is the lesson IMPROVEMENT
    taught: dropping a bare dwelling cleared some findings and emptied
    IMPROVEMENTS, which MISMO requires to hold one, and five schema errors is
    a worse document than a spare block.  The emptied container goes with the
    last block inside it.
    """
    from . import bind, schema          # circular at module level

    before = len(schema.validate(root.getroottree()))
    keep = structure_elements()
    removed, undo = 0, []

    def bare(node: etree._Element) -> bool:
        return not any((leaf.text or "").strip()
                       for leaf in node.iter()
                       if isinstance(leaf.tag, str) and not len(leaf)
                       and etree.QName(leaf).localname not in keep)

    for node in list(root.iter()):
        if not isinstance(node.tag, str) or not len(node):
            continue
        name = etree.QName(node).localname
        if name not in BARE_BLOCKS:
            continue
        parent = node.getparent()
        if parent is None or not bind.is_plural_of(etree.QName(parent).localname, name):
            continue
        if not bare(node):
            continue
        undo.append((parent, list(parent).index(node), node))
        parent.remove(node)
        removed += 1
        if len(parent) == 0 and parent.getparent() is not None:
            grand = parent.getparent()
            undo.append((grand, list(grand).index(parent), parent))
            grand.remove(parent)
            removed += 1

    if len(schema.validate(root.getroottree())) > before:
        for parent, where, node in reversed(undo):
            parent.insert(where, node)
        return 0
    return removed


def _drop_bare(root: etree._Element, tag: str, discriminator: str) -> int:
    """Remove every ``tag`` whose only content is its ``discriminator``.

    The GSE samples name a supervisory appraiser; most reports have none.  The
    role survives blanking because a role is structure, so a new case declared
    a supervisor it did not have -- and H-1 then demanded that supervisor's
    credentials, licence number and expiry, three fatal findings in every
    report made from a template.

    Dropping one is safe because it is not the editor's insertion point: a data
    point conditioned on a discriminator ('IF PartyRoleType =
    "AppraiserSupervisor"', 'IF ImprovementType = "Dwelling"') is written
    through ``uad.edit.instance_for``, which finds the instance carrying that
    value **or creates it**.  So the instance comes back the moment the
    appraiser puts something in it, and until then the report does not claim it
    exists.
    """
    removed = 0
    for node in list(root.iter(f"{{{NS['m']}}}{tag}")):
        said = [e for e in node.iter()
                if isinstance(e.tag, str) and (e.text or "").strip()]
        if said and all(etree.QName(e).localname == discriminator for e in said):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)
                removed += 1
                # The list may not be left standing empty: MISMO requires a
                # PARTIES to hold a PARTY, and an empty one is a schema error
                # in place of the finding it was meant to clear.
                if len(parent) == 0 and parent.getparent() is not None:
                    parent.getparent().remove(parent)
                    removed += 1
    return removed


def prune(root: etree._Element) -> int:
    """Drop containers that hold no data, repeatedly, from the leaves up."""
    dropped = 0
    while True:
        empties = [n for n in root.iter()
                   if isinstance(n.tag, str) and n is not root and not len(n)
                   and not (n.text or "").strip()
                   and f"{{{XLINK}}}label" not in n.attrib
                   and etree.QName(n).localname.isupper()]
        if not empties:
            return dropped
        for node in empties:
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)
                dropped += 1


def main() -> None:
    cat = catalogue()
    print(f"{len(cat)} templates from the official Appendix D-1 samples\n")
    groups = by_property_type()
    for ptype in sorted(groups):
        print(f"  {PROPERTY_TYPES.get(ptype, ptype)}")
        for t in groups[ptype]:
            det = t.determinants
            print(f"     {t.key:<38} {t.elements:>5} elem  {t.comps} comps  "
                  f"{t.units} unit(s)  {len(t.images):>2} images"
                  f"{'  +pdf' if t.pdf else ''}")
            bits = [f"{k}={v}" for k, v in det.items()
                    if k not in ("units_excluding_adus",)]
            print(f"        {', '.join(bits)}")
            if t.scenario.get("Additional Notes"):
                print(f"        note: {t.scenario['Additional Notes'][:88]}")
    missing = [t.key for t in cat if not t.scenario]
    if missing:
        print(f"\n  no scenario-matrix row matched: {missing}")


if __name__ == "__main__":
    main()
