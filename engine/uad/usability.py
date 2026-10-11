"""B-1's Usability supplement, the checks it states exactly (T-909, T-910).

Appendix B-1's "Supplement - Usability and Implementation Guidance" asks the
software to alert the appraiser -- "to alert the appraiser and confirm
information is entered accurately" -- where the report contradicts itself or
leans on an addendum.  None of it is an H-1 rule, so it never blocks a
signature: each finding is a Warning in the Review Master, on the field that
fixes it.

``addendum``   item 6: a field that says "See attached addendum", "See
               Addenda" or a variation, where a discrete data field should
               carry the information;
``as_is``      item 10, example 1: a defect whose Recommended Action is
               Completion, Inspection or Repair, and a Market Value Condition
               of "As Is" (H-1 checks the other direction only: UAD1624,
               UAD1732);
``rating``     item 10, example 2: an Overall Condition of "C1" the data
               under it does not support -- not new construction, a kitchen
               or bathroom not "New or Like New" and "Fully Updated".

What each check reads is ``spec/usability.json``, extracted from the
supplement by ``uad/spec/extract_usability.py``.  All twelve D-1 samples pass
every check (tests/test_usability.py).  Item 9 -- prohibited or veiled
language -- cites the GSE Selling Guides, which are not in the repository, so
it is not checked rather than checked against an invented word list.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from lxml import etree

from . import bind

SPEC = Path(__file__).resolve().parents[1] / "spec"
M = f"{{{bind.MISMO}}}"
WARNING = "Warning"


@dataclass
class Finding:
    code: str                  # U6, U10.1, U10.2 -- the supplement's item and example
    message: str
    field_id: str = ""
    path: str = ""
    detail: str = ""


@lru_cache(maxsize=1)
def spec() -> dict:
    return json.loads((SPEC / "usability.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _index() -> dict:
    return json.loads((SPEC / "field_index.json").read_text(encoding="utf-8"))["fields"]


def _label(fid: str) -> str:
    loc = (_index().get(fid, {}).get("locations") or [{}])[0]
    label = loc.get("label", "")
    return (label if label not in ("", bind.NO_LABEL) else loc.get("subsection")) or fid


@lru_cache(maxsize=512)
def _texts(fid: str) -> dict[str, str]:
    dps = _index().get(fid, {}).get("data_points") or []
    return bind.enumeration_texts(dps[0], fid) if dps else {}


def _shown(fid: str, value: str) -> str:
    return _texts(fid).get(value) or value


def _local(node) -> str:
    return etree.QName(node).localname


@lru_cache(maxsize=1)
def _owners() -> dict[str, tuple[tuple[str, tuple[str, ...]], ...]]:
    """data point -> (field, container path) for each field that carries it."""
    out: dict[str, list] = {}
    for fid, entry in _index().items():
        for dp in entry.get("data_points") or []:
            out.setdefault(dp.get("mismo", ""), []).append((fid, tuple(bind._tail(dp.get("xpath", "")))))
    return {n: tuple(v) for n, v in out.items()}


def field_of(node) -> str:
    """The field an element is entered in: the one whose A-1 path it sits at,
    a commentary by its category, the Summary's redisplay last."""
    hits = [f for f, path in _owners().get(_local(node), ()) if bind._matches(node, list(path))]
    if len(hits) > 1:
        cat = node.getparent().findtext(f"{M}ValuationAnalysisCategoryType") if node.getparent() is not None else None
        if cat:
            hits = [f for f in hits if bind.commentary_category(f) == cat] or hits
    hits.sort(key=lambda f: (f.startswith("1."), [int(p) if p.isdigit() else 0 for p in f.split(".")]))
    return hits[0] if hits else ""


def _is_urar(root) -> bool:
    from . import report_types
    return report_types.kind_of(root) == report_types.URAR


