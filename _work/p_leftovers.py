import pathlib

p = pathlib.Path("engine/app/autofill.py")
s = p.read_text(encoding="utf-8")

old = """            failed.append({"n": step.n, "fid": step.fid, "kind": step.kind,
                           "label": step.label,
                           "reason": f"{type(exc).__name__}: {exc}"[:160]})
    return {"written": written, "failed": failed}"""
new = """            failed.append({"n": step.n, "fid": step.fid, "kind": step.kind,
                           "label": step.label,
                           "reason": f"{type(exc).__name__}: {exc}"[:160]})
    dropped = _drop_leftovers(root, source) if source is not None else 0
    return {"written": written, "failed": failed, "dropped": dropped}


def _drop_leftovers(root: etree._Element, source: etree._Element) -> int:
    \"\"\"Take out the blocks the case being filled had and the source does not.

    A blank report is started from a template, and a template keeps the few
    elements that decide the report's *shape* -- a planned unit development has
    a PROJECT, a manufactured home has its own section.  Filling only ever
    writes values, so a case started from one shape and filled from a file of
    another kept the old block: an empty PROJECT that then demanded an
    association fee the file never had.

    Only a block the source does not have **and** that holds no value here is
    removed, so nothing anyone typed is ever thrown away.
    \"\"\"
    tree = root.getroottree()
    dropped = 0
    for node in list(root.iter()):
        if not isinstance(node.tag, str) or node.getparent() is None:
            continue
        if node.getroottree() is not tree:
            continue                     # already taken out with its parent
        if "".join(node.itertext()).strip():
            continue                     # it holds something: leave it alone
        path = tree.getelementpath(node)
        if bind.find_path(source, path) is not None:
            continue                     # the source has it too
        node.getparent().remove(node)
        dropped += 1
    return dropped"""
assert old in s, "apply tail"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("ok")
