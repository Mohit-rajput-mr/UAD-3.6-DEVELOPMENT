"""Fill a report the way an appraiser would, one control at a time.

The editor draws the report itself, so every place a value can go is already
on the page: a ``data-fid`` with a list (``pick``), a tick box (``bx``), a
typed value (``contenteditable``), a table cell (``data-tf``) that writes into
the row it prints in, or a comparable-grid cell (``data-gf``).  This module
reads those controls out of the editor's own markup, matches each to a value
from the case being brought in, and returns them **in report order** as a list
of steps.

Two things then happen at once.  The server applies the steps to the document
in one pass -- one parse, one save -- so the case is correct as quickly as the
machine can make it.  The page replays the same list visually: it opens each
section, moves to the field, opens the list and picks the value, ticks the
box, types the text, adds the row a value needs and drops the photograph in.
The visual pass is a mirror of the write, never a substitute for it, and when
the writing finishes the form is reloaded from the server, so what the
appraiser ends up looking at is the saved document.

Where the values come from: the source is another case -- for now one of the
D-1 samples, later the case an intake builds from an order sheet, an MLS
export and a folder of photographs.  A value is matched to its control by the
address of the instance it sits in (``SITE_UTILITY[2]``, ``PROPERTY[3]``), so
a value in the second utility row of the source lands in the second utility
row here, and nowhere else.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field as _field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable

from lxml import etree, html as lhtml

ENGINE = Path(__file__).resolve().parents[1]
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from uad import bind, edit, parties  # noqa: E402
from uad.report import comparables, form  # noqa: E402

M = f"{{{bind.MISMO}}}"
XLINK = "http://www.w3.org/1999/xlink"

# The Summary is a redisplay of the rest of the report (B-1 chapter 01), so it
# is never filled; it follows from what the other sections are given.
SKIP_SECTIONS = {1}

# A step of each kind is drawn differently on the page.
PICK, CHECK, TEXT, CELL, COMP, GRID, PHOTO, DATA, LINK = (
    "pick", "check", "text", "cell", "comp", "grid", "photo", "data", "link")

# An element address is "{namespace}TAG[2]/{namespace}TAG": the namespace is a
# URL and has slashes of its own, so the steps are matched rather than split.
SEGMENT = re.compile(r"(?:\{[^}]*\})?([\w.-]+)(?:\[(\d+)\])?")


@dataclass
class Step:
    n: int
    secn: int
    section: str
    label: str
    fid: str
    kind: str
    value: str                # what is written
    display: str              # what the page shows once it is written
    data_point: str = ""
    path: str = ""            # the instance the value belongs in
    row_label: str = ""       # the row a table cell prints on
    column: int = -1          # a grid column: 0 the subject, 1.. a comparable
    adjust: str = ""          # a grid adjustment's ComparableAdjustmentType
    comp_kind: str = ""       # sales | rental | grm, for a comparable
    media: dict = _field(default_factory=dict)
    attrs: dict = _field(default_factory=dict)
    # A field can be made of several data points -- a name is a first and a
    # last, an address is six -- and the page shows them as one value.  The
    # step stays one step so the filling reads as one action, and carries
    # every write it is made of.
    writes: list[dict] = _field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return self.__dict__.copy()


# --------------------------------------------------------------- the controls
def controls(tree: etree._ElementTree, folder: Path | None = None) -> list[dict]:
    """Every control the editor draws, in the order the report prints them."""
    blocks = form.build(tree, folder=folder, edit=True)
    doc = lhtml.fromstring(form.galley_html(blocks, edit=True))
    section_of: dict[Any, tuple[int, str]] = {}
    for mark in doc.iter():
        if not isinstance(mark.tag, str):
            continue
        name = mark.get("data-section")
        if name:
            pair = (form.section_number(name), name)
            for node in mark.iter():
                section_of[node] = pair
    out: list[dict] = []
    row_label = ""
    for el in doc.iter():
        if not isinstance(el.tag, str):
            continue
        if el.tag == "tr":
            first = el.find("td")
            row_label = (first.text_content() or "").strip() if first is not None else ""
        classes = (el.get("class") or "").split()
        fid, tf, gf = el.get("data-fid"), el.get("data-tf"), el.get("data-gf")
        ga, gaf = el.get("data-ga"), el.get("data-gaf")
        kind = ""
        if gf or (ga and gaf):
            kind = GRID
        elif tf is not None:
            kind = CELL
        elif fid:
            if "pick" in classes:
                kind = PICK
            elif "bx" in classes:
                kind = CHECK
            elif el.get("contenteditable") == "true":
                kind = TEXT
        if not kind:
            continue
        section = section_of.get(el, (0, ""))
        out.append({
            "fid": gf or gaf or tf or fid,
            "kind": kind,
            "secn": section[0], "section": section[1],
            "pick": el.get("data-pick") or "",
            "key": el.get("data-tk") or "",
            "data_point": el.get("data-tdp") or "",
            "sel": el.get("data-tsel") or "",
            "row_label": el.get("data-tlab") or row_label,
            "cat": el.get("data-tcat") or "",
            "column": int(el.get("data-gc") or -1),
            "adjust": ga or "",
            "text": (el.text_content() or "").strip(),
        })
    return out


# ------------------------------------------------------------- reading values
def _label(fid: str) -> str:
    b = bind.binding_for(fid)
    return b.label if b else ""


def _read(root: etree._Element, fid: str, data_point: str = "",
          scope: etree._Element | None = None) -> tuple[list[dict], str]:
    """What a source document holds for a field: the writes, and what prints."""
    binding = bind.binding_for(fid)
    if binding is None:
        return [], ""
    groups = bind.read_groups(root, binding, scope, ordinal=1)
    parts = [p for g in groups[:1] for p in g]        # the first instance
    if data_point:
        parts = [p for p in parts if p[0] == data_point]
    if not parts:
        return [], ""
    writes = [{"data_point": name, "value": value} for name, value in parts]
    return writes, bind.display_value([parts], binding)


def _in_instance(node: etree._Element, fid: str, data_point: str
                 ) -> tuple[list[dict], str]:
    """A table cell: the values inside the row's own instance."""
    binding = bind.binding_for(fid)
    if binding is None:
        return [], ""
    parts: list[tuple[str, str]] = []
    names = {dp.get("mismo") for dp in binding.data_points if dp.get("mismo")}
    for child in node.iter():
        if not isinstance(child.tag, str):
            continue
        name = etree.QName(child).localname
        if name not in names or not (child.text or "").strip():
            continue
        if data_point and name != data_point:
            continue
        if (name, child.text.strip()) not in parts:
            parts.append((name, child.text.strip()))
    if not parts:
        return [], ""
    return ([{"data_point": n, "value": v} for n, v in parts],
            bind.display_value([parts], binding))


