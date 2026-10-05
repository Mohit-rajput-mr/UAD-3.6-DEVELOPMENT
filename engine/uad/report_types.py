"""The two other UAD 3.6 reports: the Restricted Appraisal Update Report and
the Completion Report.

Both are MISMO documents of the same schema as the URAR, told apart by
``DOCUMENT_CLASS/DocumentType`` (ValuationUpdate / ValuationCompletion, A-2 and
A-3 HF.001), so a case's kind is read from the document itself and nothing
beside it.  Everything a kind needs comes from ``spec/report_types/<kind>.json``
(built by ``uad/spec/build_report_types.py`` from A-2/B-2/C-2/D-2/H-2 and
A-3/B-3/C-3/D-3/H-3):

  fields         Report Field ID -> section, label, data points
  form           the Layout appendix as C-1's extractor reads it
  furniture      header and footer (HF.001-HF.008)
  rules          H-2 / H-3, executed by ``compliance`` unchanged
  discriminators which party a name belongs to (A-2's Additional Context)

Their Report Field IDs restart at 01.001 and the two kinds share them, so they
are namespaced here -- ``RU-01.001`` is the update's Physical Address,
``CR-01.001`` the completion report's -- and every lookup keyed by a field ID
(bindings, choices, the editor's controls) stays unambiguous.  URAR IDs never
carry a prefix.
"""
from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path

from lxml import etree

from . import bind

SPEC = Path(__file__).resolve().parents[1] / "spec" / "report_types"
PROJECT = Path(__file__).resolve().parents[2]
M = f"{{{bind.MISMO}}}"
XLINK = "http://www.w3.org/1999/xlink"

URAR = "urar"
PREFIX = {"update": "RU", "completion": "CR"}
KINDS = tuple(PREFIX)
_BY_PREFIX = {v: k for k, v in PREFIX.items()}
_FID = re.compile(r"^(RU|CR)-(.+)$")


@lru_cache(maxsize=4)
def spec(kind: str) -> dict:
    return json.loads((SPEC / f"{kind}.json").read_text(encoding="utf-8"))


def title(kind: str) -> str:
    return spec(kind)["title"] if kind in PREFIX else "Uniform Residential Appraisal Report"


@lru_cache(maxsize=1)
def by_document_type() -> dict[str, str]:
    return {spec(k)["document_type"]: k for k in KINDS}


def kind_of(tree) -> str:
    """``update`` / ``completion`` from the document's DocumentType, else the URAR."""
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    for node in root.iter(f"{M}DocumentType"):
        kind = by_document_type().get((node.text or "").strip())
        if kind:
            return kind
    return URAR


# ---------------------------------------------------------------- field IDs
def fid(kind: str, raw: str) -> str:
    return f"{PREFIX[kind]}-{raw}" if kind in PREFIX else raw


def split(field_id: str) -> tuple[str, str]:
    """(kind, the ID as the appendix prints it); ("urar", id) for a URAR ID."""
    m = _FID.match(field_id or "")
    return (_BY_PREFIX[m.group(1)], m.group(2)) if m else (URAR, field_id)


@lru_cache(maxsize=None)
def _paths_of(kind: str, name: str) -> tuple[tuple[str, ...], ...]:
    """Every container path the kind's delivery spec gives a data point."""
    out = []
    data = spec(kind)
    points = [dp for f in data["fields"].values() for dp in f["data_points"]] + data["not_on_report"]
    for dp in points:
        if dp.get("mismo") == name and dp.get("xpath"):
            path = tuple(bind._tail(dp["xpath"]))
            if path not in out:
                out.append(path)
    return tuple(out)


@lru_cache(maxsize=4)
def _context_roles(kind: str) -> dict[str, str]:
    """Additional Context -> the PartyRoleType its data points' conditions
    name, where they all name the same one.  A-2 writes 'IF PartyRoleType =
    "Appraiser"' on the inspection method but not on the inspection date of
    the same context ("Subject Property: Appraiser: Property Inspection")."""
    seen: dict[str, set[str]] = {}
    for f in spec(kind)["fields"].values():
        for dp in f["data_points"]:
            role = (dp.get("requires") or {}).get("PartyRoleType")
            if role and dp.get("context"):
                seen.setdefault(dp["context"], set()).add(role)
    return {ctx: next(iter(r)) for ctx, r in seen.items() if len(r) == 1}


