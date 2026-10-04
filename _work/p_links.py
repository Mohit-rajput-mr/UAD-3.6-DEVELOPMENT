import pathlib
p=pathlib.Path("engine/app/autofill.py"); s=p.read_text(encoding="utf-8")

s=s.replace('PICK, CHECK, TEXT, CELL, COMP, GRID, PHOTO, DATA = (\n'
            '    "pick", "check", "text", "cell", "comp", "grid", "photo", "data")',
            'PICK, CHECK, TEXT, CELL, COMP, GRID, PHOTO, DATA, LINK = (\n'
            '    "pick", "check", "text", "cell", "comp", "grid", "photo", "data", "link")',1)

old = '''    steps += _photo_steps(media, len(steps))'''
new = '''    steps += _links(source)
    steps += _photo_steps(media, len(steps))'''
assert old in s; s=s.replace(old,new,1)

helper = '''def _links(source: etree._Element) -> list[Step]:
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


def _shown(fid: str, data_point: str, value: str) -> str:'''
s=s.replace("def _shown(fid: str, data_point: str, value: str) -> str:", helper, 1)

old = '''            leaf = ensure_instance(root, step.path, source)
            if leaf is None:
                raise ValueError(f"cannot place {step.data_point} at {step.path}")
            leaf.text = step.value'''
new = '''            leaf = ensure_instance(root, step.path, source)
            if leaf is None:
                raise ValueError(f"cannot place {step.data_point} at {step.path}")
            if step.kind != LINK:
                leaf.text = step.value'''
assert old in s; s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8"); print("ok")