def _party_name(source: etree._Element, fid: str) -> str:
    """Every name this party field shows, as the report prints them."""
    binding = bind.binding_for(fid)
    if binding is None:
        return ""
    return bind.display_value(bind.read_groups(source, binding, ordinal=1), binding)


# ------------------------------------------------------------------ the plan
# Filling is not a list of the boxes the editor happens to draw: it is every
# value the case holds, each one entered where it belongs.  So the plan walks
# the source document itself -- every value, with the address of the element
# it sits in -- and uses the editor's controls only to know how that value is
# entered on the page: from a list, by a tick, typed, or into a table row.


@lru_cache(maxsize=1)
def _points() -> dict[str, list[tuple[str, tuple[str, ...]]]]:
    """MISMO data point name -> the Report Field IDs that name it, and where."""
    index = json.loads((ENGINE / "spec" / "field_index.json").read_text(
        encoding="utf-8"))["fields"]
    out: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    for fid, entry in index.items():
        for dp in entry.get("data_points") or []:
            name = dp.get("mismo")
            if not name or dp.get("attribute"):
                continue
            out.setdefault(name, []).append((fid, tuple(bind._tail(dp.get("xpath", "")))))
    return out


def _ancestry(node: etree._Element) -> list[str]:
    return [etree.QName(a).localname for a in reversed(list(node.iterancestors()))]


def _field_of(node: etree._Element) -> str:
    """The Report Field ID whose A-1 path matches where this value sits.

    The same data point name appears in several places -- AddressLineText is
    the subject's, a comparable's, the appraiser's -- and the one that applies
    is the one whose container path the element actually sits under.
    """
    name = etree.QName(node).localname
    here = _ancestry(node)
    best, score = "", -1
    for fid, tail in _points().get(name, ()):  # noqa: B007
        n = 0
        for a, b in zip(reversed(here), reversed(tail)):
            if a != b:
                break
            n += 1
        if n > score:
            best, score = fid, n
    return best if score > 0 else ""