def _marks(kind: str, dp: dict) -> dict[str, str]:
    """Which instance a data point belongs to, as the URAR's ``party_marks``
    reads A-1 -- but from this kind's own Additional Context, which names
    parties the URAR index does not ("Appraiser" for 04.011 Name, so the
    borrowers' names are not read as the appraiser's)."""
    if dp.get("requires"):
        return dict(dp["requires"])
    ctx = spec(kind)["discriminators"].get(dp.get("context", ""), {})
    segs = bind._tail(dp.get("xpath", ""))
    out: dict[str, str] = {}
    if "PARTIES/PARTY/" in dp.get("xpath", "") and "PartyRoleType" in ctx:
        out["PartyRoleType"] = ctx["PartyRoleType"]
    elif dp.get("context") in _context_roles(kind):
        out["PartyRoleType"] = _context_roles(kind)[dp["context"]]
    for key, want in ctx.items():
        if key.startswith("__") or key == "PartyRoleType" or not key.endswith("Type"):
            continue
        if any(path and path[-1] in segs for path in _paths_of(kind, key)):
            out[key] = want
    return out


@lru_cache(maxsize=4096)
def entry(field_id: str) -> dict | None:
    """A field of a kind, shaped as the URAR's ``field_index`` entries are."""
    kind, raw = split(field_id)
    if kind == URAR:
        return None
    f = spec(kind)["fields"].get(raw)
    if not f:
        return None
    points = []
    for dp in f["data_points"]:
        dp = dict(dp)
        dp["requires"] = _marks(kind, dp)
        points.append(dp)
    # In a repeating block outside the parties (a defect, a completion item,
    # an image) a condition is either the row's identity -- 'IF
    # CompletionReportNewDefectIndicator = "true"': a newly observed repair --
    # or a choice of value -- 'IF DefectItemLocationType = "Other"', naming the
    # field's own list.  The identity filters the rows, every column alike
    # (``instance``); the choice is left to the display, which prints the
    # description for "Other".  Kept on the data point, either one picked the
    # first block that met it, whichever row was being read.
    names = {dp.get("mismo") for dp in points}
    instance: dict[str, str] = {}
    for dp in points:
        if "PARTIES/PARTY/" in dp.get("xpath", "") or not bind.repeating_container(dp.get("xpath", "")):
            continue
        for key, want in dp["requires"].items():
            if key not in names and key != "PartyRoleType" and not key.startswith(("@", "__")):
                instance[key] = want
    for dp in points:
        # whose block it is (an inspection is the appraiser's or the
        # supervisor's) stays with the data point; only row conditions move
        if "PARTIES/PARTY/" not in dp.get("xpath", "") and bind.repeating_container(dp.get("xpath", "")):
            dp["requires"] = {k: v for k, v in dp["requires"].items() if k == "PartyRoleType"}
    return {"locations": [{"section": f["section"], "subsection": f["subsection"],
                           "label": f["label"]}],
            "data_points": points, "display_rules": f.get("display_rules", []),
            "roles": ["Subject Property"], "kind": kind, "instance": instance}


def binding(field_id: str) -> bind.Binding | None:
    e = entry(field_id)
    if not e or not e["data_points"]:
        return None
    loc = e["locations"][0]
    return bind.Binding(field_id=field_id, section=loc["section"], subsection=loc["subsection"],
                        label=loc["label"], data_points=e["data_points"],
                        display_rules=e["display_rules"])


def section_number(kind: str, printed: str) -> int:
    """A printed section title's number in this kind's own table of contents
    (B-2 / B-3): the Layout prints "Certifications" for B-2's section 5
    "Certifications and Scope of Work"."""
    base = printed.split(" - ")[0].strip()
    for n, name in spec(kind)["sections"].items():
        if base == name or name.startswith(base) or base.startswith(name):
            return int(n)
    return 0


def fields(kind: str) -> list[str]:
    return [fid(kind, raw) for raw in spec(kind)["fields"]]


# ---------------------------------------------------------------- the layout
@lru_cache(maxsize=4)
def form(kind: str) -> dict:
    """The kind's Layout appendix (C-2 / C-3), its IDs namespaced."""
    data = copy.deepcopy(spec(kind)["form"])

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("ids"), list):
                node["ids"] = [fid(kind, x) for x in node["ids"]]
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(data)
    return data


def furniture(kind: str) -> dict[str, dict]:
    return spec(kind).get("furniture", {}) if kind in PREFIX else {}


