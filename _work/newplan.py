NEW = '''# ------------------------------------------------------------------ the plan
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

    comps: dict[int, tuple[str, int]] = {}      # PROPERTY id -> (kind, column)
    steps: list[Step] = []
    for kind, (_sheet, role, _section) in comparables.SHEETS.items():
        if kind == "not_used":
            continue
        for number, prop in enumerate(comparables.properties(source, role), start=1):
            comps[id(prop)] = (kind, number)

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
        if fid and fid.split(".")[0] in ("1",):
            continue                      # the Summary redisplays; it is not typed
        control = drawn.get(fid, {})
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
            if id(ancestor) in comps:
                comp_kind, column = comps[id(ancestor)]
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
        steps.append(Step(
            n=0, secn=secn, section=section or names.get(secn, ""),
            label=_label(fid) or name, fid=fid, kind=kind,
            value=value, display=_shown(fid, name, value),
            data_point=name, path=tree.getelementpath(node),
            row_label=control.get("row_label", ""), column=column,
            comp_kind=comp_kind,
            attrs={k: v for k, v in node.attrib.items()}))
    steps += _photo_steps(media, len(steps))
    for n, step in enumerate(steps, start=1):
        step.n = n
    return steps


def _shown(fid: str, data_point: str, value: str) -> str:
    """The value as the report prints it, for the page to show while filling."""
    binding = bind.binding_for(fid) if fid else None
    if binding is None:
        return value
    try:
        return bind.display_value([[(data_point, value)]], binding) or value
    except Exception:                                   # noqa: BLE001
        return value


'''
import pathlib
p=pathlib.Path("engine/app/autofill.py"); s=p.read_text(encoding="utf-8")
assert "__PLAN__" in s
s=s.replace("__PLAN__", NEW.rstrip("\n"), 1)
s=s.replace("import re\nimport sys", "import json\nimport re\nimport sys",1)
s=s.replace("from dataclasses import dataclass, field as _field",
            "from dataclasses import dataclass, field as _field\nfrom functools import lru_cache",1)
s=s.replace('PICK, CHECK, TEXT, CELL, COMP, GRID, PHOTO = (\n    "pick", "check", "text", "cell", "comp", "grid", "photo")',
            'PICK, CHECK, TEXT, CELL, COMP, GRID, PHOTO, DATA = (\n'
            '    "pick", "check", "text", "cell", "comp", "grid", "photo", "data")')
s=s.replace('    media: dict = _field(default_factory=dict)',
            '    media: dict = _field(default_factory=dict)\n'
            '    attrs: dict = _field(default_factory=dict)')
p.write_text(s,encoding="utf-8"); print("ok")
