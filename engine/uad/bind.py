"""Bind the page's labels to the case's values.

Three artifacts have to meet for a field to be drawn:

  ``page_layout.json``   where a label sits -- section, subsection, column,
                         indent, order -- read back from the twelve samples
  ``field_index.json``   what that label means -- its Report Field ID, its
                         MISMO data points and their xPaths, its enumerations
  the case document      the value itself

The join is the label, because that is what the page shows and what A-1's
"Report Location" column names.  A-1 packs every place a field displays into
one string -- ``Summary - {No Subsection} - Opinion of Market Value 26.007:
Reconciliation - Appraisal Summary - ...`` -- so the string is split back into
the separate locations it describes rather than read as one.

A label may belong to more than one field (``Company Name`` appears under the
client, the AMC and the appraiser), so a lookup is always scoped by section and
subsection first, and the enclosing MISMO container decides between whatever
remains.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from lxml import etree

SPEC = Path(__file__).resolve().parents[1] / "spec"
MISMO = "http://www.mismo.org/residential/2009/schemas"

# "2.057: Assignment Information - Contact Information - Reference ID"
LOCATION = re.compile(r"(?:^|\s)(\d{1,2}\.\d{2,3}(?:\.\d{1,2})?)\s*:\s*")
NO_SUBSECTION = "{No Subsection}"
NO_LABEL = "{No Label}"


@dataclass(frozen=True)
class Location:
    field_id: str
    section: str
    subsection: str
    label: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.section.casefold(), self.label.casefold())


def _split_locations(field_id: str, raw: str) -> list[Location]:
    """Pull every "Section - Subsection - Label" out of one packed string."""
    text = " ".join(str(raw or "").split())
    if not text:
        return []
    marks = [(m.start(), m.end(), m.group(1)) for m in LOCATION.finditer(text)]
    spans: list[tuple[str, str]] = []
    if not marks:
        spans.append((field_id, text))
    else:
        if marks[0][0] > 0:
            spans.append((field_id, text[:marks[0][0]]))
        for i, (_s, end, fid) in enumerate(marks):
            stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
            spans.append((fid, text[end:stop]))

    out: list[Location] = []
    for fid, chunk in spans:
        parts = [p.strip() for p in chunk.split(" - ")]
        if len(parts) < 2:
            continue
        section = parts[0]
        label = parts[-1]
        subsection = " - ".join(parts[1:-1])
        if subsection == NO_SUBSECTION:
            subsection = ""
        if label in (NO_LABEL, ""):
            continue
        out.append(Location(fid, section, subsection, label))
    return out


@dataclass
class Binding:
    """One label on the page and the data behind it."""
    field_id: str
    section: str
    subsection: str
    label: str
    data_points: list[dict] = field(default_factory=list)
    display_rules: list[dict] = field(default_factory=list)

    @property
    def enumerations(self) -> list[dict]:
        for dp in self.data_points:
            if dp.get("enumerations"):
                return dp["enumerations"]
        return []

    @property
    def leaf_names(self) -> list[str]:
        return [dp["mismo"] for dp in self.data_points if dp.get("mismo")]

    def to_json(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id, "section": self.section,
            "subsection": self.subsection, "label": self.label,
            "data_points": [
                {k: dp.get(k) for k in
                 ("mismo", "xpath", "unique_id", "format_type", "format_details",
                  "conditionality", "cardinality")}
                for dp in self.data_points],
            "enumerations": self.enumerations,
            "display_rules": self.display_rules,
        }


@lru_cache(maxsize=1)
def _index() -> dict:
    return json.loads((SPEC / "field_index.json").read_text(encoding="utf-8"))["fields"]


@lru_cache(maxsize=1)
def locations() -> list[Location]:
    """Every place the index says a field displays.

    ``build_index`` already splits A-1's packed Report Location into one entry
    per place, so that list is used directly; the string parser above stays for
    reading a raw delivery row.
    """
    out: list[Location] = []
    for fid, entry in _index().items():
        places = entry.get("locations") or []
        if places:
            out.extend(Location(fid, p["section"], p.get("subsection", ""),
                                p["label"]) for p in places if p.get("label"))
        else:
            out.extend(_split_locations(fid, entry.get("report_location", "")))
    return out


@lru_cache(maxsize=1)
def by_label() -> dict[tuple[str, str], list[Binding]]:
    """Every (section, label) on the page, with the fields behind it."""
    index = _index()
    out: dict[tuple[str, str], list[Binding]] = {}
    for loc in locations():
        entry = index.get(loc.field_id)
        if not entry:
            continue
        binding = Binding(
            field_id=loc.field_id, section=loc.section,
            subsection=loc.subsection, label=loc.label,
            data_points=entry.get("data_points", []),
            display_rules=entry.get("display_rules", []),
        )
        out.setdefault(loc.key, []).append(binding)
    return out


def lookup(section: str, label: str, subsection: str = "") -> list[Binding]:
    """Fields displaying under this label, best match on subsection first."""
    found = by_label().get((section.casefold(), label.casefold()), [])
    if subsection:
        exact = [b for b in found if b.subsection.casefold() == subsection.casefold()]
        if exact:
            return exact
    return found


# --------------------------------------------------------------------------
# Reading values out of a case
# --------------------------------------------------------------------------
def _tail(xpath: str) -> list[str]:
    return [s for s in xpath.strip("/").split("/") if s and s not in ("..", "MESSAGE")]


PROPERTY_PATH = "PROPERTIES/PROPERTY"


# Containers that are plural in name but single in a report: there is one
# service, one deal, one valuation.  Treating SERVICES/SERVICE as a repeat
# makes every field on the page look like a repeating block.
DOCUMENT_SINGLETONS = {
    "DOCUMENT_SET", "DOCUMENT", "DEAL_SET", "DEAL", "SERVICE",
    "VALUATION_ANALYSIS", "PROPERTY",
}

# Containers that genuinely repeat but are not addressed by position: a PARTY
# is picked by its PartyRoleType -- the borrower, the appraiser, the lender --
# so counting them returns whichever happens to be written first, and the
# borrower's name comes back empty.  A-1's Conditionality Details names the
# discriminator for these rather than an ordinal.
DISCRIMINATED = {"PARTY", "AMENITY", "AMENITY_CATEGORY"}


def repeating_container(xpath: str) -> str:
    """The element that repeats along this path, if one does.

    MISMO marks a repeat by wrapping the singular in its plural:
    ``DEFECTS/DEFECT``, ``ROOMS/ROOM``, ``PROPERTY_UNITS/PROPERTY_UNIT``.  The
    innermost such pair below the document's own singletons is the one a
    field's ordinal selects, which is how the report's second defect block
    reads the second defect rather than the first.
    """
    segments = _tail(xpath)
    found = ""
    for parent, child in zip(segments, segments[1:]):
        if child in DOCUMENT_SINGLETONS or child in DISCRIMINATED:
            continue
        if _is_plural(parent, child):
            found = child
    return found


def _is_plural(parent: str, child: str) -> bool:
    """Whether ``parent`` is the container MISMO wraps ``child`` in.

    Most are the singular with an S.  Fourteen in the subschema are not:
    a trailing Y becomes IES -- PARTIES/PARTY, SALES_HISTORIES/SALES_HISTORY,
    PROPERTIES/PROPERTY, AMENITIES/AMENITY and the rest.  Matching only
    ``<child>S`` misses every one of them, so no ordinal ever selects an
    instance and the second prior sale, the second party and the second
    amenity are all written over the first.
    """
    # The blocks whose instance is picked by a type value rather than a
    # position -- PARTY, AMENITY, AMENITY_CATEGORY -- are held apart in
    # DISCRIMINATED, so recognising the Y->IES plural here no longer lets a
    # row keyed by a category read the first amenity of any category.
    return parent in (f"{child}S", f"{child}ES") or (
        child.endswith("Y") and parent == f"{child[:-1]}IES")


def nth_instance(root: etree._Element, container: str, ordinal: int,
                 scope: etree._Element | None = None) -> etree._Element | None:
    """The ordinal-th instance of a repeating container, counting from 1."""
    base = root if scope is None else scope
    found = base.findall(f".//{{{MISMO}}}{container}")
    if 1 <= ordinal <= len(found):
        return found[ordinal - 1]
    return None


def subject(root: etree._Element) -> etree._Element | None:
    """The property the report is about."""
    for prop in root.iter(f"{{{MISMO}}}PROPERTY"):
        if prop.get("ValuationUseType") == "SubjectProperty":
            return prop
    return None


def read(root: etree._Element, binding: Binding, scope: etree._Element | None = None
         ) -> list[str]:
    """The values this binding's data points hold, in the given scope.

    A data point that lives under a PROPERTY is read from the **subject**
    property unless a scope is given.  Every comparable repeats the same
    container path, so searching the whole document returns the subject's
    answer joined to three or five comparables' answers -- which is not a field
    value, it is the sales grid flattened into one line.
    """
    return [v for _name, v in read_parts(root, binding, scope)]


def locate(root: etree._Element, binding: Binding, data_point: str,
           scope: etree._Element | None = None,
           ordinal: int = 1) -> etree._Element | None:
    """The element a read of this data point would return, if it exists.

    Editing uses this so a write lands exactly where the page reads from.
    Building a second path-walk for writes is how a value ends up in a
    comparable, or in a defect block the page never looks at.
    """
    for name, node in _walk(root, binding, scope, ordinal):
        if name == data_point:
            return node
    return None


def read_parts(root: etree._Element, binding: Binding,
               scope: etree._Element | None = None,
               ordinal: int = 1) -> list[tuple[str, str]]:
    """The values, each tagged with the data point it came from.

    Keeping the data point lets the page tell a composed value from a repeated
    one.  ``Borrower Name`` is FirstName plus LastName and reads "Betty
    Borrower"; ``Recommended Action`` is one element occurring twice and reads
    "Repair | None".
    """
    out: list[tuple[str, str]] = []
    for name, node in _walk(root, binding, scope, ordinal):
        text = (node.text or "").strip()
        if text and (name, text) not in out:
            out.append((name, text))
    return out


def is_plural_of(parent: str, child: str) -> bool:
    """Does this parent name the collection of that child?

    MISMO is mostly regular -- DEFECTS/DEFECT -- but not always: PARTIES/PARTY
    and VALUATION_COMMENTARIES/VALUATION_COMMENTARY turn a final Y into IES.

    This looser test is used only for grouping values by the instance they sit
    in.  ``repeating_container`` keeps the strict test deliberately, because it
    answers a different question -- whether A-1 gives each repeat its own field
    IDs -- and the irregular ones are exactly the containers where it does not.
    """
    return (parent == f"{child}S" or parent == f"{child}ES"
            or (child.endswith("Y") and parent == f"{child[:-1]}IES"))


def instance_of(node: etree._Element) -> str:
    """Which repeated container a value sits in.

    Two borrowers are two PARTY elements, each with its own first and last
    name.  Composing by data point instead would print "Betty | Bob Borrower":
    both first names, then one surname.  Composing per instance prints "Betty
    Borrower | Bob Borrower".

    The key is the element's path, not its ``id``.  lxml hands out a fresh
    proxy object on each access, so two reads of the same element compare
    unequal by identity and every value would look like its own instance.
    """
    tree = node.getroottree()
    cur = node.getparent()
    last = node
    while cur is not None:
        parent = cur.getparent()
        if parent is not None and isinstance(parent.tag, str):
            if is_plural_of(etree.QName(parent).localname,
                            etree.QName(cur).localname):
                return tree.getpath(cur)
        last = cur
        cur = parent
    return tree.getpath(last)


def stable_path(node: etree._Element) -> str:
    """An element's address that survives edits elsewhere in the document.

    ``getpath`` numbers an element among *all* its siblings (``*[26]``), so
    adding any element before it renumbers it, and a page drawn a moment ago
    would write into the wrong row.  This names each step by its tag and its
    place among siblings of that tag (``SITE_UTILITY[2]``), which only changes
    if another instance of the same container is inserted before it.
    """
    return node.getroottree().getelementpath(node)


def find_path(root: etree._Element, path: str) -> etree._Element | None:
    """The element a ``stable_path`` names, or None."""
    if not path:
        return None
    if path == ".":
        return root
    if path.startswith("/"):                         # an older getpath() address
        hits = root.getroottree().xpath(path)
        return hits[0] if hits else None
    return root.find(path)


def read_groups(root: etree._Element, binding: Binding,
                scope: etree._Element | None = None,
                ordinal: int = 1) -> list[list[tuple[str, str]]]:
    """The values, gathered into the instance each came from."""
    order: list[str] = []
    groups: dict[str, list[tuple[str, str]]] = {}
    for name, node in _walk(root, binding, scope, ordinal):
        text = (node.text or "").strip()
        if not text:
            continue
        key = instance_of(node)
        if key not in groups:
            groups[key] = []
            order.append(key)
        if (name, text) not in groups[key]:
            groups[key].append((name, text))
    return [groups[k] for k in order]


def scope_for(root: etree._Element, xpath: str,
              scope: etree._Element | None, ordinal: int
              ) -> etree._Element | None:
    """Where in the document this data point is read from, or written to.

    A data point under a PROPERTY belongs to the subject unless told otherwise,
    and a data point inside a repeating block belongs to the ordinal-th
    instance of it.  Returns None when that instance does not exist.
    """
    base = scope
    if base is None:
        if PROPERTY_PATH in xpath:
            found = subject(root)
            base = root if found is None else found
        else:
            base = root
    # A-1 gives each repeat of a block its own field IDs -- the second defect
    # is 1.040-1.045, the third 1.048-1.053 -- so the ordinal picks which
    # instance this block uses.  Without it every block shows the first.
    container = repeating_container(xpath)
    picked = _nth_on_path(base, xpath, container, ordinal) if container else None
    if picked is not None:
        return picked
    return None if ordinal > 1 else base


def _nth_on_path(base: etree._Element, xpath: str, container: str,
                 ordinal: int) -> etree._Element | None:
    """The ordinal-th instance of the container *on the path A-1 gives*.

    The same container name can sit under several parents that mean quite
    different things: VALUATION_APPROACH_EXCLUSION_REASON appears once under
    COST_APPROACH, once under INCOME_APPROACH and once under
    SALES_COMPARISON_APPROACH.  Searching the whole document for the name
    alone took whichever came first, so the reason the income approach was
    excluded was written into the cost approach's block -- and the field it
    was written for then read back empty.

    So candidates are narrowed to those whose ancestors match the path, as far
    back as the document actually goes.  A shorter run of the path is tried
    when the full one matches nothing, which is what keeps a scope deeper than
    the path (a comparable's PROPERTY) working.
    """
    segments = _tail(xpath)
    if container in segments:
        prefix = segments[:segments.index(container)]
        for start in range(len(prefix)):
            want = prefix[start:]
            if not want:
                break
            found = [node for node in base.iter(f"{{{MISMO}}}{container}")
                     if _matches(node, want)]
            if found:
                return found[ordinal - 1] if 1 <= ordinal <= len(found) else None
    return nth_instance(base, container, ordinal, base)


# ------------------------------------------------------------- commentary
# Every commentary box in the report writes the same data point,
# ValuationCommentText, into the same repeating block, VALUATION_COMMENTARY.
# What tells one box from another is the ValuationAnalysisCategoryType beside
# it, so a read that ignores the category shows the wrong comment and a write
# that ignores it overwrites one.  B-1 names the category for the fields it
# discusses; where it does not, the A-1 enumeration whose name spells the
# field's own label is used ("Site Influence Commentary" -> SiteInfluences).


@lru_cache(maxsize=1)
def commentary_categories() -> dict[str, str]:
    path = SPEC / "commentary_categories.json"
    data = json.loads(path.read_text(encoding="utf-8"))["map"] if path.exists() else {}
    rows = json.loads((SPEC / "enumerations.json").read_text(encoding="utf-8"))
    enums = {r["Supported Enumerations"] for r in rows
             if r.get("MISMO Data Point / Attribute Name") == "ValuationAnalysisCategoryType"}
    key = {_squash(e): e for e in enums}
    key.update({_squash(e).rstrip("s"): e for e in enums})
    for fid, entry in _index().items():
        if fid in data:
            continue
        if not any(is_commentary(dp) for dp in entry.get("data_points", [])):
            continue
        for loc in entry.get("locations") or []:
            label = loc.get("label", "")
            if label in (NO_LABEL, ""):
                label = loc.get("subsection", "")
            stem = _squash(re.sub(r"(Commentary|Analysis of|Analysis|Reconciliation of)", "", label))
            for cand in (stem, stem.rstrip("s"), "site" + stem, stem.replace("view", "siteview")):
                if cand in key:
                    data[fid] = key[cand]
                    break
            if fid in data:
                break
    return data


def is_commentary(dp: dict) -> bool:
    """Does this data point sit in a categorised VALUATION_COMMENTARY?"""
    return "VALUATION_COMMENTAR" in (dp.get("xpath") or "")


@lru_cache(maxsize=4096)
def commentary_category(field_id: str) -> str:
    known = commentary_categories().get(field_id)
    if known:
        return known
    for dp in (_index().get(field_id) or {}).get("data_points") or []:
        if is_commentary(dp):
            cat = (discriminators().get(dp.get("context", ""), {}) or {}).get(
                "ValuationAnalysisCategoryType")
            if cat:
                return cat
    return ""


@lru_cache(maxsize=4096)
def binding_for(field_id: str) -> "Binding | None":
    """A binding built straight from A-1's index, for any Report Field ID (an
    update or completion report's namespaced ID from its own appendix)."""
    entry = _index().get(field_id)
    if entry is None:
        from . import report_types
        return report_types.binding(field_id)
    if not entry.get("data_points"):
        return None
    loc = (entry.get("locations") or [{}])[0]
    return Binding(field_id=field_id, section=loc.get("section", ""),
                   subsection=loc.get("subsection", ""), label=loc.get("label", ""),
                   data_points=entry["data_points"],
                   display_rules=entry.get("display_rules", []))


def commentary_marks(field_id: str, dp: dict) -> dict[str, str]:
    """The category that picks this field's own commentary, if it is one."""
    if not is_commentary(dp):
        return {}
    cat = commentary_category(field_id)
    return {"ValuationAnalysisCategoryType": cat} if cat else {}


def _squash(v: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(v).casefold())


def _walk(root: etree._Element, binding: Binding,
          scope: etree._Element | None, ordinal: int,
          marks: dict[str, str] | None = None):
    """Every element this binding addresses, as (data point name, element).

    One traversal serves both reading and writing, so an edit can never land
    somewhere the page does not look.
    """
    for dp in binding.data_points:
        name = dp.get("mismo")
        if not name or not re.match(r"^[A-Za-z_][\w.]*$", name):
            continue
        xpath = dp.get("xpath", "")
        if (scope is not None and "DATA_SOURCES/DATA_SOURCE" in xpath
                and etree.QName(scope).localname == "PROPERTY"):
            # a property's data sources are kept once, in the valuation's
            # DATA_SOURCES, each tied to the property by a
            # DATA_SOURCE_IsDataSourceFor_PROPERTY relationship (D-1 SF1 prints
            # "Assessor Record | Exterior Inspection | MLS 123456")
            for ds in linked_data_sources(scope):
                for node in ds.iter(f"{{{MISMO}}}{name}"):
                    yield name, node
            continue
        if scope is None and is_inspection_service(dp):
            svc = inspection_service(root)
            if svc is None:
                continue
            yield from _walk(root, Binding(binding.field_id, binding.section, binding.subsection,
                                           binding.label, [dp]), svc, ordinal)
            continue
        explicit = {k: v for k, v in (dp.get("requires") or {}).items()
                    if not k.startswith(("@", "__"))}
        # the caller may name the instance itself: three grid rows share one
        # field ID and are told apart by the type their label spells
        explicit.update(marks or {})
        container = repeating_container(xpath)
        if not explicit and container:
            # A-1 left the condition to the Additional Context: its type value
            # picks the instance when it sits inside that repeating block
            # (ASSOCIATION_CHARGE by AssociationChargeType)
            ctx = discriminators().get(dp.get("context", ""), {})
            inner = ctx.get("__container__", "")
            segs_ = _tail(xpath)
            if inner and container in segs_ and inner in segs_[segs_.index(container):]:
                # only a type value identifies an instance; an indicator or a
                # description copied from a sample does not
                explicit = {k: v for k, v in ctx.items()
                            if not k.startswith("__") and k.endswith("Type")}
        if not explicit and "PARTIES/PARTY/" in xpath:
            explicit = party_marks(dp)
        explicit.update(commentary_marks(binding.field_id, dp))
        if explicit and container:
            # 'IF PartyRoleType = "Appraiser"' names the instance: the ordinal
            # counts the instances that meet it, not every ROLE in the
            # document -- counting all of them read the Lender's role for the
            # appraiser's ASC identifier and found nothing.
            yield from _walk_marked(root, name, xpath, explicit, container, ordinal, scope)
            continue
        base = scope_for(root, xpath, scope, ordinal)
        if base is None:
            continue
        segments = _tail(xpath)
        # Two different mechanisms pick an instance, and only one applies at a
        # time.  Where MISMO wraps a singular in its plural (DEFECTS/DEFECT),
        # A-1 gives each repeat its own field IDs and the ordinal selects it.
        # Where it does not (VALUATION_COMMENTARIES/VALUATION_COMMENTARY), one
        # field ID covers every instance and a type value beside it selects.
        # Applying both would filter a defect by a label type that merely says
        # its description is free text, and find nothing.
        # A-1 often states the instance outright -- 'IF PartyRoleType =
        # "Borrower"' -- and that is taken first because it is written per data
        # point.  Otherwise the Additional Context column groups a data point
        # with the type value that identifies its instance.
        marks = dict(dp.get("requires") or {})
        if not marks and not repeating_container(xpath):
            marks = discriminators().get(dp.get("context", ""), {})
        marks.update(commentary_marks(binding.field_id, dp))
        for node in base.iter(f"{{{MISMO}}}{name}"):
            if segments and not _matches(node, segments):
                continue
            if marks and not _instance_matches(node, marks):
                continue
            yield name, node


def linked_data_sources(prop: etree._Element) -> list[etree._Element]:
    """The DATA_SOURCEs a relationship ties to this property, in document order."""
    label = prop.get(f"{{{XLINK}}}label")
    if not label:
        return []
    root = prop.getroottree().getroot()
    wanted = [rel.get(f"{{{XLINK}}}from") for rel in root.iter(f"{{{MISMO}}}RELATIONSHIP")
              if rel.get(f"{{{XLINK}}}to") == label
              and rel.get(f"{{{XLINK}}}arcrole", "").endswith("DATA_SOURCE_IsDataSourceFor_PROPERTY")]
    by_label = {ds.get(f"{{{XLINK}}}label"): ds for ds in root.iter(f"{{{MISMO}}}DATA_SOURCE")}
    return [by_label[w] for w in wanted if w in by_label]


def party_marks(dp: dict) -> dict[str, str]:
    """A party's data point identified only by A-1's Additional Context
    ("Assignment Information: Appraiser" -> PartyRoleType Appraiser), with any
    other type value of that context whose block the data point sits in
    (FeeType AppraisalFee, for a value inside PROVIDED_SERVICE)."""
    ctx = discriminators().get(dp.get("context", ""), {})
    if "PartyRoleType" not in ctx:
        return {}
    marks = {"PartyRoleType": ctx["PartyRoleType"]}
    segs = _tail(dp.get("xpath", ""))
    cond = dp.get("conditionality_details") or ""
    for key, want in ctx.items():
        if not key.endswith("Type") or key == "PartyRoleType":
            continue
        paths = _paths_of(key)
        if any(path and path[-1] in segs for path in paths) or (not paths and key in cond):
            marks[key] = want
    return marks


@lru_cache(maxsize=None)
def _paths_of(name: str) -> tuple[tuple[str, ...], ...]:
    """Every container path A-1 gives a data point of this name."""
    out = []
    for entry in _index().values():
        for dp in entry.get("data_points") or []:
            if dp.get("mismo") == name and dp.get("xpath"):
                path = tuple(_tail(dp["xpath"]))
                if path not in out:
                    out.append(path)
    return tuple(out)


def is_inspection_service(dp: dict) -> bool:
    """A data point of the Property Data Report: it lives in the second
    SERVICE, the one whose ServiceType is Inspection (D-1 condo 1)."""
    if "INSPECTION_SERVICE" in dp.get("xpath", ""):
        return True
    ctx = discriminators().get(dp.get("context", ""), {})
    role = (dp.get("requires") or {}).get("PartyRoleType") or ctx.get("PartyRoleType")
    return ctx.get("ServiceType") == "Inspection" or role == "PropertyDataCollector"


def inspection_service(root: etree._Element) -> etree._Element | None:
    for svc in root.iter(f"{{{MISMO}}}SERVICE"):
        kind = svc.find(f"{{{MISMO}}}SERVICE_DETAIL/{{{MISMO}}}ServiceType")
        if kind is not None and (kind.text or "").strip() == "Inspection":
            return svc
    return None


def _walk_marked(root, name, xpath, marks, container, ordinal, scope=None):
    base = root if scope is None else scope
    if scope is None and PROPERTY_PATH in xpath:
        found = subject(root)
        base = root if found is None else found
    segments = _tail(xpath)
    instances: list = []
    hits: dict = {}
    for node in base.iter(f"{{{MISMO}}}{name}"):
        if segments and not _matches(node, segments):
            continue
        if not _instance_matches(node, marks):
            continue
        inst = node
        while inst is not None and etree.QName(inst).localname != container:
            inst = inst.getparent()
        # by address, never by id(): lxml builds a fresh proxy on each access,
        # so id() is not stable and two instances can share one -- which made
        # a second render of the same document drop a row the first one drew
        key = node.getroottree().getelementpath(inst) if inst is not None else ""
        if key not in hits:
            instances.append(key)
            hits[key] = []
        hits[key].append(node)
    if 1 <= ordinal <= len(instances):
        for node in hits[instances[ordinal - 1]]:
            yield name, node


@lru_cache(maxsize=1)
def discriminators() -> dict[str, dict[str, str]]:
    """Per A-1 Additional Context, the type value that identifies an instance."""
    data = json.loads((SPEC / "field_index.json").read_text(encoding="utf-8"))
    return data.get("discriminators", {})


XLINK = "http://www.w3.org/1999/xlink"


def related_role(node: etree._Element) -> etree._Element | None:
    """The ROLE an element is tied to by an xlink relationship
    (INSPECTION_CompletedBy_ROLE, SIGNATORY_IsAssociatedWith_ROLE): the
    nearest ancestor with an xlink:label, followed to the ROLE it names."""
    root = node.getroottree().getroot()
    cur = node
    while cur is not None:
        label = cur.get(f"{{{XLINK}}}label") if isinstance(cur.tag, str) else None
        if label:
            for rel in root.iter(f"{{{MISMO}}}RELATIONSHIP"):
                if rel.get(f"{{{XLINK}}}from") == label and rel.get(f"{{{XLINK}}}arcrole", "").endswith("_ROLE"):
                    to = rel.get(f"{{{XLINK}}}to")
                    for el in root.iter(f"{{{MISMO}}}ROLE"):
                        if el.get(f"{{{XLINK}}}label") == to:
                            return el
        cur = cur.getparent()
    return None


def _outside_party(node: etree._Element) -> bool:
    cur = node.getparent()
    while cur is not None:
        if etree.QName(cur).localname == "PARTY":
            return False
        cur = cur.getparent()
    return True


def instance_has(node: etree._Element, marks: dict[str, str]) -> bool:
    """Strictly: every type value is present on this instance and equal.
    (Reading forgives a missing type; writing must not, or a second fee
    overwrites the first.)"""
    for key, want in marks.items():
        if key.startswith("__") or not key.endswith("Type"):
            continue
        if key == "PartyRoleType" and _outside_party(node):
            role = related_role(node)
            got = role.findtext(f"{{{MISMO}}}ROLE_DETAIL/{{{MISMO}}}PartyRoleType") if role is not None else None
        else:
            got, cur = None, node.getparent()
            while cur is not None and got is None:
                hit = cur.find(f"{{{MISMO}}}{key}")
                if hit is None:
                    hit = cur.find(f".//{{{MISMO}}}{key}")
                got = None if hit is None else (hit.text or "").strip()
                cur = cur.getparent()
        if got != want:
            return False
    return True


def _instance_matches(node: etree._Element, marks: dict[str, str]) -> bool:
    """Is this the instance the field means?

    Every VALUATION_COMMENTARY holds a ``ValuationCommentText``; which comment
    belongs to which field is settled by the category beside it.  The same goes
    for a party: every PARTY holds a ``FirstName``, and the borrower is told
    from the appraiser by the ``PartyRoleType`` in the role beneath it.

    The discriminator rarely sits next to the value -- a name is in
    PARTY/INDIVIDUAL/NAME while the role is in PARTY/ROLES/ROLE/ROLE_DETAIL --
    so the search climbs to the nearest ancestor that has one and judges there.
    Searching only the immediate parent finds nothing and lets every party
    through, which prints all of them on one line.
    """
    for key, want in marks.items():
        if key.startswith("__"):
            continue
        if key == "PartyRoleType" and _outside_party(node):
            # an inspection is the appraiser's or the supervisor's by the
            # relationship that says who completed it, not by whichever
            # party's role a climb up the document happens to reach first
            role = related_role(node)
            got = role.findtext(f"{{{MISMO}}}ROLE_DETAIL/{{{MISMO}}}PartyRoleType") if role is not None else None
            if (got or "").strip() != want:
                return False
            continue
        tag = f"{{{MISMO}}}{key}"
        cur = node.getparent()
        found = None
        while cur is not None and found is None:
            found = cur.find(tag) if cur.find(tag) is not None else cur.find(f".//{tag}")
            if found is None:
                cur = cur.getparent()
        if found is None:
            continue
        if (found.text or "").strip() != want:
            return False
    return True


def _matches(node: etree._Element, segments: list[str]) -> bool:
    """Does this node sit at the end of the container path the spec names?"""
    cur = node.getparent()
    for want in reversed(segments):
        if cur is None:
            return False
        if etree.QName(cur).localname != want:
            return False
        cur = cur.getparent()
    return True


ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
ISO_MONTH = re.compile(r"^(\d{4})-(\d{2})$")


# A-1 writes a numeric field's precision as "+9.2" or "±3.6": digits before
# the point, then digits after.  That is what decides whether a figure prints
# as $491,000 or $121.25, and it is read from the specification rather than
# guessed from the value -- a price per square foot of exactly two dollars
# prints "$2.00" in the samples, which no rule based on the value could know.
PRECISION = re.compile(r"[+±]?\d+\.(\d+)")


def decimals(details: str) -> int | None:
    m = PRECISION.search(str(details or ""))
    return int(m.group(1)) if m else None


def format_value(raw: str, format_type: str, details: str = "",
                 data_point: str = "") -> str:
    """Write a value the way the report prints it.

    A-1 declares each data point's ``UAD Data Point Format Type`` -- Amount,
    Date, Numeric -- and its precision, so the presentation follows the
    specification rather than a guess.  The XML carries 491000 and 2019-09-20;
    the page shows $491,000 and 09/20/2019.
    """
    text = raw.strip()
    if not text:
        return ""
    kind = format_type.strip().casefold()
    places = decimals(details)

    if kind in ("amount", "percent", "count", "numeric", "number", "measure"):
        try:
            number = float(text)
        except ValueError:
            return text
        if (places and kind in ("numeric", "number", "measure", "count")
                and not data_point.endswith("Percent")):
            # A-1's "+3.2" bounds the digits (three before the point, two
            # after); it does not pad them.  Every D-1 sample prints the digits
            # the XML carries -- 3 as "3", 0.40 as "0.40" -- with a leading
            # zero where the XML has none (B-1 supplement, Proximity to Subject:
            # ".5" is "0.5").
            return literal_number(text)
        if places is None:
            places = 0 if number == int(number) else 2
        shown = f"{abs(number):,.{places}f}"
        if kind == "amount":
            # B-1 Figure 22-5 and every D-1 sample (121 times, never "-$"):
            # a negative amount prints in parentheses, $(10,000)
            return f"$({shown})" if number < 0 else f"${shown}"
        if kind == "percent" or data_point.endswith("Percent"):
            return f"-{shown}%" if number < 0 else f"{shown}%"
        return f"-{shown}" if number < 0 else shown

    if kind == "date":
        m = ISO_DATE.match(text)
        if m:
            return f"{m.group(2)}/{m.group(3)}/{m.group(1)}"
        m = ISO_MONTH.match(text)
        if m:
            return f"{m.group(2)}/{m.group(1)}"
    return text


AREA_UNITS = {"SquareFeet": "Sq. Ft.", "Acres": "Acres", "SquareMeters": "Sq. M.",
              "Hectares": "Hectares"}


LINEAR_UNITS = {"Feet": "Feet", "Kilometers": "Kilometers", "Meters": "Meters", "Miles": "Miles"}


def literal_number(text: str) -> str:
    """A number as the XML wrote it, with the thousands grouped and a zero
    before a bare decimal point: "3" -> "3", "0.40" -> "0.40", ".5" -> "0.5"."""
    raw = text.strip()
    sign = "-" if raw.startswith("-") else ""
    whole, point, fraction = raw.lstrip("+-").partition(".")
    whole = f"{int(whole):,}" if whole.isdigit() else (whole or "0")
    return f"{sign}{whole}{point}{fraction}"


def format_linear(text: str, unit: str) -> str:
    """A distance with its unit in one cell, as B-1 says and the samples print
    it: "3 Miles", "0.02 Miles".  The unit is never made singular ("1 Miles",
    D-1 2-4 unit)."""
    return f"{literal_number(text)} {LINEAR_UNITS.get(unit, _humanise(unit))}".strip()


def with_unit(text: str, node: etree._Element) -> str:
    """A value with the unit its element carries -- an area, or a distance."""
    unit = node.get("AreaUnitOfMeasureType")
    if unit:
        return format_area(text, unit)
    unit = node.get("LinearUnitOfMeasureType")
    if unit:
        return format_linear(text, unit)
    return text


AMOUNT_CENTS = re.compile(r"(\$[\d,]+)\.00(?!\d)")


def format_area(text: str, unit: str) -> str:
    """An area as the samples print it: '14,950 Sq. Ft.', '10.5 Acres'."""
    try:
        number = float(text)
    except ValueError:
        return f"{text} {AREA_UNITS.get(unit, unit)}".strip()
    shown = f"{number:,.3f}".rstrip("0").rstrip(".")
    return f"{shown} {AREA_UNITS.get(unit, _humanise(unit))}".strip()


def trim_cents(text: str, label: str = "") -> str:
    """Whole dollars print without cents, as every sample sets them."""
    if "Per " in (label or ""):
        return text
    return AMOUNT_CENTS.sub(lambda m: m.group(1), text)


NO_PRINT = re.compile(r"^<<.*>>$")


def answer_label(value: str, printed: str = "") -> str:
    """What the editor calls an answer, where the report may print nothing.

    B-1 gives some answers no printed text -- "Known Renewable Energy
    Components: true" prints "<<Does Not Display>>", because the components
    themselves print instead.  That marker is a print rule, not a label: as a
    choice it read "<<Does Not Display>>", and an answered "Yes" looked
    unanswered (owner's section test B7).  A Boolean indicator is Yes / No
    (A-1 format Boolean); any other value keeps its printed form or its own
    words."""
    printed = (printed or "").strip()
    if printed and not NO_PRINT.match(printed):
        return printed
    v = (value or "").strip()
    if v.lower() == "true":
        return "Yes"
    if v.lower() == "false":
        return "No"
    return _humanise(v) if v else ""


def display_value(values: list[str] | list[tuple[str, str]], binding: Binding) -> str:
    """The text the page shows for a field.

    Two shapes have to be told apart.  Several *different* data points under
    one label compose a single value and are written with spaces between them
    -- FirstName and LastName make "Betty Borrower".  One data point occurring
    several times is a list, and the report separates those with a pipe, as the
    samples do: "Repair | None".
    """
    if not values:
        return ""
    # A list of lists is already grouped by instance; compose each and join
    # the instances with a pipe -- or, where B-1 says the instances "stack",
    # one to a line.
    if values and isinstance(values[0], list):
        if binding.field_id in ROOF_DETAIL:
            return _roof_detail([p for g in values for p in g], binding)
        values = _in_enumeration_order(values, binding)
        shown = [display_value(group, binding) for group in values]
        stacked = composite_for([dp.get("mismo", "") for dp in binding.data_points])
        return ("\n" if stacked and stacked.stack else " | ").join(s for s in shown if s)
    parts: list[tuple[str, str]] = [
        v if isinstance(v, tuple) else ("", v) for v in values]
    if binding.field_id in ROOF_DETAIL:
        return _roof_detail(parts, binding)
    days = _days_text(parts)
    if days:
        return days
    address = _address_text(parts)
    if address:
        return address
    if {n for n, _ in parts} == {"DataSourceType", "DataSourceIdentifier"}:
        parts = sorted(parts, key=lambda p: p[0] != "DataSourceType")
    if any(n in NAME_ORDER for n, _ in parts) and all(n in NAME_ORDER for n, _ in parts):
        # a person's name reads First Middle Last Suffix, whatever order A-1
        # lists the data points in
        parts = sorted(parts, key=lambda p: NAME_ORDER.index(p[0]))

    by_point: dict[str, dict] = {dp.get("mismo", ""): dp
                                 for dp in binding.data_points if dp.get("mismo")}
    groups: list[tuple[str, list[str]]] = []
    for name, raw in parts:
        if groups and groups[-1][0] == name:
            groups[-1][1].append(raw)
        else:
            groups.append((name, [raw]))

    rendered: list[tuple[str, str]] = []
    for name, raws in groups:
        dp = by_point.get(name, {})
        options = {o["value"]: o.get("display", "")
                   for o in (dp.get("enumerations") or []) if o.get("value")}
        kind = (dp.get("format_type") or "").strip()
        details = dp.get("format_details") or ""
        shown = []
        if len(raws) > 1 and all(r in options for r in raws):
            # several values of one enumerated data point list in the order A-1
            # lists the enumeration, not the order the XML happened to write
            # them: D-1 prints "Deck | Porch" for Porch, Deck (and "8 Ft. | 9 Ft.
            # | 10 or more feet", which alphabetical order would not give)
            rank = {value: n for n, value in enumerate(options)}
            raws = sorted(raws, key=rank.__getitem__)
        for raw in raws:
            if raw in options:
                text = options[raw]
                if text:                     # blank means "does not display"
                    shown.append(text)
            elif kind and kind.casefold() not in ("enumerated", "boolean"):
                shown.append(format_value(raw, kind, details, name))
            else:
                shown.append(_humanise(raw))
        if shown:
            rendered.append((name, " | ".join(shown)))
    composite = composite_for([n for n, _ in rendered])
    if composite:
        return composite.join(rendered)
    return " ".join(text for _n, text in rendered).strip()


# B-1 8.033 (p171): "When true, display RoofMaterialType. When false, display
# '(Unobservable)'"; materials separated by "|"; "Display 'Estimated Age:'
# followed by the number and 'years' on a separate line under material."
# The grid's Roof row (22.08.20) says the same about its materials.
ROOF_DETAIL = {"8.033"}


def _roof_detail(parts: list[tuple[str, str]], binding: Binding) -> str:
    by_point = {dp.get("mismo", ""): dp for dp in binding.data_points}

    def shown(name: str, raw: str) -> str:
        options = {o["value"]: o.get("display", "")
                   for o in (by_point.get(name, {}).get("enumerations") or []) if o.get("value")}
        return options.get(raw, "") if raw in options else _humanise(raw)

    observable = next((raw for name, raw in parts if name == "RoofObservableIndicator"), "")
    materials = [shown(name, raw) for name, raw in parts
                 if name in ("RoofMaterialType", "RoofMaterialTypeOtherDescription")]
    age = next((shown(name, raw) for name, raw in parts if name == "RoofEstimatedAgeRangeType"), "")
    first = ("(Unobservable)" if observable.strip().casefold() == "false"
             else " | ".join(m for m in materials if m))
    return "\n".join(x for x in (first, f"Estimated Age: {age}" if age else "") if x)


def _in_enumeration_order(groups: list, binding: Binding) -> list:
    """Instances that each hold one value of the same enumerated data point
    (two AMENITY blocks, Porch then Deck) list in A-1's enumeration order, as
    D-1 prints "Deck | Porch" -- the same rule as several values in one block."""
    if len(groups) < 2 or not all(isinstance(g, list) and len(g) == 1 and isinstance(g[0], tuple)
                                  for g in groups):
        return groups
    names = {g[0][0] for g in groups}
    if len(names) != 1:
        return groups
    dp = next((d for d in binding.data_points if d.get("mismo") == next(iter(names))), {})
    rank = {o["value"]: n for n, o in enumerate(dp.get("enumerations") or []) if o.get("value")}
    if not rank or not all(g[0][1] in rank for g in groups):
        return groups
    return sorted(groups, key=lambda g: rank[g[0][1]])


@dataclass(frozen=True)
class Composite:
    """A cell several data points share, in the order and with the separator
    B-1 gives it.  Without one, different data points under a label compose a
    value with spaces ("Betty Borrower")."""
    order: tuple[str, ...]
    sep: str = " | "
    stack: bool = False          # several instances: one to a line
    tail: tuple[str, ...] = ()   # joined last, with a space, not the separator
    authority: str = ""

    @property
    def names(self) -> set[str]:
        return set(self.order) | set(self.tail)

    def join(self, rendered: list[tuple[str, str]]) -> str:
        by: dict[str, str] = {}
        for name, text in rendered:
            base = name[:-len("OtherDescription")] if name.endswith("OtherDescription") else name
            by[base] = f"{by[base]} {text}" if base in by else text
        head = [by[n] for n in self.order if n in by]
        head += [t for n, t in by.items() if n not in self.order and n not in self.tail]
        tail = [by[n] for n in self.tail if n in by]
        return " ".join(x for x in (self.sep.join(head), " ".join(tail)) if x)


COMPOSITES = (
    Composite(("StreetAccessType", "ImprovedSurfaceMaterialType"), stack=True,
              authority="B-1 4.021 p130; grid 'Street Type | Surface'"),
    Composite(("HeatingSystemType", "HeatingFuelType"), stack=True,
              authority="grid 'Heating': System and Fuel separated by |, a line for each system"),
    Composite(("FullBathroomCount", "HalfBathroomCount"),
              authority="grid 'Baths - Full | Half'"),
    Composite(("ViewType", "ViewRangeType"), stack=True,
              authority="grid 'View | Range': a line for each view"),
    Composite(("ProjectName", "SameProjectAsSubjectIndicator"),
              authority="grid 'Project Name | Same Project as Subject'"),
    Composite(("GreenCertificationName", "GreenCertificationLevelName"), stack=True,
              authority="grid 'Building Certification'"),
    Composite(("EfficiencyRatingName", "EfficiencyRatingScoreValue"), stack=True,
              authority="grid 'Efficiency Rating'"),
    Composite(("BodyOfWaterType", "BodyOfWaterName", "WaterAccessDepthType"), stack=True,
              authority="grid 'Water Frontage'"),
    Composite(("CarStorageType", "ParkingSpacesCount", "CarStorageAttachmentType",
               "ImprovedSurfaceMaterialType"), stack=True, tail=("CarStorageAreaMeasure",),
              authority="grid 'Type | Spaces | Detail': facts separated by |, a line for each"),
    Composite(("ProximityToSubjectDistanceLinearMeasure", "ComparableToSubjectDirectionType"),
              sep=" ", authority="grid 'Proximity to Subject': measurement, unit, direction"),
    Composite(("EnvironmentalConditionProximityType", "BodyOfWaterProximityType",
               "SiteInfluenceProximityType", "DistanceFromPropertyLinearMeasure"),
              authority="B-1 4.026 p132: Proximity | Distance and Unit"),
)


def composite_for(names) -> "Composite | None":
    """The composite these data points belong to: two or more of its own."""
    present = {n[:-len("OtherDescription")] if n.endswith("OtherDescription") else n
               for n in names if n}
    for composite in COMPOSITES:
        if len(present & composite.names) >= 2:
            return composite
    return None


# An address is not the sum of its data points in the order A-1 lists them.
# Every sample sets it as the street on one line and "City, ST ZIP" on the
# next, which is how a reader expects to see one; joining the parts in the
# order they are declared prints "Treeville 12345 VA".
ADDRESS_PARTS = {"AddressLineText", "AddressUnitDesignatorType",
                 "AddressUnitIdentifier", "CityName", "StateCode", "PostalCode"}


def _address_text(parts: list[tuple[str, str]]) -> str:
    named = {name: value for name, value in parts if value}
    if not named or not set(named) <= ADDRESS_PARTS or "AddressLineText" not in named:
        return ""
    street = named["AddressLineText"]
    # "Unit", "Apt", "Suite" is the *kind* of unit; without a number after it
    # it says nothing, and printing it produced addresses like "15 S Beechwood
    # Rd Unit" -- which is what the comparable grid showed and what the map
    # then failed to find, because no gazetteer knows that street.  The
    # designator prints only when there is an identifier for it to designate,
    # which is how ``maps._address`` and ``form`` already read it.
    number = named.get("AddressUnitIdentifier")
    if number:
        unit = " ".join(x for x in (named.get("AddressUnitDesignatorType"), number) if x)
        street = f"{street} {unit}"
    town = named.get("CityName", "")
    state = named.get("StateCode", "")
    postal = named.get("PostalCode", "")
    tail = ", ".join(x for x in (town, " ".join(y for y in (state, postal) if y)) if x)
    return chr(10).join(x for x in (street, tail) if x)


NAME_ORDER = ("FirstName", "MiddleName", "LastName", "SuffixName")


def _days_text(parts: list[tuple[str, str]]) -> str:
    """A time given in days, as B-1 26.010 prints it: "a single number followed
    by 'days' (e.g., 45 days) OR two numbers indicating a range with the low and
    high numbers separated by '-' and followed by 'days' (e.g., 30-60 days)"."""
    named = {name: raw for name, raw in parts if name.endswith("DaysCount")}
    if not named or len(named) != len(parts):
        return ""
    low = next((v for n, v in named.items() if "LowRange" in n), "")
    high = next((v for n, v in named.items() if "HighRange" in n), "")
    single = next((v for n, v in named.items() if "Range" not in n), "")
    if low and high:
        return f"{low}-{high} days"
    value = single or high or low
    return f"{value} days" if value else ""


_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _humanise(value: str) -> str:
    """'SiteBuilt' -> 'Site Built'; 'true'/'false' -> 'Yes'/'No'."""
    low = value.strip().lower()
    if low == "true":
        return "Yes"
    if low == "false":
        return "No"
    if value.isupper() or " " in value or not value[:1].isalpha():
        return value
    return _CAMEL.sub(" ", value)


# --------------------------------------------------------------------------
# The page model
# --------------------------------------------------------------------------
# The 29 sections in the order Appendix F-1 "URAR Section Organization" lists
# them.  The number is also the first component of every Report Field ID in
# that section, which is what orders the fields down the page.
SECTIONS = [
    (1, "Summary"), (2, "Assignment Information"), (3, "Subject Property"),
    (4, "Site"), (5, "Disaster Mitigation"),
    (6, "Energy Efficient and Green Features"), (7, "Sketch"),
    (8, "Dwelling Exterior"), (9, "Manufactured Home"), (10, "Unit Interior"),
    (11, "Functional Obsolescence"), (12, "Outbuilding"),
    (13, "Vehicle Storage"), (14, "Subject Property Amenities"),
    (15, "Overall Quality and Condition"), (16, "Highest and Best Use"),
    (17, "Market"), (18, "Project Information"),
    (19, "Subject Listing Information"), (20, "Sales Contract"),
    (21, "Prior Sale and Transfer History"), (22, "Sales Comparison Approach"),
    (23, "Rental Information"), (24, "Income Approach"), (25, "Cost Approach"),
    (26, "Reconciliation"), (27, "Revision History"),
    (28, "Supplemental Information"), (29, "Certifications and Scope of Work"),
]
SECTION_NAME = dict(SECTIONS)
TAB_NAME = {29: "Certifications"}          # the tab is shorter than the section

# A label written with a placeholder -- "Client/[Party Role Type]" -- prints
# with the placeholder resolved, so it is matched with the bracketed part
# treated as a wildcard.
PLACEHOLDER = re.compile(r"\[[^\]]+\]")


def _sort_key(field_id: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in field_id.split("."))


@lru_cache(maxsize=1)
def _layout_positions() -> dict[tuple[str, str], dict]:
    """Column and indent for a label, from two sources.

    The twelve samples are the stronger evidence, because they are the form as
    rendered -- but they only show the fields those twelve cases happen to
    exercise.  Appendix C-1's layout covers the rest, stating which column each
    label sits in without the indent.  Samples first, C-1 to fill the gaps.
    """
    out: dict[tuple[str, str], dict] = {}

    path = SPEC / "page_layout.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        for section, fields in data.get("sections", {}).items():
            for f in fields:
                key = (section.casefold(), f["label"].casefold())
                out.setdefault(key, {
                    "column": f["column"], "indent": f["indent"],
                    "order": f["order"], "kind": f["kind"],
                    "seen_in": f.get("seen_in", []), "source": "D-1 samples"})

    c1 = SPEC / "layout.json"
    if c1.exists():
        data = json.loads(c1.read_text(encoding="utf-8"))
        for section, block in data.items():
            for label, side in (block.get("columns") or {}).items():
                key = (section.casefold(), label.casefold())
                out.setdefault(key, {
                    "column": 1 if str(side).lower().startswith("r") else 0,
                    "indent": 0, "order": 10_000, "kind": "label",
                    "seen_in": [], "source": "C-1 URAR Layout"})
    return out


def _same_section(a: str, b: str) -> bool:
    """Do these name the same section?

    A tab is sometimes shorter than the section it opens -- section 29 prints
    "Certifications" for "Certifications and Scope of Work" -- so one name
    being the start of the other counts as a match.
    """
    x, y = a.casefold().strip(), b.casefold().strip()
    return x == y or x.startswith(y) or y.startswith(x)


def _position(section: str, label: str) -> dict:
    """Where this label sits, matching a placeholder label loosely."""
    table = _layout_positions()
    names = [section] + [n for n in TAB_NAME.values() if _same_section(n, section)]
    for name in names:
        exact = table.get((name.casefold(), label.casefold()))
        if exact:
            return exact
    if PLACEHOLDER.search(label):
        pattern = re.compile(
            "^" + PLACEHOLDER.sub(r"[^/]+", re.escape(label)
                                  .replace(r"\[", "[").replace(r"\]", "]")) + "$",
            re.I)
        for (sec, lab), spot in table.items():
            if any(_same_section(sec, n) for n in names) and pattern.match(lab):
                return spot
    return {"column": 0, "indent": 0, "order": 10_000, "kind": "label",
            "seen_in": []}


@dataclass
class PageField:
    field_id: str
    label: str
    section: str
    subsection: str
    column: int
    indent: int
    binding: Binding
    ordinal: int = 1          # which repeat of a block this field belongs to

    @property
    def section_number(self) -> int:
        return int(self.field_id.split(".")[0])

    @property
    def group(self) -> str:
        """The repeating block this field belongs to, if any."""
        for dp in self.binding.data_points:
            container = repeating_container(dp.get("xpath", ""))
            if container:
                return f"{self.subsection}|{container}"
        return ""


@lru_cache(maxsize=1)
def page_model() -> dict[int, list[PageField]]:
    """Every field the specification places on the page, section by section.

    The field list and its order come from A-1: a Report Field ID names its
    section in its first component and its position in the rest, so sorting the
    identifiers reproduces the order they are printed in.  Column and indent
    come from the measured samples, because A-1 does not state them.
    """
    index = _index()
    out: dict[int, list[PageField]] = {n: [] for n, _name in SECTIONS}
    seen: set[tuple[int, str]] = set()
    for fid, entry in index.items():
        head = fid.split(".")[0]
        if not head.isdigit():
            continue
        number = int(head)
        if number not in out:
            continue
        for place in entry.get("locations", []):
            label = place.get("label", "")
            if not label or label == NO_LABEL:
                continue
            if (number, fid) in seen:
                continue
            section = SECTION_NAME[number]
            if not _same_section(place["section"], section):
                continue
            seen.add((number, fid))
            spot = _position(section, label)
            out[number].append(PageField(
                field_id=fid, label=label, section=section,
                subsection=place.get("subsection", ""),
                column=spot["column"], indent=spot["indent"],
                binding=Binding(
                    field_id=fid, section=section,
                    subsection=place.get("subsection", ""), label=label,
                    data_points=entry.get("data_points", []),
                    display_rules=entry.get("display_rules", []),
                ),
            ))
    for number in out:
        out[number].sort(key=lambda f: _sort_key(f.field_id))
        _number_repeats(out[number])
    return out


def _number_repeats(fields: list[PageField]) -> None:
    """Give each repeat of a block its ordinal.

    A-1 lays a repeating block out as consecutive runs of the same labels --
    Feature, Location, Description, then Feature, Location, Description again
    -- one run per instance the report may hold.  Seeing a label for the second
    time in the same block therefore opens the second instance.
    """
    seen: dict[tuple[str, str], int] = {}
    for f in fields:
        group = f.group
        if not group:
            continue
        # A field A-1 conditions on its own type value ('IF PartyRoleType =
        # "AppraiserSupervisor"') is its own instance, told apart by that
        # value, not the second run of the appraiser's block.
        marks = tuple(sorted({(k, v) for dp in f.binding.data_points
                              for k, v in (dp.get("requires") or {}).items()
                              if k.endswith("Type") and not k.startswith("__")}))
        # Fields whose A-1 paths differ are not repeats of each other: the
        # reason the cost approach was excluded and the reason the income
        # approach was excluded share a label and a container name, but sit
        # in COST_APPROACH and INCOME_APPROACH.  Numbering them 1, 2, 3 made
        # the second and third unwritable once the path itself told them
        # apart, because there is only ever one of each on its own path.
        where = tuple(sorted({dp.get("xpath", "") for dp in f.binding.data_points}))
        key = (group, f.label.casefold(), marks, where)
        seen[key] = seen.get(key, 0) + 1
        f.ordinal = seen[key]


def main() -> None:
    locs = locations()
    labels = by_label()
    print(f"{len(locs)} display locations parsed from A-1 Report Location")
    print(f"{len(labels)} distinct (section, label) pairs")
    sections: dict[str, int] = {}
    for loc in locs:
        sections[loc.section] = sections.get(loc.section, 0) + 1
    print(f"{len(sections)} sections named\n")
    layout = json.loads((SPEC / "page_layout.json").read_text(encoding="utf-8"))
    total = matched = 0
    for section, fields in layout["sections"].items():
        for f in fields:
            if f["kind"] == "heading":
                continue
            total += 1
            if lookup(section, f["label"], f["subsection"]):
                matched += 1
    print(f"page labels bound to a field: {matched}/{total} "
          f"({100 * matched / max(total, 1):.0f}%)")


if __name__ == "__main__":
    main()
