import pathlib

p = pathlib.Path("engine/app/autofill.py")
s = p.read_text(encoding="utf-8")

start = s.index("def _drop_leftovers(root: etree._Element, source: etree._Element) -> int:")
tail_start = s.index("def _only_a_spare_label(")
tail_end = len(s)

NEW = '''def _drop_leftovers(root: etree._Element, source: etree._Element) -> int:
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
        if parent is None:
            continue                     # already taken out with its branch
        if "".join(node.itertext()).strip():
            continue                     # it holds something: leave it alone
        if not _only_a_spare_label(node, labels):
            continue                     # an attribute is a value of its own
        name = etree.QName(node).localname
        if name in xsd_order.required(etree.QName(parent).localname) and \\
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


'''

TAIL = '''def _only_a_spare_label(node: etree._Element, labels: set) -> bool:
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


'''

s = s[:start] + NEW + TAIL + s[tail_end:]
p.write_text(s, encoding="utf-8")
print("ok")