def _field_of_outside_summary(node: etree._Element) -> str:
    """The same match, ignoring the Summary's own redisplay fields."""
    name = etree.QName(node).localname
    here = _ancestry(node)
    best, score = "", -1
    for fid, tail in _points().get(name, ()):
        if fid.split(".")[0] == "1":
            continue
        n = 0
        for a, b in zip(reversed(here), reversed(tail)):
            if a != b:
                break
            n += 1
        if n > score:
            best, score = fid, n
    return best if score > 0 else ""


def plan(target: etree._ElementTree, source: etree._Element,
         folder: Path | None = None, source_folder: Path | None = None,
         media: Iterable[Any] = ()) -> list[Step]:
    """Every value this case brings, as the steps that enter it."""
    root = target.getroot() if hasattr(target, "getroot") else target
    drawn = {}
    for c in controls(source.getroottree(), folder=source_folder):
        drawn.setdefault(c["fid"], c)
    tree = source.getroottree()
    names = dict(bind.SECTIONS)

    # keyed by address, never by id(): lxml makes a fresh proxy on each access,
    # so an element's id() is not the same twice and neither is "is"
    comps: dict[str, tuple[str, int]] = {}      # PROPERTY -> (kind, column)
    steps: list[Step] = []
    for kind, (_sheet, role, _section) in comparables.SHEETS.items():
        if kind == "not_used":
            continue
        for number, prop in enumerate(comparables.properties(source, role), start=1):
            comps[tree.getelementpath(prop)] = (kind, number)

    subject = bind.subject(source)
    subject_path = tree.getelementpath(subject) if subject is not None else ""
    have = {kind: len(comparables.properties(root, comparables.SHEETS[kind][1]))
            for kind in comparables.SHEETS if kind != "not_used"}
    added: set[tuple[str, int]] = set()
    secn, section = 0, ""
    for node in source.iter():
        if not isinstance(node.tag, str) or len(node) or not (node.text or "").strip():
            continue
        name = etree.QName(node).localname
        value = node.text.strip()
        fid = _field_of(node)
        if fid.split(".")[0] == "1":
            # The Summary redisplays the rest of the report (B-1 chapter 01).
            # A value that matched a Summary field is not a Summary value --
            # the subject's address is the Summary's *source* -- so it is
            # still entered; only the field label is taken from elsewhere.
            fid = _field_of_outside_summary(node) or fid
        control = drawn.get(fid, {})
        # Which section the value is entered in: the section the editor draws
        # its control in, else the section A-1 locates the field in.  A value
        # A-1 does not locate (an image's MIME type) belongs with the value
        # before it, which is the block it sits in.
        if control.get("secn"):
            secn, section = control["secn"], control["section"]
        elif fid:
            b = bind.binding_for(fid)
            number = form.SECTION_NUMBER.get(b.section if b else "", 0)
            if number:
                secn, section = number, (b.section if b else "")
        # which property this value belongs to, if any
        column, comp_kind = -1, ""
        for ancestor in node.iterancestors():
            if etree.QName(ancestor).localname != "PROPERTY":
                continue
            here = tree.getelementpath(ancestor)
            if here in comps:
                comp_kind, column = comps[here]
            elif here == subject_path:
                column = 0            # the grid's subject column
            break
        if column > 0 and (comp_kind, column) not in added:
            added.add((comp_kind, column))
            if column > have.get(comp_kind, 0):
                steps.append(Step(n=0, secn=secn, section=section,
                                  label=f"Comparable #{column}", fid="", kind=COMP,
                                  value=str(column), display=f"Comparable #{column}",
                                  comp_kind=comp_kind, column=column))
        kind = control.get("kind") or DATA
        if kind == CHECK and control.get("pick") and control["pick"] != value:
            kind = DATA                   # a run of boxes: this is not that box
        if kind == GRID and column < 0:
            # the grid shows a column per property; a value that belongs to no
            # property is entered in its section rather than in the grid
            kind = CELL if control.get("key") else DATA
        steps.append(Step(
            n=0, secn=secn, section=section or names.get(secn, ""),
            label=_label(fid) or name, fid=fid, kind=kind,
            value=value, display=_shown(fid, name, value),
            data_point=name, path=tree.getelementpath(node),
            row_label=control.get("row_label", ""), column=column,
            comp_kind=comp_kind,
            attrs={k: v for k, v in node.attrib.items()}))
    steps += _links(source)
    steps += _photo_steps(media, len(steps))
    # In report order, because that is the order an appraiser fills it in.
    # Inside a section the document's own order is kept, except that a
    # comparable is created before anything is written into its column.
    for n, step in enumerate(steps):
        step.n = n                      # the document's own order, to sort by
    steps.sort(key=lambda x: (x.secn or 99, 0 if x.kind == COMP else 1, x.n))
    for n, step in enumerate(steps, start=1):
        step.n = n
    return steps


