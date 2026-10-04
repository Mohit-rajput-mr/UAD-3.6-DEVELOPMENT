import pathlib

p = pathlib.Path("engine/app/autofill.py")
s = p.read_text(encoding="utf-8")

start = s.index("def _drop_leftovers(root: etree._Element, source: etree._Element) -> int:")
end = s.index("def _write_grid(") if "def _write_grid(" in s[start:] else len(s)
end = s.index("def _write_grid(", start) if "def _write_grid(" in s[start:] else len(s)

NEW = '''def _drop_leftovers(root: etree._Element, source: etree._Element) -> int:
    """Take out the blocks the case being filled had and the source does not.

    A blank report is started from a template, and a template keeps the shape
    of its scenario: an empty ROOM, an empty DEFECT, the PROJECT of a planned
    unit development.  Filling only ever writes values, so a case started from
    one scenario and filled from a file of another kept those blocks -- and an
    empty room then demanded a condition status, an empty project an
    association fee, for a property that has neither.

    Only a block the source does not have **and** that holds no value here is
    removed, deepest first so a container empties before it is judged; nothing
    anyone typed is ever thrown away.
    """
    tree = root.getroottree()
    nodes = [n for n in root.iter() if isinstance(n.tag, str) and n is not root]
    nodes.sort(key=lambda n: len(list(n.iterancestors())), reverse=True)
    dropped = 0
    for node in nodes:
        parent = node.getparent()
        if parent is None:
            continue                     # already taken out with its parent
        if "".join(node.itertext()).strip() or node.attrib:
            continue                     # it holds something: leave it alone
        path = tree.getelementpath(node)
        if bind.find_path(source, path) is not None:
            continue                     # the source has it too
        parent.remove(node)
        dropped += 1
    return dropped


'''
s = s[:start] + NEW + s[end:]
p.write_text(s, encoding="utf-8")
print("ok")