def version_label(kind: str) -> str:
    """'Update Version #' / 'Completion Version #' (A-2/A-3 HF.002)."""
    return furniture(kind).get("HF.002", {}).get("label", "Appraisal Version #")


# ---------------------------------------------------------------- compliance
@lru_cache(maxsize=4)
def field_ids(kind: str) -> dict[str, str]:
    """H-2/H-3 Unique ID -> the (namespaced) Report Field ID it governs."""
    out: dict[str, str] = {}
    for raw, f in spec(kind)["fields"].items():
        for dp in f["data_points"]:
            if dp.get("unique_id"):
                out.setdefault(dp["unique_id"], fid(kind, raw))
    return out


def evaluate(tree, *, include_ok: bool = False):
    """H-2 / H-3 against a document of that kind."""
    from . import compliance
    kind = kind_of(tree)
    if kind == URAR:
        return compliance.evaluate(tree, include_ok=include_ok)
    return compliance.evaluate(tree, include_ok=include_ok,
                               rule_set=compliance.rules_for(kind), field_ids=field_ids(kind))


# ---------------------------------------------------------------- documents
def samples(kind: str) -> list[Path]:
    return [PROJECT / s for s in spec(kind)["samples"]]


def blank(kind: str) -> etree._ElementTree:
    """A new report of this kind: the official D-2/D-3 structure with every
    supplied value removed (``templates.clear``, as a new URAR is made), so no
    sample content reaches a real report."""
    from . import templates
    tree = etree.parse(str(samples(kind)[0]))
    templates.clear(tree.getroot())
    _set_document_type(tree.getroot(), kind)
    from . import delivery
    delivery.stamp_software(tree.getroot())
    return tree


def _set_document_type(root: etree._Element, kind: str) -> None:
    from . import edit
    want = spec(kind)["document_type"]
    node = root.find(f".//{M}DOCUMENT_CLASS/{M}DocumentType")
    if node is None:
        cls = root.find(f".//{M}DOCUMENT_CLASS")
        if cls is None:
            return
        node = edit.insert_ordered(cls, "DocumentType")
    node.text = want


# What an update or completion report states about "the original appraisal"
# (A-2 / A-3 section 02), and the URAR data point that holds it.  A-2 defines
# each as the original report's own value -- "The effective date of the
# original appraisal report", "The amount of the reconciled opinion of value
# from the original appraisal report" -- and the URAR value of that meaning is
# the one A-1 files under the label B-1 prints for it (26.011 Effective Date of
# Appraisal, 26.007 Opinion of Market Value, 26.010 Reasonable Exposure Time,
# HF.005 Appraiser Reference ID).  The pairs are named here because no
# appendix cross-references the two reports; each is checked against the D-1 /
# D-2 / D-3 pairs that share a property (SF1 -> AU1, SF2 -> CR1, SF4 -> CR2)
# in tests/test_report_types.py.
ORIGINAL = {
    "OriginalAppraisalEffectiveDate": "AppraisalReportEffectiveDate",
    "OriginalAppraisedValueAmount": "OpinionOfValueAmount",
    "OriginalAppraisalMarketingOrExposureDaysCount": "MarketingOrExposureDaysCount",
    "OriginalAppraisalMarketingOrExposureHighRangeDaysCount": "MarketingOrExposureHighRangeDaysCount",
    "OriginalAppraisalMarketingOrExposureLowRangeDaysCount": "MarketingOrExposureLowRangeDaysCount",
    "OriginalAppraiserFileIdentifier": "AppraiserFileIdentifier",
}
_RECONCILIATION = "VALUATION_RECONCILIATION_SUMMARY_DETAIL"


def _urar_value(root: etree._Element, name: str) -> str:
    if name == "AppraiserFileIdentifier":
        node = root.find(f".//{M}VALUATION_REPORT_DETAIL/{M}{name}")
    elif name == "OpinionOfValueAmount":
        node = next((n for n in root.iter(f"{M}{name}")), None)
    else:
        node = root.find(f".//{M}{_RECONCILIATION}/{M}{name}")
    return (node.text or "").strip() if node is not None else ""


def _party_name(root: etree._Element, role: str) -> str:
    for party in root.iter(f"{M}PARTY"):
        roles = [(r.text or "").strip() for r in party.iter(f"{M}PartyRoleType")]
        if role not in roles:
            continue
        full = party.findtext(f".//{M}LEGAL_ENTITY_DETAIL/{M}FullName")
        if full and full.strip():
            return full.strip()
        name = party.find(f".//{M}INDIVIDUAL/{M}NAME")
        if name is not None:
            parts = [name.findtext(f"{M}{p}") or "" for p in
                     ("FirstName", "MiddleName", "LastName", "SuffixName")]
            text = " ".join(p.strip() for p in parts if p.strip())
            if text:
                return text
    return ""