def _links(source: etree._Element) -> list[Step]:
    """The elements that carry meaning in their attributes, not their text.

    A defect belongs to the unit it was found in through a RELATIONSHIP whose
    xlink arcrole says so, and an element that is only a link has no text at
    all -- so a walk that copies values alone drops it, and the report stops
    showing defects it does hold.  These are written last, once every element
    they point at exists.
    """
    out: list[Step] = []
    tree = source.getroottree()
    for node in source.iter():
        if not isinstance(node.tag, str) or not node.attrib:
            continue
        if (node.text or "").strip():
            continue                     # a value: already written, with its attributes
        out.append(Step(n=0, secn=99, section="Links", kind=LINK,
                        label=etree.QName(node).localname, fid="", value="",
                        display="", data_point=etree.QName(node).localname,
                        path=tree.getelementpath(node),
                        attrs=dict(node.attrib)))
    return out


def _shown(fid: str, data_point: str, value: str) -> str:
    """The value as the report prints it, for the page to show while filling."""
    binding = bind.binding_for(fid) if fid else None
    if binding is None:
        return value
    try:
        return bind.display_value([[(data_point, value)]], binding) or value
    except Exception:                                   # noqa: BLE001
        return value


def _photo_steps(media: Iterable[Any], start: int) -> list[Step]:
    """Every photograph and exhibit the case brings with it."""
    out: list[Step] = []
    for item in media:
        row = item if isinstance(item, dict) else {
            "category": getattr(item, "category", ""),
            "filename": getattr(item, "filename", ""),
            "caption": getattr(item, "caption", ""),
            "section": getattr(item, "section", 0),
            "comparable": getattr(item, "comparable", 0),
            "order": getattr(item, "order", 0),
            "content_type": getattr(item, "content_type", ""),
        }
        if not row.get("filename"):
            continue
        secn = int(row.get("section") or 0)
        out.append(Step(n=start + len(out) + 1, secn=secn or 99,
                        section=bind.SECTION_NAME.get(secn, "Exhibits"),
                        label=row.get("caption") or row["filename"],
                        fid="", kind=PHOTO, value=row["filename"],
                        display=row.get("caption") or row["filename"],
                        media=row))
    return out


# ----------------------------------------------------------------- the write
def _roles_of(party: etree._Element) -> tuple[str, ...]:
    return tuple(sorted((r.text or "").strip()
                        for r in party.iter(f"{M}PartyRoleType") if (r.text or "").strip()))


def party_map(root: etree._Element, source: etree._Element
              ) -> dict[str, dict[int, int]]:
    """Which PARTY of this report each party of the source report is.

    A party is identified by the role it holds, never by where it sits: the
    document lists whoever that report happens to have.  A blank report
    carrying an appraiser and a management company but no lender puts the
    management company first, so writing the source's second party into the
    second position here gave the lender the management company's fee and left
    a role block with no role in it.

    The match is made **once, before anything is written**, and every write
    then follows it.  Working it out per value cannot work: a role arrives as
    a value like any other, so a party not yet given its role matches nothing
    and each later write starts another party -- which is how the appraiser's
    name ended up alone in a party of its own.

    A report can have more than one list of parties: a case with a data
    collector keeps that party in the inspection SERVICE, beside the one the
    valuation uses.  Each list is therefore matched against its own
    counterpart, and the answer is keyed by the address of the list.
    """
    tree = source.getroottree()
    out: dict[str, dict[int, int]] = {}
    lists: dict[str, list[etree._Element]] = {}
    for party in source.iter(f"{M}PARTY"):
        holder = party.getparent()
        if holder is None:
            continue
        lists.setdefault(tree.getelementpath(holder), []).append(party)
    for where, theirs in lists.items():
        here = bind.find_path(root, where)
        if here is None:
            continue                      # nothing of ours to line up with
        mine = here.findall(f"{M}PARTY")
        taken: set[int] = set()
        seats: dict[int, int] = {}
        for n, twin in enumerate(theirs, start=1):
            roles = _roles_of(twin)
            seat = next((i for i, party in enumerate(mine)
                         if i not in taken and roles and _roles_of(party) == roles), None)
            if seat is None:
                seat = next((i for i, party in enumerate(mine)
                             if i not in taken and not _roles_of(party)), None)
            if seat is None:
                fresh = edit.insert_ordered(here, "PARTY")
                mine = here.findall(f"{M}PARTY")
                seat = mine.index(fresh)
            taken.add(seat)
            seats[n] = seat + 1
        out[where] = seats
    return out