# ------------------------------------------------------------------ item 6
def addendum(root) -> list[Finding]:
    rule = spec()["addendum"]
    pat = re.compile(rule["pattern"], re.I)
    out = []
    for node in root.iter():
        if not isinstance(node.tag, str) or len(node) or not node.text:
            continue
        m = pat.search(node.text)
        if not m:
            continue
        fid = field_of(node)
        out.append(Finding(
            code="U6", field_id=fid, path=bind.stable_path(node),
            message=(f"{_label(fid) if fid else _local(node)} says “{m.group(0)}”: "
                     "put the information in the report's own fields and commentary"),
            detail=f"B-1 Usability item 6: {rule['text']}"))
    return out


# ------------------------------------------------------------ item 10, ex. 1
def as_is(root) -> list[Finding]:
    rule = spec()["as_is"]
    subject = bind.subject(root)
    if subject is None:
        return []
    acting = [n for n in subject.iter(M + rule["action_point"]) if (n.text or "").strip() in rule["actions"]]
    concl = [n for n in root.iter(M + rule["condition_point"]) if (n.text or "").strip() == rule["not"]]
    if not acting or not concl:
        return []
    fid = rule["condition_fids"][0]
    actions = sorted({n.text.strip() for n in acting})
    where = sorted({_label_section(field_of(n)) for n in acting} - {""})
    return [Finding(
        code="U10.1", field_id=fid, path=bind.stable_path(concl[0]),
        message=(f"{_label(fid)} is “{_shown(fid, rule['not'])}”, but "
                 f"{len(acting)} defect(s) call for {', '.join(actions)}"
                 + (f" ({', '.join(where)})" if where else "")
                 + ": the value is subject to that action, not as is"),
        detail=f"B-1 Usability item 10, example 1: {rule['text']}")]


def _label_section(fid: str) -> str:
    loc = (_index().get(fid, {}).get("locations") or [{}])[0]
    return loc.get("section", "")


# ------------------------------------------------------------ item 10, ex. 2
def _dwellings(subject):
    for imp in subject.iter(M + "IMPROVEMENT"):
        if imp.findtext(f"{M}IMPROVEMENT_DETAIL/{M}ImprovementType") == "Dwelling":
            yield imp


def rating(root) -> list[Finding]:
    subject = bind.subject(root)
    if subject is None:
        return []
    out = []
    for rule in spec()["ratings"]:
        given = [n.text.strip() for n in subject.iter(M + rule["rating_point"]) if (n.text or "").strip()]
        if rule["rating"] not in given:
            continue
        head = f"{_label(rule['rating_fid'])} is “{rule['rating']}”"
        for need in rule["requires"]:
            fid, want = need["fid"], need["value"]
            if need["rooms"]:
                nodes = [n for imp in _dwellings(subject) for d in imp.iter(M + "ROOM_DETAIL")
                         if d.findtext(M + "RoomType") in need["rooms"]
                         for n in d.findall(M + need["point"])]
            elif any(need["point"] in {_local(e) for e in imp.iter()} for imp in _dwellings(subject)):
                nodes = [n for imp in _dwellings(subject) for n in imp.iter(M + need["point"])]
            else:
                nodes = [n for n in subject.iter(M + need["point"])
                         if not any(_local(a) == "IMPROVEMENT" for a in n.iterancestors())]
            for n in nodes:
                have = (n.text or "").strip()
                if not have or have == want:
                    continue            # an empty one is H-1's to require, not this
                room = n.getparent().findtext(M + "RoomType") if need["rooms"] else ""
                out.append(Finding(
                    code="U10.2", field_id=fid, path=bind.stable_path(n),
                    message=(f"{head}, but {_label(fid)}"
                             + (f" ({_shown_room(room)})" if room else "")
                             + f" is “{_shown(fid, have)}”: {rule['rating']} needs "
                             f"“{_shown(fid, want)}”"),
                    detail=f"B-1 Usability item 10, example 2: {rule['text']}"))
    return out


@lru_cache(maxsize=64)
def _shown_room(value: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)


def check(tree) -> list[Finding]:
    """Every usability finding on the document, in the supplement's order."""
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    if not _is_urar(root):
        return []                 # the supplement is B-1's, for the URAR
    return addendum(root) + as_is(root) + rating(root)
