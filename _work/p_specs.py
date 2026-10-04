import pathlib

p = pathlib.Path("engine/uad/report/comparables.py")
s = p.read_text(encoding="utf-8")

# --- the spec row carries what an added row needs ---------------------------
old = """    data_point: str = ""
    rules: str = ""
    adjust_type: str = \"\""""
new = """    data_point: str = ""
    rules: str = ""
    adjust_type: str = ""
    # An added row ("[Additional Row]") is one the appraiser names.  Once
    # named it behaves as an ordinary row whose label is that name, so the
    # expansion happens in one place and every reader sees the same rows.
    item_name: str = ""
    container: str = ""
    new_item: bool = False"""
assert old in s, "GridRow fields"
s = s.replace(old, new, 1)

# --- one expansion, used by the grid, the editor and the API ----------------
old = """def build(tree, kind: str = "sales", *, per_block: int = 3, every_row: bool = False) -> list[Grid]:"""
new = '''def specs(root: etree._Element, kind: str = "sales", *,
          every_row: bool = False) -> list[GridRow]:
    """The rows of a grid, with every added row expanded into its own.

    The workbook gives each group one "[Additional Row]" template; a case may
    have named several, and they are all kept under one adjustment type, so
    the template is expanded here -- once, at the last place the workbook
    offers it -- and every part of the program reads the same list.
    """
    _sheet, role, _title = SHEETS[kind]
    props = properties(root, role)
    subject = bind.subject(root)
    everywhere = ([subject] if subject is not None else []) + props
    spec = rows(kind)
    last: dict[tuple[str, str], int] = {}
    for row in spec:
        if row.label == ADDITIONAL_ROW:
            last[line_item_place(kind, row)] = row.order
    out: list[GridRow] = []
    for row in spec:
        if row.label != ADDITIONAL_ROW:
            out.append(row)
            continue
        where = line_item_place(kind, row)
        if row.order != last.get(where):
            continue
        container, adjust_type = where
        for name in line_items(root, kind, row, everywhere):
            out.append(replace(row, label=name, item_name=name,
                               container=container, adjust_type=adjust_type))
        if every_row:
            out.append(replace(row, item_name="", container=container,
                               adjust_type=adjust_type, new_item=True))
    return out


def build(tree, kind: str = "sales", *, per_block: int = 3, every_row: bool = False) -> list[Grid]:'''
assert old in s, "specs"
s = s.replace(old, new, 1)

# --- build() uses it --------------------------------------------------------
old = """    subject = bind.subject(root)
    spec = rows(kind)
    last_additional: dict[tuple[str, str], int] = {}
    for r in spec:
        if r.label == ADDITIONAL_ROW:
            last_additional[line_item_place(kind, r)] = r.order"""
new = """    subject = bind.subject(root)
    spec = specs(root, kind, every_row=every_row)"""
assert old in s, "build spec"
s = s.replace(old, new, 1)

start = s.index("            if row.label == ADDITIONAL_ROW:")
end = s.index("            subject_text = (value_for(root, row.subject_fid, subject, row)", start)
s = s[:start] + s[end:]

# --- reading a cell of an added row ----------------------------------------
old = """    binding = binding_of(field_id)
    if binding is None:
        return ""
    groups = []"""
new = """    if row is not None and row.container and scope is not None:
        # an added row keeps its value beside its name, not where the field's
        # own path would otherwise look
        text, _adjust = line_item_value(scope, row.container, row.adjust_type,
                                        row.item_name)
        return text
    binding = binding_of(field_id)
    if binding is None:
        return ""
    groups = []"""
assert old in s, "value_for item"
s = s.replace(old, new, 1)

old = """    if not row.adjust_fid:
        return ""
    want = row.adjust_type"""
new = """    if row.container:
        _text, amount = line_item_value(prop, row.container, row.adjust_type,
                                        row.item_name)
        return amount
    if not row.adjust_fid:
        return ""
    want = row.adjust_type"""
assert old in s, "adjustment_for item"
s = s.replace(old, new, 1)

s = s.replace("from dataclasses import dataclass, field",
              "from dataclasses import dataclass, field, replace", 1)
p.write_text(s, encoding="utf-8")
print("ok")