PARTY_AT = re.compile(r"^(.*?/(?:\{[^}]*\})?PARTIES)/((?:\{[^}]*\})?PARTY)(?:\[(\d+)\])?")


def _remap_parties(path: str, parties_: dict[str, dict[int, int]]) -> str:
    """Rewrite the party an address names, before anything looks at it.

    The address is rewritten before the walk rather than during it, because a
    path that happens to exist already is taken as found without ever being
    walked -- and an address pointing at the source's first party then wrote
    the lender's role straight over the appraiser's.
    """
    match = PARTY_AT.match(path)
    if not match:
        return path
    seats = parties_.get(match.group(1))
    if not seats:
        return path
    want = int(match.group(3) or 1)
    return (f"{match.group(1)}/{match.group(2)}[{seats.get(want, want)}]"
            + path[match.end():])


def ensure_instance(root: etree._Element, path: str,
                    source: etree._Element | None = None,
                    parties_: dict[int, int] | None = None) -> etree._Element | None:
    """The element this address names, created if the document lacks it.

    A value written into ``SITE_UTILITY[2]`` of the case it came from belongs
    in ``SITE_UTILITY[2]`` here, and a blank report has neither.  So the path
    is walked and each missing step is inserted where the XSD says it goes --
    the same rule every other write in the editor follows.  A block that is
    created takes the attributes its counterpart carries (``ValuationUseType``
    on a comparable's PROPERTY, the ``xlink:label`` a relationship points at),
    because without them the block is not the one the report looks for.
    """
    if not path:
        return None
    if parties_:
        path = _remap_parties(path, parties_)
    node = bind.find_path(root, path)
    if node is not None:
        return node
    cur = root
    walked: list[str] = []
    for match in SEGMENT.finditer(path):
        tag, want = match.group(1), int(match.group(2) or 1)
        walked.append(match.group(0))
        found = cur.findall(f"{M}{tag}")
        while len(found) < want:
            made = edit.insert_ordered(cur, tag)
            if source is not None:
                twin = bind.find_path(source, "/".join(walked))
                if twin is not None:
                    for key, value in twin.attrib.items():
                        made.set(key, value)
            found = cur.findall(f"{M}{tag}")
        cur = found[want - 1]
    return cur


def apply(tree: etree._ElementTree, steps: Iterable[Step],
          source: etree._Element | None = None,
          add_comparable: Callable[[str], int] | None = None,
          add_media: Callable[[dict], None] | None = None) -> dict:
    """Write every step into the document, and say what happened.

    A value is put back exactly where it stood in the case it came from: the
    address names the element, the address is created if it is missing, and
    the value and its attributes (a measure's unit of measure) go with it.
    """
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    written, failed = 0, []
    parties_ = party_map(root, source) if source is not None else {}
    for step in steps:
        try:
            if step.kind == COMP:
                if add_comparable is not None:
                    add_comparable(step.comp_kind)
                else:
                    comparables.add_property(tree, comparables.SHEETS[step.comp_kind][1])
                written += 1
                continue
            if step.kind == PHOTO:
                if add_media is not None:
                    add_media(step.media)
                    written += 1
                continue
            leaf = ensure_instance(root, step.path, source, parties_)
            if leaf is None:
                raise ValueError(f"cannot place {step.data_point} at {step.path}")
            if step.kind != LINK:
                leaf.text = step.value
            for key, value in (step.attrs or {}).items():
                leaf.set(key, value)
            written += 1
        except Exception as exc:                       # noqa: BLE001
            failed.append({"n": step.n, "fid": step.fid, "kind": step.kind,
                           "label": step.label,
                           "reason": f"{type(exc).__name__}: {exc}"[:160]})
    dropped = (_drop_contradicted(root, source) + _drop_leftovers(root, source)
               if source is not None else 0)
    return {"written": written, "failed": failed, "dropped": dropped}