# The parties a derived report carries from its URAR: the people the
# assignment is for, not the people who will do it.  The appraiser of an
# update need not be the original appraiser (D-2 AU1 "performed by another
# appraiser"), so the appraiser and supervisor are left to be entered.
CARRIED_ROLES = ("Borrower", "Client", "Lender", "ManagementCompany")


def derive(urar, kind: str) -> tuple[etree._ElementTree, list[str]]:
    """A new update / completion report for the property of ``urar``.

    Pre-filled, by address, with every value the URAR holds in a data point
    the kind also has at the same place (subject address, county, legal
    description, property rights, the parties the assignment is for, the
    URAR's defects for a completion report's itemized repairs), and the
    Original Appraisal section from the URAR's own reconciliation.  Returns
    the document and the Report Field IDs it filled.
    """
    from . import edit
    src = urar.getroot() if hasattr(urar, "getroot") else urar
    tree = blank(kind)
    filled: list[str] = []

    def put(field_id: str, value: str, data_point: str = "", ordinal: int = 1) -> None:
        if not value:
            return
        try:
            edit.write(tree, field_id, value, data_point=data_point, ordinal=ordinal)
        except (KeyError, ValueError):
            return
        if field_id not in filled:
            filled.append(field_id)

    for raw, f in spec(kind)["fields"].items():
        field_id = fid(kind, raw)
        b = binding(field_id)
        if b is None:
            continue
        for dp in b.data_points:
            name = dp.get("mismo")
            if not name or dp.get("attribute"):
                continue
            if name in ORIGINAL:
                put(field_id, _urar_value(src, ORIGINAL[name]), name)
            elif name == "OriginalAppraiserUnparsedName":
                put(field_id, _party_name(src, "Appraiser"), name)
            elif name == "OriginalLenderUnparsedName":
                put(field_id, _party_name(src, "Lender"), name)
    _carry_same_address(src, tree, kind, put)
    filled += _carry_parties(src, tree, kind)
    if kind == "completion":
        # A-3 02.003 Market Value Condition: the original's (B-1 26.009)
        conditions = [(n.text or "").strip() for n in src.iter(f"{M}PropertyValuationConditionalConclusionType")
                      if n.getparent() is not None and _local(n.getparent().getparent()) == "VALUATION_CONDITIONS"]
        for ordinal, value in enumerate(dict.fromkeys(c for c in conditions if c), start=1):
            put(fid(kind, "02.003"), value, "PropertyValuationConditionalConclusionType", ordinal)
        filled += _carry_repairs(src, tree, kind)
    return tree, filled


def _local(node) -> str:
    return etree.QName(node).localname if node is not None and isinstance(node.tag, str) else ""


#: a defect the original appraisal acted on: B-3 03 lists "the repairs that
#: were required in the original appraisal"; a defect with no action is not one
NO_ACTION = ("", "None")


def _carry_repairs(src: etree._Element, tree, kind: str) -> list[str]:
    """The original appraisal's itemized repairs, as the Completion Report's
    Itemized List of Repairs: each DEFECT the URAR recommended an action on,
    copied whole (without its photographs, which are the original
    appraiser's), with CompletionReportNewDefectIndicator = "false" as B-3 p21
    requires of every repair carried from the original report."""
    subject = bind.subject(tree.getroot())
    source = bind.subject(src)
    if subject is None or source is None:
        return []
    picked = []
    for defect in source.iter(f"{M}DEFECT"):
        action = (defect.findtext(f".//{M}DefectItemRecommendedActionType") or "").strip()
        if action not in NO_ACTION:
            picked.append(defect)
    if not picked:
        return []
    from . import edit
    holder = subject.find(f"{M}PROPERTY_DEFECT")
    if holder is None:
        holder = edit.insert_ordered(subject, "PROPERTY_DEFECT")
    defects = holder.find(f"{M}DEFECTS")
    if defects is None:
        defects = edit.insert_ordered(holder, "DEFECTS")
    for d in list(defects):
        defects.remove(d)
    for defect in picked:
        new = copy.deepcopy(defect)
        for images in new.findall(f".//{M}IMAGES"):
            images.getparent().remove(images)
        for attr in [a for a in new.attrib if a.endswith("label")]:
            del new.attrib[attr]
        detail = new.find(f"{M}DEFECT_DETAIL")
        if detail is None:
            detail = edit.insert_ordered(new, "DEFECT_DETAIL")
        flag = detail.find(f"{M}CompletionReportNewDefectIndicator")
        if flag is None:
            flag = edit.insert_ordered(detail, "CompletionReportNewDefectIndicator")
        flag.text = "false"
        defects.append(new)
    return [fid(kind, raw) for raw in spec(kind)["fields"] if raw.startswith("03.")]


