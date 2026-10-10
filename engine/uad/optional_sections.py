"""Optional sections: leave one out of the report, keep what was entered in
it, bring it back (T-1057; WinTOTAL's Show / Hide).

B-1 decides when three sections print, by a question each asks itself:

* Disaster Mitigation -- when the Mitigation Feature (5.000) is a value
  other than 'None';
* Energy Efficient and Green Features -- when one of its three "exists"
  questions (6.000, 6.004, 6.010) is true;
* Sales Contract -- when a sales contract exists (20.000).

(``form.switch_fields`` reads these from B-1's own sentences.)  So leaving a
section out *is* answering that question the way that switches it off, and the
official samples show what the delivered file then holds: the question, and
nothing else of the section (D-1 Condo1, MH1, SF5).  Whatever else had been
entered -- a contract date beside "no contract", a certification beside "no
certification" -- is moved out of the MISMO document into ``hidden.json`` in
the case folder (it travels in the case bundle, never in the package), and is
put back, where the XSD orders it, when the section is switched on again:
by the side panel's switch, or by answering the question itself.

Revision History is not one of them: it prints whenever a revision is
recorded, and a revised report cannot hold its revisions back (H-1
UAD1750-1754 require them once ReconsiderationOfValueIndicator is true).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

from . import bind, edit
from .report import form

FILE = "hidden.json"
M = f"{{{bind.MISMO}}}"


def sections() -> list[str]:
    return form.switch_sections()


def section_of(field_id: str) -> str:
    """The optional section a Report Field ID switches, or ''."""
    return next((s for s in sections() if field_id in form.switch_fields(s)), "")


def _number(section: str) -> int:
    return next(n for n, name in bind.SECTIONS if name == section)


# ------------------------------------------------------------ what it holds
def _points(section: str) -> list[tuple[str, dict]]:
    number = str(_number(section))
    return [(fid, dp) for fid, entry in form._fields().items()
            if fid.split(".")[0] == number and fid.count(".") == 1
            for dp in entry.get("data_points") or [] if dp.get("mismo")]


def _asks(section: str) -> set[str]:
    """The data point names of the question(s) that switch it."""
    return set(form.switch_points(section))


def _anchor(root, dp: dict):
    xpath = dp.get("xpath", "")
    if "PROPERTIES/PROPERTY/" in xpath:
        return bind.subject(root), xpath.split("PROPERTIES/PROPERTY/", 1)[1]
    if "VALUATION_REPORT/" in xpath:
        return root.find(f".//{M}VALUATION_REPORT"), xpath.split("VALUATION_REPORT/", 1)[1]
    return None, ""


def _anchors(root) -> list:
    return [a for a in (bind.subject(root), root.find(f".//{M}VALUATION_REPORT")) if a is not None]


def _leaves(node) -> list:
    return [e for e in node.iter() if isinstance(e.tag, str) and not len(e)]


def _found(root, section: str, *, asks: bool) -> list:
    """The elements holding the section's answers: its question(s) when
    ``asks``, everything else otherwise -- each lifted to the largest
    container that holds nothing else (a whole certification, not its five
    leaves; never the container that also holds the question)."""
    question = _asks(section)
    own = {dp["mismo"] for _fid, dp in _points(section)}
    movable = question if asks else own - question
    hits = []
    for fid, dp in _points(section):
        if (dp["mismo"] in question) != asks:
            continue
        if bind.is_commentary(dp):
            category = (dp.get("requires") or {}).get("ValuationAnalysisCategoryType") \
                or bind.commentary_category(fid)
            hits += [c for c in root.iter(f"{M}VALUATION_COMMENTARY")
                     if (c.findtext(f"{M}ValuationAnalysisCategoryType") or "") == category]
            continue
        anchor, tail = _anchor(root, dp)
        if anchor is None:
            continue
        steps = [t for t in tail.split("/") if t] + [dp["mismo"]]
        hits += anchor.findall("./" + "/".join(f"{M}{t}" for t in steps))
    if not asks:
        # the section's exhibits written into the document (A-1 ...Exhibit)
        cats = {c for c, (sec, _cap) in form.image_categories().items() if sec == section}
        subject = bind.subject(root)
        if subject is not None and cats:
            hits += [i for i in subject.iter(f"{M}IMAGE")
                     if (i.findtext(f"{M}ImageCategoryType") or "") in cats]
    anchors = _anchors(root)
    units = []
    for node in hits:
        while True:
            parent = node.getparent()
            if parent is None or any(parent is a for a in anchors) or etree.QName(parent).localname in (
                    "VALUATION_COMMENTARIES", "IMAGES"):
                break
            names = {etree.QName(e).localname for e in _leaves(parent)}
            if not names <= movable:
                break
            node = parent
        if not any(node is u for u in units):
            units.append(node)
    # an element inside another unit goes with it
    return [u for u in units if not any(v is not u and u in v.iterancestors() for v in units)]


# ------------------------------------------------------------ moving it out
def _record(node, anchors) -> dict:
    parent = node.getparent()
    anchor = next(a for a in anchors if a is parent or a in parent.iterancestors()) \
        if any(a is parent or a in parent.iterancestors() for a in anchors) else None
    chain = []
    up = parent
    while up is not None and up is not anchor:
        chain.insert(0, etree.QName(up).localname)
        up = up.getparent()
    tag = etree.QName(node).localname
    same = [s for s in parent if isinstance(s.tag, str) and etree.QName(s).localname == tag]
    return {"anchor": "subject" if anchor is not None and etree.QName(anchor).localname == "PROPERTY"
            else "report",
            "chain": chain, "parent": bind.stable_path(parent),
            "index": next(i for i, s in enumerate(same, 1) if s is node),
            "xml": etree.tostring(node, with_tail=False).decode("utf-8")}


def _take(root, nodes) -> list[dict]:
    anchors = _anchors(root)
    body = list(root.iter())
    ordered = sorted(nodes, key=lambda n: body.index(n))         # document order
    records = [_record(n, anchors) for n in ordered]
    for n in ordered:
        parent = n.getparent()
        parent.remove(n)
        # a container left empty goes too (an empty VALUATION_COMMENTARIES is
        # not the samples' shape); the record's chain rebuilds it
        while parent is not None and not len(parent) and not any(parent is a for a in anchors) \
                and not (parent.text or "").strip():
            up = parent.getparent()
            up.remove(parent)
            parent = up
    return records


def _put(root, rec: dict) -> None:
    node = etree.fromstring(rec["xml"].encode("utf-8"))
    tag = etree.QName(node).localname
    parent = bind.find_path(root, rec["parent"])
    want = rec["chain"][-1] if rec["chain"] else ("PROPERTY" if rec["anchor"] == "subject"
                                                   else "VALUATION_REPORT")
    if parent is None or etree.QName(parent).localname != want:
        parent = bind.subject(root) if rec["anchor"] == "subject" else root.find(f".//{M}VALUATION_REPORT")
        for step in rec["chain"]:
            parent = parent.find(f"{M}{step}") if parent.find(f"{M}{step}") is not None \
                else edit._insert_ordered(parent, step)
    same = [s for s in parent if isinstance(s.tag, str) and etree.QName(s).localname == tag]
    if same and rec["index"] <= len(same):
        same[rec["index"] - 1].addprevious(node)
    elif same:
        same[-1].addnext(node)
    else:
        holder = edit._insert_ordered(parent, tag)                 # the XSD's place for it
        holder.addprevious(node)
        parent.remove(holder)


# ------------------------------------------------------------ the stash file
def load(folder: Path | None) -> dict:
    path = Path(folder) / FILE if folder else None
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("sections", {})
    except ValueError:
        return {}


def save(folder: Path, kept: dict) -> None:
    path = Path(folder) / FILE
    kept = {k: v for k, v in kept.items() if v.get("units") or v.get("asked")}
    if not kept:
        if path.exists():
            path.unlink()
        return
    path.write_text(json.dumps({"format": "uad36-hidden-sections/1", "sections": kept}, indent=1),
                    encoding="utf-8")


def _answered(entry: dict) -> int:
    return sum(len([e for e in _leaves(etree.fromstring(r["xml"].encode("utf-8")))
                    if (e.text or "").strip()]) for r in entry.get("units", []))


# ------------------------------------------------------------ the switch
def _hide_value(section: str) -> str:
    """The answer that switches it off: B-1's "a value other than 'None'"
    gives 'None'; an indicator that must be "true" is answered "false"."""
    m = re.search(r"other than\s*[‘'\"]([A-Za-z]+)[’'\"]", form.switch_rule(section))
    return m.group(1) if m else "false"


def _clear(root, section: str) -> None:
    for node in _found(root, section, asks=True):
        node.getparent().remove(node)


def _answer(tree, section: str, values: dict[str, list[str]]) -> None:
    root = tree.getroot()
    _clear(root, section)
    for fid in form.switch_fields(section):
        for n, value in enumerate(values.get(fid) or [], start=1):
            edit.write(tree, fid, value, ordinal=n)


def _current(root, section: str) -> dict[str, list[str]]:
    out = {}
    for fid in form.switch_fields(section):
        name = next(dp["mismo"] for f, dp in _points(section)
                    if f == fid and dp["mismo"] in form.switch_points(section))
        subject = bind.subject(root)
        out[fid] = [(e.text or "").strip() for e in (subject.iter(f"{M}{name}") if subject is not None else [])
                    if (e.text or "").strip()]
    return out


def follow(tree, section: str, kept: dict) -> bool:
    """After the switching question changed: a section B-1 now leaves out
    has its other answers moved aside; one it prints again gets them back.
    True when the document changed."""
    root = tree.getroot()
    entry = kept.get(section) or {}
    if not form.section_prints(root, section):
        nodes = _found(root, section, asks=False)
        if not nodes:
            return False
        records = _take(root, nodes)
        kept[section] = {**entry, "units": entry.get("units", []) + records,
                         "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        return True
    if not entry.get("units"):
        kept.pop(section, None)
        return False
    for rec in entry["units"]:
        _put(root, rec)
    kept.pop(section, None)
    return True


def set_shown(tree, section: str, on: bool, kept: dict) -> None:
    """The side panel's switch.  Off: the question is answered the way that
    leaves the section out (its earlier answers remembered), and the rest is
    moved aside.  On: the earlier answers come back -- or, with none
    remembered, a single yes/no question is answered yes and a choice is left
    open to be made -- and so does the rest."""
    if section not in sections():
        raise ValueError(f"{section} is not a section the report can leave out")
    root = tree.getroot()
    if not on:
        if not form.section_prints(root, section):
            follow(tree, section, kept)
            return
        before = _current(root, section)
        entry = kept.get(section) or {}
        # the rest first: clearing the question removes whatever container
        # holds nothing else, and by then that is only the question
        records = _take(root, _found(root, section, asks=False))
        _answer(tree, section, {fid: [_hide_value(section)] for fid in form.switch_fields(section)})
        kept[section] = {"asked": before, "units": entry.get("units", []) + records,
                         "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        return
    entry = kept.get(section) or {}
    asked = entry.get("asked")
    if asked:
        _answer(tree, section, asked)
    else:
        fids = form.switch_fields(section)
        _answer(tree, section, {fids[0]: ["true"]} if len(fids) == 1 and _hide_value(section) == "false"
                else {})
    follow(tree, section, kept)


def state(root, kept: dict, media: list | None = None) -> list[dict]:
    """Each optional section: does it print, what B-1 says, what is kept."""
    out = []
    for section in sections():
        number = _number(section)
        entry = kept.get(section) or {}
        out.append({"section": section, "number": number,
                    "printed": form.section_prints(root, section),
                    "rule": form.switch_rule(section),
                    "fields": list(form.switch_fields(section)),
                    "kept": _answered(entry),
                    "exhibits": sum(1 for m in media or []
                                    if int(getattr(m, "section", 0) or 0) == number)})
    return out