def _drop_contradicted(root: etree._Element, source: etree._Element) -> int:
    """Take out the few values that decide what kind of report this is.

    A blank report inherits them from its template -- a planned unit
    development has a ``ProjectLegalStructureType``, a manufactured home a
    ``ConstructionMethodType`` -- because they decide which sections it shows.
    Filling only ever writes, so a case started as a PUD and filled from a file
    that is not one kept the old answer and went on demanding the association
    fee and the special assessment status a detached house never has.

    A determinant the source does not carry at all is therefore removed, with
    the block it stands in if that block is then empty.  ``templates`` owns the
    list; nothing else is touched.
    """
    from uad import templates

    dropped = 0
    for name in templates.kept_elements():
        if any(True for _ in source.iter(f"{M}{name}")):
            continue                     # the file has its own answer
        for node in list(root.iter(f"{M}{name}")):
            parent = node.getparent()
            if parent is None:
                continue
            parent.remove(node)
            dropped += 1
    return dropped


def _drop_leftovers(root: etree._Element, source: etree._Element) -> int:
    """Take out the blocks the case being filled had and the source does not.

    A blank report is started from a template, and a template keeps the shape
    of its scenario: an empty ROOM, an empty DEFECT, the PROJECT of a planned
    unit development.  Filling only ever writes values, so a case started from
    one scenario and filled from a file of another kept those blocks -- and an
    empty room then demanded a condition status, an empty project an
    association fee, for a property that has neither.

    A block is removed only when it holds no value at all, the source has
    nothing at that address, and the schema does not insist on it being there.
    The walk is top-down, so a whole empty branch goes at its root rather than
    leaf by leaf, and any relationship that pointed into it goes with it.
    Nothing anyone typed is ever thrown away.
    """
    from uad import xsd_order

    tree = root.getroottree()
    labels = {rel.get(f"{{{XLINK}}}{end}") for rel in root.iter(f"{M}RELATIONSHIP")
              for end in ("from", "to")}
    dropped, gone = 0, set()
    for node in list(root.iter()):
        if not isinstance(node.tag, str) or node is root:
            continue
        parent = node.getparent()
        if parent is None or not _attached(node, root):
            continue                     # already taken out with its branch
        if "".join(node.itertext()).strip():
            continue                     # it holds something: leave it alone
        if not _only_a_spare_label(node, labels):
            continue                     # an attribute is a value of its own
        name = etree.QName(node).localname
        if name in xsd_order.required(etree.QName(parent).localname) and \
                len(parent.findall(f"{M}{name}")) == 1:
            continue                     # the schema insists on one being there
        if bind.find_path(source, tree.getelementpath(node)) is not None:
            continue                     # the source has it too
        gone.update(x.get(f"{{{XLINK}}}label") for x in node.iter()
                    if isinstance(x.tag, str) and x.get(f"{{{XLINK}}}label"))
        parent.remove(node)
        dropped += 1
    for rel in list(root.iter(f"{M}RELATIONSHIP")):
        if {rel.get(f"{{{XLINK}}}from"), rel.get(f"{{{XLINK}}}to")} & gone:
            rel.getparent().remove(rel)
            dropped += 1
    return dropped


def _attached(node: etree._Element, root: etree._Element) -> bool:
    """Is this element still part of the document?

    The walk takes whole branches out as it goes, and lxml keeps the children
    of a removed branch perfectly usable -- asking one of them for its path
    raises "Element is not in this tree", which aborted the run.
    """
    cur = node
    while cur is not None:
        if cur is root:
            return True
        cur = cur.getparent()
    return False


def _only_a_spare_label(node: etree._Element, labels: set) -> bool:
    """Is this block empty, counting a link label nothing points at as empty?

    A template's blocks carry an ``xlink:label`` so a relationship *could*
    name them.  A label no relationship uses says nothing about the property,
    so a block that holds only that is still an empty block.
    """
    for name, value in node.attrib.items():
        if name == f"{{{XLINK}}}label" and value not in labels:
            continue
        return False
    return True