def _roles(party: etree._Element) -> set[str]:
    return {(r.text or "").strip() for r in party.iter(f"{M}PartyRoleType")}


def _carry_parties(src: etree._Element, tree, kind: str) -> list[str]:
    """The borrower, client, lender and AMC, copied whole from the URAR.

    A PARTY is self-contained and both reports use the same schema for it, so
    the block itself is carried rather than its fields one by one -- written
    by ordinal, a second borrower's name landed in whichever party the blank
    held at that position.  The blank's own parties in those roles go first."""
    root = tree.getroot()
    parties = root.find(f".//{M}SERVICE/{M}PARTIES")
    if parties is None:
        return []
    for party in list(parties.findall(f"{M}PARTY")):
        if _roles(party) and _roles(party) <= set(CARRIED_ROLES):
            parties.remove(party)
    carried = [p for p in src.iter(f"{M}PARTY") if _roles(p) & set(CARRIED_ROLES)
               and _roles(p) <= set(CARRIED_ROLES)]
    for party in carried:
        parties.append(copy.deepcopy(party))
    # the blank's links to the parties it no longer has
    labels = {e.get(f"{{{XLINK}}}label") for e in root.iter() if isinstance(e.tag, str)
              and e.get(f"{{{XLINK}}}label")}
    for rel in list(root.iter(f"{M}RELATIONSHIP")):
        if rel.get(f"{{{XLINK}}}from") not in labels or rel.get(f"{{{XLINK}}}to") not in labels:
            holder = rel.getparent()
            holder.remove(rel)
            if not len(holder):                 # MISMO: RELATIONSHIPS holds at least one
                holder.getparent().remove(holder)
    return [fid(kind, raw) for raw, f in spec(kind)["fields"].items()
            if any("PARTIES/PARTY/" in dp.get("xpath", "") and (_marks(kind, dp).get("PartyRoleType")
                   in CARRIED_ROLES) for dp in f["data_points"])] if carried else []


#: what a derived report takes from its URAR besides the Original Appraisal:
#: the subject (A-2/A-3 section 01) and, for a completion report, the repairs
#: the original appraisal required (A-3 section 03).  The inspection, the
#: certifications, the signature and the commentary are the new assignment's.
CARRIED_SECTIONS = {"update": ("01",), "completion": ("01",)}


def _carry_same_address(src, tree, kind, put) -> None:
    """Values the two reports keep in the same data point at the same place,
    read from the URAR instance by instance with the kind's own binding (so the
    same marks pick the same party) and written to the same instance."""
    for raw, f in spec(kind)["fields"].items():
        field_id = fid(kind, raw)
        b = binding(field_id)
        if b is None:
            continue
        party = False
        if any("PARTIES/PARTY/" in dp.get("xpath", "") for dp in b.data_points) \
                or raw.split(".")[0] not in CARRIED_SECTIONS.get(kind, ()):
            continue
        points = []
        for dp in b.data_points:
            name = dp.get("mismo")
            if not name or dp.get("attribute") or name.startswith("Original") \
                    or "/IMAGES/" in dp.get("xpath", ""):
                continue
            role = (dp.get("requires") or {}).get("PartyRoleType")
            if party and role not in CARRIED_ROLES:
                continue
            if party and "PARTIES/PARTY/" not in dp.get("xpath", ""):
                continue
            points.append(dp)
        if not points:
            continue
        one = bind.Binding(field_id, b.section, b.subsection, b.label, points)
        if party:
            groups = bind.read_groups(src, one)
        else:
            groups = [[(n, (node.text or "").strip())] for n, node in bind._walk(src, one, None, 1)
                      if (node.text or "").strip()]
        for ordinal, group in enumerate(groups, start=1):
            for name, value in group:
                put(field_id, value, name, ordinal if party else 1)
