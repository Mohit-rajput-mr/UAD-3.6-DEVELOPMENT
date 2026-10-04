import pathlib

p = pathlib.Path("engine/app/autofill.py")
s = p.read_text(encoding="utf-8")

old = """    tree = root.getroottree()
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
    return dropped"""
new = """    from uad import xsd_order

    tree = root.getroottree()
    labels = {rel.get(f"{{{XLINK}}}{end}") for rel in root.iter(f"{M}RELATIONSHIP")
              for end in ("from", "to")}
    nodes = [n for n in root.iter() if isinstance(n.tag, str) and n is not root]
    nodes.sort(key=lambda n: len(list(n.iterancestors())), reverse=True)
    dropped = 0
    for node in nodes:
        parent = node.getparent()
        if parent is None:
            continue                     # already taken out with its parent
        if "".join(node.itertext()).strip():
            continue                     # it holds something: leave it alone
        if not _only_a_spare_label(node, labels):
            continue                     # an attribute is a value of its own
        name = etree.QName(node).localname
        if name in xsd_order.required(etree.QName(parent).localname):
            continue                     # the schema insists on it being there
        path = tree.getelementpath(node)
        if bind.find_path(source, path) is not None:
            continue                     # the source has it too
        parent.remove(node)
        dropped += 1
    return dropped


def _only_a_spare_label(node: etree._Element, labels: set) -> bool:
    \"\"\"Is this block empty, counting a link label nothing points at as empty?

    A template's blocks carry an ``xlink:label`` so a relationship *could*
    name them.  A label no relationship uses says nothing about the property,
    so a block that holds only that is still an empty block.
    \"\"\"
    for name, value in node.attrib.items():
        if name == f"{{{XLINK}}}label" and value not in labels:
            continue
        return False
    return True"""
assert old in s, "leftovers body"
s = s.replace(old, new, 1)

if "XLINK = " not in s:
    s = s.replace('M = f"{{{bind.MISMO}}}"',
                  'M = f"{{{bind.MISMO}}}"\nXLINK = "http://www.w3.org/1999/xlink"', 1)
p.write_text(s, encoding="utf-8")
print("ok")
