import pathlib

p = pathlib.Path("engine/app/autofill.py")
s = p.read_text(encoding="utf-8")

old = '''    dropped = _drop_leftovers(root, source) if source is not None else 0
    return {"written": written, "failed": failed, "dropped": dropped}'''
new = '''    dropped = (_drop_contradicted(root, source) + _drop_leftovers(root, source)
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
    return dropped'''
assert old in s, "apply tail"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("ok")
